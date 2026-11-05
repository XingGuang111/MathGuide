import json
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

import config
import llm
import model_gateway
import model_settings
import web_app


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(model_settings, 'SETTINGS_PATH', tmp_path / 'settings.json')


def online(**kwargs):
    return model_settings.SettingsRequest(provider='compatible', **kwargs)


def test_settings_persist_switch_and_never_return_key():
    client = TestClient(web_app.app)
    payload = online(api_key='secret-token').model_dump()
    response = client.put('/api/model-settings', json=payload)
    assert response.status_code == 200
    assert 'secret-token' not in response.text
    assert response.json()['has_api_key'] is True
    assert 'secret-token' not in client.get('/api/model-settings').text
    assert model_settings.current().api_key == 'secret-token'
    payload.update(api_key='', provider='ollama')
    client.put('/api/model-settings', json=payload)
    assert model_settings.current().provider == 'ollama'
    assert model_settings.current().api_key == 'secret-token'
    payload.update(provider='compatible', base_url='https://other.example/v1')
    client.put('/api/model-settings', json=payload)
    assert model_settings.current().api_key == ''


def test_clear_key_and_invalid_address_do_not_overwrite_settings():
    model_settings.save(online(api_key='secret'))
    model_settings.save(online(clear_api_key=True))
    assert model_settings.current().api_key == ''
    client = TestClient(web_app.app)
    payload = online().model_dump()
    for address in ['file:///secret', 'https://secret@example.com/v1', 'https://example.com?key=secret']:
        assert client.put('/api/model-settings', json={**payload, 'base_url': address}).status_code == 422
    assert model_settings.current().base_url == online().base_url


def test_configuration_rejects_remote_clients_and_cross_origin():
    client = TestClient(web_app.app, client=('192.168.1.2', 1234))
    assert client.get('/api/model-settings').status_code == 403
    client = TestClient(web_app.app)
    assert client.put('/api/model-settings', json=online().model_dump(),
                      headers={'Origin': 'https://another.example'}).status_code == 403


def test_connection_test_uses_draft_without_saving():
    client = TestClient(web_app.app)
    with patch('model_gateway.check_health', return_value=None) as check:
        assert client.post('/api/model-settings/test', json=online().model_dump()).json()['ok']
    assert check.call_args.args[0].provider == 'compatible'
    assert model_settings.current().provider == 'ollama'
    assert not model_settings.SETTINGS_PATH.exists()


def test_online_json_and_stream_requests_are_translated(monkeypatch):
    requests = []
    def handle(request):
        data = json.loads(request.content)
        requests.append((request, data))
        if data['stream']:
            return httpx.Response(200, text='data: {"choices":[{"delta":{"role":"assistant"}}]}\n\ndata: {"choices":[{"delta":{"content":"你好"}}]}\n\ndata: [DONE]\n\n')
        return httpx.Response(200, json={'choices': [{'message': {'content': '{"reply":"想一想"}'}}]})
    real_client = httpx.Client
    monkeypatch.setattr(model_gateway.httpx, 'Client', lambda **kw: real_client(transport=httpx.MockTransport(handle), **kw))
    model_settings.save(online(api_key='secret'))
    assert llm.compose_reply([{'role': 'user', 'content': '题目'}]) == '想一想'
    assert ''.join(llm.chat_stream([{'role': 'user', 'content': '你好'}])) == '你好'
    request, body = requests[0]
    assert str(request.url) == 'https://api.deepseek.com/v1/chat/completions'
    assert request.headers['Authorization'] == 'Bearer secret'
    assert body['model'] == 'deepseek-chat'
    assert body['response_format'] == {'type': 'json_object'}
    assert body['max_tokens'] == 384


@pytest.mark.parametrize('status', [401, 429, 500])
def test_upstream_errors_do_not_leak_credentials(monkeypatch, status):
    real_client = httpx.Client
    transport = httpx.MockTransport(lambda req: httpx.Response(status, text='secret-token'))
    monkeypatch.setattr(model_gateway.httpx, 'Client', lambda **kw: real_client(transport=transport, **kw))
    message = model_gateway.check_health(online(api_key='secret-token'))
    assert 'secret-token' not in message
    assert str(status) in message


def test_custom_local_endpoint_and_model():
    settings = model_settings.ModelSettings(ollama_url='http://localhost:12345', ollama_model='qwen-test')
    with patch('model_gateway.ollama.Client') as client:
        model_gateway.chat(settings=settings, messages=[{'role': 'user', 'content': '你好'}])
    client.assert_called_once_with(host='http://localhost:12345', timeout=60)
    assert client.return_value.chat.call_args.kwargs['model'] == 'qwen-test'


def test_multiple_favorites_persist_and_only_active_is_called():
    model_settings.save(online(online_model='official-model-b',
                               online_models=['official-model-a', 'official-model-b', 'official-model-a']))
    saved = model_settings.current()
    assert saved.online_models == ['official-model-b', 'official-model-a']
    assert model_settings.model_name() == 'official-model-b'
    with patch('model_gateway._online', return_value={'message': {'content': 'OK'}}) as call:
        model_gateway.chat(messages=[{'role': 'user', 'content': 'hello'}])
    assert call.call_args.args[0].online_model == 'official-model-b'


def test_old_configuration_loads_with_active_model_as_favorite():
    model_settings.SETTINGS_PATH.write_text(json.dumps({'provider': 'compatible', 'online_model': 'old-model'}), encoding='utf-8')
    assert model_settings.current().online_models == ['old-model']


def test_official_model_list_uses_endpoint_and_key_without_chat(monkeypatch):
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={'data': [{'id': 'official-b'}, {'id': 'official-a'},
                                                 {'id': 'official-b'}, {'id': ''}, {'id': None}]})
    real_client = httpx.Client
    monkeypatch.setattr(model_gateway.httpx, 'Client', lambda **kw: real_client(transport=httpx.MockTransport(handle), **kw))
    assert model_gateway.list_models(online(api_key='secret')) == ['official-a', 'official-b']
    assert len(requests) == 1
    assert requests[0].method == 'GET'
    assert str(requests[0].url) == 'https://api.deepseek.com/v1/models'
    assert requests[0].headers['Authorization'] == 'Bearer secret'


@pytest.mark.parametrize('status,body', [(401, {'error': 'secret'}), (404, {}), (200, {'data': 'wrong'})])
def test_model_list_errors_are_actionable_and_do_not_leak_key(monkeypatch, status, body):
    real_client = httpx.Client
    transport = httpx.MockTransport(lambda req: httpx.Response(status, json=body))
    monkeypatch.setattr(model_gateway.httpx, 'Client', lambda **kw: real_client(transport=transport, **kw))
    with pytest.raises(model_gateway.ModelConnectionError) as error:
        model_gateway.list_models(online(api_key='secret'))
    assert 'secret' not in str(error.value)
    assert '官网' in str(error.value) or '密钥' in str(error.value)


def test_local_model_list_reads_installed_models():
    with patch('model_gateway.ollama.Client') as factory:
        factory.return_value.list.return_value = {'models': [{'model': 'qwen:3b'}, {'name': 'custom:latest'}]}
        assert model_gateway.list_models(model_settings.ModelSettings()) == ['custom:latest', 'qwen:3b']


def test_list_endpoint_preserves_settings_and_uses_saved_key_only_for_same_url():
    model_settings.save(online(api_key='saved-secret'))
    client = TestClient(web_app.app)
    before = model_settings.SETTINGS_PATH.read_bytes()
    with patch('model_gateway.list_models', return_value=['new-official-model']) as fetch:
        response = client.post('/api/model-settings/models', json=online().model_dump())
        assert response.json() == {'models': ['new-official-model']}
        assert fetch.call_args.args[0].api_key == 'saved-secret'
        client.post('/api/model-settings/models', json=online(base_url='https://other.example/v1').model_dump())
        assert fetch.call_args.args[0].api_key == ''
    assert model_settings.SETTINGS_PATH.read_bytes() == before
    remote = TestClient(web_app.app, client=('192.168.1.2', 1234))
    assert remote.post('/api/model-settings/models', json=online().model_dump()).status_code == 403


def test_deepseek_probe_has_budget_for_answer_and_disables_thinking(monkeypatch):
    requests = []
    def handle(request):
        payload = json.loads(request.content)
        requests.append(payload)
        if payload.get('thinking') != {'type': 'disabled'} or payload['max_tokens'] < 32:
            return httpx.Response(200, json={'choices': [{'finish_reason': 'length', 'message': {'content': '', 'reasoning_content': 'internal'}}]})
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': 'OK'}}]})
    real_client = httpx.Client
    monkeypatch.setattr(model_gateway.httpx, 'Client', lambda **kw: real_client(transport=httpx.MockTransport(handle), **kw))
    assert model_gateway.check_health(online(online_model='deepseek-v4-pro')) is None
    assert len(requests) == 1


def test_truncated_reasoning_is_not_reported_as_bad_connection(monkeypatch):
    real_client = httpx.Client
    requests = []
    def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={'choices': [{'finish_reason': 'length', 'message': {'content': '', 'reasoning_content': 'private reasoning'}}]})
    monkeypatch.setattr(model_gateway.httpx, 'Client', lambda **kw: real_client(transport=httpx.MockTransport(handle), **kw))
    message = model_gateway.check_health(online(base_url='https://another.example/v1'))
    assert '长度上限' in message
    assert 'private reasoning' not in message
    assert 'thinking' not in requests[0]
