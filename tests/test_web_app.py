# -*- coding: utf-8 -*-
from unittest.mock import patch

from fastapi.testclient import TestClient

import db
import web_app


def _client(tmp_path, monkeypatch):
    path = str(tmp_path / "web.db")
    db.init_db(path)
    monkeypatch.setattr(web_app.config, "DB_PATH", path)
    web_app._sessions.clear()
    return TestClient(web_app.app), path


def test_index_and_health(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    with patch("web_app.llm.check_health", return_value=None):
        assert client.get("/").status_code == 200
        data = client.get("/api/health").json()
    assert data["ok"] is True


def test_session_reply_and_archive(tmp_path, monkeypatch):
    client, path = _client(tmp_path, monkeypatch)
    analyzed = {"is_elementary_math": True, "knowledge_id": 12,
                "question_type": "几何应用题", "raw_knowledge": None}
    replies = iter(["先想一想面积公式是什么？[CONTINUE]", "答对了！[UNDERSTOOD]"])
    with patch("agent.llm.analyze", return_value=analyzed), \
         patch("agent.llm.chat_stream", side_effect=lambda messages: iter([next(replies)])):
        started = client.post("/api/sessions", json={"question": "长方形长12米宽8米，面积是多少？"})
        assert started.status_code == 200
        body = started.json()
        assert body["card"]["knowledge_point"] == "长方形面积"
        assert "CONTINUE" not in body["reply"]
        answered = client.post("/api/replies", json={
            "session_id": body["session_id"], "message": "12乘8等于96平方米"
        })
    assert answered.status_code == 200
    assert answered.json()["finished"] is True
    assert len(db.query_history(db_path=path)) == 1


def test_missing_session_returns_404(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    response = client.post("/api/replies", json={"session_id": "missing", "message": "答案"})
    assert response.status_code == 404


def test_history_decodes_dialogue(tmp_path, monkeypatch):
    client, path = _client(tmp_path, monkeypatch)
    db.save_record({"session_id": "s", "record_date": "2026-10-12", "question_type": "计算题",
                    "question_text": "1+1", "knowledge_point": "加法", "formula": "1+1=2",
                    "dialogue_log": '[{"role":"student","content":"2"}]', "understood": 1}, path)
    rows = client.get("/api/history").json()
    assert rows[0]["dialogue"][0]["content"] == "2"
    assert "dialogue_log" not in rows[0]


def test_sessions_returns_clarify_instead_of_error(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    unmatched = {"is_elementary_math": True, "knowledge_id": None,
                 "question_type": "几何应用题", "raw_knowledge": None}
    clarify = {"kind": "clarify", "question": "题目里没有半径，能补上吗？"}
    with patch("agent.llm.analyze", return_value=unmatched), \
         patch("agent.llm.generate_formula", return_value=clarify):
        r = client.post("/api/sessions", json={"question": "圆的面积"})
    assert r.status_code == 200
    body = r.json()
    assert body["clarify"] is True
    assert "半径" in body["message"]
    assert "session_id" not in body  # clarify 不创建 session


def test_replies_response_includes_card_and_alert(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    analyzed = {"is_elementary_math": True, "knowledge_id": 12,
                "question_type": "几何应用题", "raw_knowledge": None}
    opening = iter(["先想一想[CONTINUE]"])
    with patch("agent.llm.analyze", return_value=analyzed), \
         patch("agent.llm.chat_stream", side_effect=lambda msgs: iter([next(opening)])):
        started = client.post("/api/sessions", json={"question": "长方形长12米宽8米，面积？"})
    sid = started.json()["session_id"]
    # 第二轮：学生追问超纲内容（命中关键词），同时 AI 输出 [CARD:11] 标记
    # patch calculation.rectangle 让走 LLM 分支以验证标记管道
    with patch("agent.calculation.rectangle", return_value=None), \
         patch("agent.llm.chat_stream",
               return_value=iter(["我们换个角度\n[CARD:11]\n[CONTINUE]"])):
        replied = client.post("/api/replies", json={"session_id": sid, "message": "我还想知道一元二次方程"})
    body = replied.json()
    assert "更高年级" in body["alert"]
    assert body["card"]["id"] == 11
    assert "CARD:" not in body["reply"]
