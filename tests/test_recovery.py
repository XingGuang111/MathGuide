import copy
import json
import threading
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import agent
import db
import llm
import web_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app.config, "DB_PATH", str(tmp_path / "test.db"))
    web_app._sessions.clear()
    web_app._activity.clear()
    web_app._turn_locks.clear()
    with TestClient(web_app.app) as result:
        yield result


def start(client):
    with patch("agent.llm.analyze", return_value={"is_elementary_math": True,
               "knowledge_id": 12, "question_type": "几何应用题", "raw_knowledge": None}), \
         patch("agent.llm.chat_stream", return_value=iter(["面积公式是什么？[CONTINUE]"])):
        return client.post("/api/sessions", json={"question": "长方形长12米宽8米，面积是多少？"}).json()["session_id"]


def test_restart_restores_dialogue(client):
    sid = start(client)
    web_app._sessions.clear()
    web_app._activity.clear()
    web_app._restore()
    response = client.get(f"/api/sessions/{sid}")
    assert response.status_code == 200
    assert '不明白' in response.json()["dialogue"][0]["content"]
    assert web_app._sessions[sid].state == agent.AgentState.STAGE1_UNDERSTAND
    assert '第一步：读懂题目' in web_app._sessions[sid].stage_messages[0]['content']


@pytest.mark.parametrize('old_answers', [
    ['打折后的价格'],
    ['打折后的价格', '原价和打折数', '打折后价格'],
])
def test_restored_discount_recovers_partial_answers_and_repairs_wrong_card(client, old_answers):
    sid = start(client)
    tutor = web_app._sessions[sid]
    tutor.question_text = '一件商品原价200元，打八折后多少钱？'
    tutor.card = tutor.question_card = {
        'id': None, 'knowledge_point': '百分数计算', 'formula': '200×80%=160',
        'easy_tip': '注意保留一位小数', 'is_temp': True,
    }
    tutor._enter_stage(agent.AgentState.STAGE1_UNDERSTAND)
    for answer in old_answers:
        tutor.stage_messages += [{'role': 'user', 'content': answer},
                                 {'role': 'assistant', 'content': '题里要我们求什么？[CONTINUE]'}]
    web_app._persist()
    web_app._sessions.clear()
    web_app._restore()
    snapshot = client.get(f'/api/sessions/{sid}').json()
    assert snapshot['card']['formula'] == '现价=原价×折扣率'
    assert snapshot['card']['knowledge_point'] == '折扣问题'
    assert not snapshot['card'].get('is_temp')
    with patch('agent.llm.chat_stream', side_effect=AssertionError('恢复后不能丢失已知和所求')):
        response = client.post('/api/replies', json={'session_id': sid, 'message': '原价和打折数'})
    assert response.status_code == 200
    assert web_app._sessions[sid].state == agent.AgentState.STAGE2_METHOD
    assert '原价和折扣' in response.json()['reply'] and '关系' in response.json()['reply']


def test_expired_session_is_removed(client):
    sid = start(client)
    web_app._activity[sid] = time.time() - web_app.SESSION_TTL - 1
    assert client.get(f"/api/sessions/{sid}").status_code == 404


@pytest.mark.parametrize('progress', ['method', 'expression', 'unit'])
def test_restart_restores_stage_and_calculation_progress(client, progress):
    sid = start(client)
    # 保留解释进度及是否需要专项练习，重启后继续用下一层提示。
    client.post('/api/replies', json={'session_id': sid, 'message': '没有'})
    client.post('/api/replies', json={'session_id': sid, 'message': '还是没明白'})
    with patch('agent.llm.chat_stream', return_value=iter(['题意清楚了\n[UNDERSTOOD]'])):
        client.post('/api/replies', json={'session_id': sid, 'message': '明白了'})
    if progress != 'method':
        with patch('agent.llm.chat_stream', return_value=iter(['方法正确\n[UNDERSTOOD]'])):
            client.post('/api/replies', json={'session_id': sid, 'message': '长乘宽，因为求长方形面积'})
        client.post('/api/replies', json={'session_id': sid, 'message': '12×8'})
        if progress == 'unit':
            client.post('/api/replies', json={'session_id': sid, 'message': '96'})
    before = copy.deepcopy(web_app._sessions[sid].__dict__)
    web_app._sessions.clear()
    web_app._activity.clear()
    web_app._restore()
    restored = web_app._sessions[sid]
    for field in ('state', 'stage_messages', 'stage_rounds', 'rounds', 'dialogue',
                  'compute_expression', 'compute_result_correct', 'help_counts', 'needs_practice',
                  'previous_stage_answer', 'teaching_state'):
        assert getattr(restored, field) == before[field]
    if progress != 'method':
        answer = '96平方米' if progress == 'expression' else '平方米'
        with patch('agent.llm.chat_stream', side_effect=AssertionError('恢复后继续本地核验')):
            response = client.post('/api/replies', json={'session_id': sid, 'message': answer})
        assert response.json()['finished']
        assert len(db.query_history()) == 1


def test_restart_restores_diagnosis_and_each_small_step_and_offers_same_topic(client):
    sid = start(client)
    for message in ('12×8=95平方米', '94'):
        response = client.post('/api/replies', json={'session_id': sid, 'message': message})
        assert not response.json()['finished']
    before = copy.deepcopy(web_app._sessions[sid].teaching_state)
    assert before['error_type'] == 'CALCULATION_ERROR'
    assert before['substep']['expected'] == '80'
    web_app._sessions.clear()
    web_app._restore()
    tutor = web_app._sessions[sid]
    assert tutor.teaching_state == before
    response = client.post('/api/replies', json={'session_id': sid, 'message': '80'}).json()
    assert '2×8' in response['reply']
    assert tutor.teaching_state['substep']['expected'] == '16'
    web_app._sessions.clear()
    web_app._restore()
    tutor = web_app._sessions[sid]
    response = client.post('/api/replies', json={'session_id': sid, 'message': '16'}).json()
    assert '回到原题' in response['reply']
    assert tutor.compute_expression == '12*8' and not tutor.compute_result_correct
    response = client.post('/api/replies', json={'session_id': sid, 'message': '96平方米'}).json()
    assert response['finished'] and response['practice_knowledge_id'] == 12
    assert 'teaching_state' not in response and 'error_type' not in response['reply']
    practice = client.post('/api/practice', json={'knowledge_id': response['practice_knowledge_id']}).json()
    assert practice['knowledge_id'] == 12 and practice['knowledge_point'] == '长方形面积'


def test_snapshot_without_new_teaching_state_still_restores(client):
    sid = start(client)
    path = web_app._session_file()
    data = json.loads(path.read_text(encoding='utf-8'))
    data[sid].pop('teaching_state')
    data[sid].pop('initial_student_msg')
    path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    web_app._sessions.clear()
    web_app._restore()
    assert web_app._sessions[sid].teaching_state['attempt_count'] == 0
    assert web_app._sessions[sid].state == agent.AgentState.STAGE1_UNDERSTAND
    snapshot = client.get(f'/api/sessions/{sid}').json()
    assert 'teaching_state' not in snapshot


def test_legacy_snapshot_restarts_with_reading_context(client):
    sid = start(client)
    path = web_app._session_file()
    data = json.loads(path.read_text(encoding='utf-8'))
    data[sid]['state'] = 'GUIDING'
    data[sid]['messages'] = [{'role': 'system', 'content': '旧的混合辅导提示词'}]
    data[sid].pop('stage_messages')
    path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    web_app._sessions.clear()
    web_app._restore()
    tutor = web_app._sessions[sid]
    assert tutor.state == agent.AgentState.STAGE1_UNDERSTAND
    assert '第一步：读懂题目' in tutor.stage_messages[0]['content']
    assert tutor.dialogue == data[sid]['dialogue']


def test_parallel_turn_is_rejected(client):
    sid = start(client)
    lock = web_app._turn_locks.setdefault(sid, threading.Lock())
    lock.acquire()
    try:
        assert client.post("/api/replies", json={"session_id": sid, "message": "96"}).status_code == 409
        assert client.post("/api/sessions/abort", json={"session_id": sid}).status_code == 409
    finally:
        lock.release()


def test_failed_reply_rolls_back_and_can_retry(client):
    sid = start(client)
    tutor = web_app._sessions[sid]
    old_messages = copy.deepcopy(tutor.stage_messages)
    old_dialogue = copy.deepcopy(tutor.dialogue)
    with patch("agent.llm.chat_stream", side_effect=llm.LLMError("服务暂时不可用")):
        response = client.post("/api/replies", json={"session_id": sid, "message": "96"})
    assert response.json()["retryable"]
    assert tutor.stage_messages == old_messages
    assert tutor.dialogue == old_dialogue
    assert tutor.rounds == 1
    with patch("agent.llm.chat_stream", return_value=iter(["题意正确[UNDERSTOOD]"])):
        result = client.post("/api/replies", json={"session_id": sid, "message": "明白了"}).json()
    assert not result['finished']
    assert tutor.state == agent.AgentState.STAGE2_METHOD
    with patch("agent.llm.chat_stream", return_value=iter(["方法正确[UNDERSTOOD]"])):
        result = client.post("/api/replies", json={"session_id": sid, "message": "长乘宽，因为要求长方形面积"}).json()
    assert not result['finished']
    with patch("agent.llm.chat_stream", return_value=iter(["结果正确[UNDERSTOOD]"])):
        assert client.post("/api/replies", json={"session_id": sid, "message": "12×8=96平方米"}).json()["finished"]
    assert len(db.query_history()) == 1


def test_whitespace_date_and_upload_validation(client, monkeypatch):
    assert client.post("/api/sessions", json={"question": "   "}).status_code == 422
    assert client.get("/api/history?date=2026-02-30").status_code == 422
    assert client.get("/api/history?qtype=不支持").status_code == 422
    monkeypatch.setattr(web_app, "MAX_UPLOAD_BYTES", 4)
    assert client.post("/api/ocr", files={"image": ("a.png", b"12345", "image/png")}).status_code == 413
    assert client.post("/api/ocr", files={"image": ("a.txt", b"1", "text/plain")}).status_code == 415


def test_ocr_temp_file_removed(client):
    paths = []
    def recognize(path):
        from pathlib import Path
        paths.append(Path(path))
        assert paths[0].exists()
        return "12 × 8"
    with patch("web_app.ocr.recognize", side_effect=recognize):
        response = client.post("/api/ocr", files={"image": ("a.png", b"image", "image/png")})
    assert response.json()["text"] == "12 × 8"
    assert not paths[0].exists()


def test_model_cannot_end_opening_without_student_answer(client):
    tutor = agent.TutorAgent()
    tutor.state = agent.AgentState.FORMULA_SHOWN
    with patch("agent.llm.chat_stream", return_value=iter(["答案是96[UNDERSTOOD]"])):
        list(tutor.begin_guiding())
    assert not tutor.finished


def test_explanation_is_archived(client):
    sid = start(client)
    tutor = web_app._sessions[sid]
    tutor.rounds = agent.config.MAX_GUIDE_ROUNDS - 1
    with patch("agent.llm.chat_stream", side_effect=[iter(["题意正确[UNDERSTOOD]"]),
               iter(["面积=12×8=96平方米。检查单位应为平方米。"])]):
        result = client.post("/api/replies", json={"session_id": sid, "message": "明白了"})
    assert result.json()["finished"]
    record = db.query_history()[0]
    assert record["understood"] == 0
    assert "96平方米" in json.loads(record["dialogue_log"])[-1]["content"]


def test_analysis_rejects_string_boolean():
    with patch("llm.ollama.chat", return_value={"message": {"content": '{"is_elementary_math":"false"}'}}):
        with pytest.raises(llm.LLMError):
            llm.analyze("题目", "候选")


def test_empty_reply_can_retry_and_abort_removes_snapshot(client):
    sid = start(client)
    with patch("agent.llm.chat_stream", return_value=iter([])):
        response = client.post("/api/replies", json={"session_id": sid, "message": "96"})
    assert response.json()["retryable"]
    assert web_app._sessions[sid].dialogue[-1]["role"] == "teacher"
    assert client.post("/api/sessions/abort", json={"session_id": sid}).status_code == 200
    web_app._restore()
    assert client.get(f"/api/sessions/{sid}").status_code == 404
    assert db.query_history() == []
