"""Ollama and OpenAI-compatible chat adapters, with a common response shape."""
import json
from urllib.parse import urlsplit

import httpx
import ollama

import model_settings


class ModelConnectionError(Exception):
    pass


def list_models(settings):
    """Ask the configured service for its current model IDs; never guess names."""
    try:
        if settings.provider == 'ollama':
            data = ollama.Client(host=settings.ollama_url, timeout=10).list()
            rows = data.get('models', [])
            names = [row.get('model') or row.get('name') for row in rows]
        else:
            headers = {'Authorization': 'Bearer ' + settings.api_key} if settings.api_key else {}
            with httpx.Client(timeout=15, follow_redirects=False) as client:
                response = client.get(settings.base_url + '/models', headers=headers)
                if response.status_code in (404, 405):
                    raise ModelConnectionError('此服务未提供模型列表接口，请在服务商官网查询模型 ID 后手动添加。')
                _check_response(response)
                rows = response.json()['data']
                if not isinstance(rows, list):
                    raise ValueError('invalid model list')
                names = [row.get('id') for row in rows if isinstance(row, dict)]
        return sorted({name.strip() for name in names
                       if isinstance(name, str) and 0 < len(name.strip()) <= 200})
    except ModelConnectionError:
        raise
    except httpx.TimeoutException as exc:
        raise ModelConnectionError('获取模型列表超时，请稍后重试，或从官网查询后手动添加。') from exc
    except Exception as exc:
        raise ModelConnectionError('无法读取模型列表，请检查服务地址、密钥与网络，或从官网查询后手动添加。') from exc


def _online(settings, messages, options, format, stream, timeout):
    payload = {'model': settings.online_model, 'messages': list(messages), 'stream': stream,
               'temperature': options.get('temperature', 0.2),
               'max_tokens': options.get('num_predict', 512)}
    # Tutor requests have short output budgets. DeepSeek's thinking mode can
    # exhaust them before producing any answer, including the connection probe.
    if urlsplit(settings.base_url).hostname == 'api.deepseek.com':
        payload['thinking'] = {'type': 'disabled'}
    if format:
        instruction = '请只返回有效 JSON 对象，不要包含 Markdown 代码块。'
        if isinstance(format, dict):
            instruction += '遵循此 JSON Schema：' + json.dumps(format, ensure_ascii=False)
        payload['messages'] = [{'role': 'system', 'content': instruction}] + payload['messages']
        payload['response_format'] = {'type': 'json_object'}
    headers = {'Authorization': 'Bearer ' + settings.api_key} if settings.api_key else {}
    url = settings.base_url + '/chat/completions'
    if stream:
        return _stream(url, headers, payload, timeout)
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        response = client.post(url, headers=headers, json=payload)
        _check_response(response)
        try:
            choice = response.json()['choices'][0]
            content = choice['message']['content']
            if choice.get('finish_reason') == 'length':
                raise ModelConnectionError('模型输出达到长度上限，回答未完成；请关闭服务端的深度思考模式或换用普通对话模型。')
            if not isinstance(content, str) or not content.strip():
                raise ValueError('empty response')
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ModelConnectionError('模型返回了空内容或不兼容的回复格式。') from exc
        return {'message': {'content': content}}


def _check_response(response):
    if not response.is_success:
        # Do not expose upstream bodies or headers, which may contain credentials.
        message = {401: '密钥无效，请检查 API Key。', 403: '没有访问此模型的权限。',
                   404: '服务地址或模型名称不存在。', 429: '请求过于频繁或额度不足。'}.get(
                       response.status_code, '模型服务请求失败，请检查地址和模型配置。')
        raise ModelConnectionError(f'{message}（HTTP {response.status_code}）')


def _stream(url, headers, payload, timeout):
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            with client.stream('POST', url, headers=headers, json=payload) as response:
                _check_response(response)
                for line in response.iter_lines():
                    if not line.startswith('data:'):
                        continue
                    data = line[5:].strip()
                    if data == '[DONE]':
                        return
                    if not data:
                        continue
                    chunk = json.loads(data)
                    if 'error' in chunk:
                        raise ModelConnectionError('模型生成中断，请重试。')
                    choices = chunk.get('choices') or []
                    content = choices[0].get('delta', {}).get('content') if choices else None
                    if content:
                        yield {'message': {'content': content}}
    except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError) as exc:
        raise ModelConnectionError('模型连接中断或返回了不兼容的数据，请重试。') from exc


def chat(*, client=None, timeout=60, settings=None, model=None, messages,
         format=None, options=None, stream=False):
    settings = settings or model_settings.current()
    options = options or {}
    try:
        if settings.provider == 'compatible':
            return _online(settings, messages, options, format, stream, timeout)
        local = client or ollama
        if settings.ollama_url != 'http://127.0.0.1:11434':
            local = ollama.Client(host=settings.ollama_url, timeout=timeout)
        kwargs = dict(model=settings.ollama_model, messages=messages, options=options, stream=stream)
        if format:
            kwargs['format'] = format
        return local.chat(**kwargs)
    except httpx.HTTPError as exc:
        raise ModelConnectionError('无法连接模型服务，请检查服务地址、网络或超时设置。') from exc


def check_health(settings=None):
    settings = settings or model_settings.current()
    try:
        if settings.provider == 'compatible':
            chat(settings=settings, messages=[{'role': 'user', 'content': '请回复 OK'}],
                 options={'num_predict': 128}, timeout=30)
        else:
            data = ollama.Client(host=settings.ollama_url, timeout=5).list()
            names = {m.get('model') or m.get('name', '') for m in data.get('models', [])}
            wanted = settings.ollama_model
            if wanted not in names and wanted + ':latest' not in names:
                if wanted in ('mathguide-qwen25-3b', 'mathguide-qwen25-3b:latest'):
                    return ('请先运行：\nollama pull qwen2.5:3b-instruct-q4_K_M\n'
                            'ollama create mathguide-qwen25-3b -f models/Modelfile.qwen25-mathguide')
                return f'本地服务中没有模型 {wanted}。请下载模型：ollama pull {wanted}；自定义模型请先创建。'
        return None
    except ModelConnectionError as exc:
        return str(exc)
    except Exception:
        service = 'Ollama' if settings.provider == 'ollama' else '所选模型'
        return f'无法连接 {service}，请检查服务是否启动、地址和模型名称是否正确。'
