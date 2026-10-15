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
        return client.post("/api/sessions", json={"question": "长12米宽8米，面积是多少？"}).json()["session_id"]


def test_restart_restores_dialogue(client):
    sid = start(client)
    web_app._sessions.clear()
    web_app._activity.clear()
    web_app._restore()
    response = client.get(f"/api/sessions/{sid}")
    assert response.status_code == 200
    assert response.json()["dialogue"][0]["content"] == "面积公式是什么？"


def test_expired_session_is_removed(client):
    sid = start(client)
    web_app._activity[sid] = time.time() - web_app.SESSION_TTL - 1
    assert client.get(f"/api/sessions/{sid}").status_code == 404


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
    old_messages = list(tutor.messages)
    with patch("agent.llm.chat_stream", side_effect=llm.LLMError("服务暂时不可用")):
        response = client.post("/api/replies", json={"session_id": sid, "message": "96"})
    assert response.json()["retryable"]
    assert tutor.messages == old_messages
    assert tutor.rounds == 1
    with patch("agent.llm.chat_stream", return_value=iter(["正确[UNDERSTOOD]"])):
        assert client.post("/api/replies", json={"session_id": sid, "message": "96"}).json()["finished"]
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
    with patch("agent.llm.chat_stream", side_effect=[iter(["再想想[CONTINUE]"]),
               iter(["面积=12×8=96平方米。检查单位应为平方米。"])]):
        result = client.post("/api/replies", json={"session_id": sid, "message": "不会"})
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
