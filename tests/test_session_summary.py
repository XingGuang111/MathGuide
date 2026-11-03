"""The sidebar only exposes problem data and confirmed student progress."""
import json
from unittest.mock import patch

import agent
import llm
import session_summary
import web_app
from tests.test_web_app import _client


QUESTION = '长方形长12米宽8米，面积是多少？'
ANALYZED = dict(is_elementary_math=True, knowledge_id=12,
                question_type='几何应用题', raw_knowledge=None)


def start(client):
    with patch('agent.llm.analyze', return_value=ANALYZED):
        response = client.post('/api/sessions', json={'question': QUESTION})
    assert response.status_code == 200
    return response.json()


def reply(client, sid, text):
    with patch('agent.llm.chat_stream', side_effect=lambda *_: iter(['继续看题。[CONTINUE]'])):
        response = client.post('/api/replies', json={'session_id': sid, 'message': text})
    assert response.status_code == 200
    return response.json()


def test_summary_tracks_reading_corrections_and_survives_restart(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    data = start(client)
    sid = data['session_id']
    summary = data['summary']
    assert [row['value'] for row in summary['conditions']] == ['12米', '8米']
    assert not any(row['confirmed'] for row in summary['conditions'])
    assert summary['expression'] == '' and summary['method'] == ''
    assert '96' not in json.dumps(summary)
    data = reply(client, sid, '长12米')
    assert data['summary']['conditions'][0]['confirmed']
    data = reply(client, sid, '长13米')
    assert not data['summary']['conditions'][0]['confirmed']
    assert data['summary']['conditions'][0]['value'] == '12米'
    data = reply(client, sid, '长12米，宽8米，求面积')
    assert all(row['confirmed'] for row in data['summary']['conditions'])
    assert data['summary']['target_confirmed']
    assert '读懂题目' in data['summary']['completed']
    data = reply(client, sid, '面积用长乘宽')
    assert '长乘宽' in data['summary']['method']
    data = reply(client, sid, '12×8')
    assert data['summary']['expression']
    before = data['summary']
    web_app._sessions.clear()
    web_app._activity.clear()
    web_app._restore()
    assert client.get('/api/sessions/' + sid).json()['summary'] == before
    data = reply(client, sid, '96平方米')
    assert data['finished']
    assert data['summary']['status'] == '本题已解出'
    assert '完成计算' in data['summary']['completed']


def test_failed_reply_does_not_confirm_student_fact(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    data = start(client)
    before = data['summary']
    sid = data['session_id']
    with patch('agent.llm.chat_stream', side_effect=llm.LLMError('offline')):
        data = client.post('/api/replies', json={'session_id': sid, 'message': '我想先看看图'}).json()
    assert data['retryable']
    assert data['summary'] == before


def test_unknown_question_keeps_statements_unconfirmed_and_does_not_invent_method():
    tutor = agent.TutorAgent()
    tutor.question_text = '三角形底10米，高6米，面积是多少？'
    tutor.state = agent.AgentState.STAGE1_UNDERSTAND
    tutor.dialogue = [{'role':'student', 'content':'我猜面积是60平方米'}]
    summary = session_summary.build(tutor)
    assert [row['value'] for row in summary['conditions']] == ['三角形底10米', '高6米']
    assert not any(row['confirmed'] for row in summary['conditions'])
    assert not summary['method'] and not summary['expression']
    assert '60' not in json.dumps(summary)


def test_equal_share_and_discount_summaries_do_not_reveal_results():
    tutor = agent.TutorAgent()
    tutor.state = agent.AgentState.STAGE1_UNDERSTAND
    for question, expected in [('老师有24颗糖，平均分给6个小朋友，每个人有几颗？', ['24颗', '6人']),
                               ('一件商品原价200元，打八折后多少钱？', ['200元', '80%'])]:
        tutor.question_text = question
        summary = session_summary.build(tutor)
        assert [row['value'] for row in summary['conditions']] == expected
        assert summary['expression'] == ''
