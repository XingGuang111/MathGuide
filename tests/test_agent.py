# -*- coding: utf-8 -*-
from unittest.mock import patch
import db
import agent as agent_mod


def _new_agent(tmp_path):
    p = str(tmp_path / "t.db")
    db.init_db(p)
    return agent_mod.TutorAgent(db_path=p), p


ANALYZE_OK = {"is_elementary_math": True, "knowledge_id": 12,
              "question_type": "几何应用题", "raw_knowledge": None}


def _start_ok(a):
    with patch("agent.llm.analyze", return_value=ANALYZE_OK):
        return a.start_session("长方形花园长12米宽8米，面积是多少？")


def test_start_session_success(tmp_path):
    a, _ = _new_agent(tmp_path)
    r = _start_ok(a)
    assert r["ok"] is True
    assert r["card"]["formula"] == "长方形面积=长×宽"
    assert r["question_type"] == "几何应用题"
    assert a.state == agent_mod.AgentState.FORMULA_SHOWN


def test_start_session_rejects_non_math(tmp_path):
    a, _ = _new_agent(tmp_path)
    with patch("agent.llm.analyze", return_value={
            "is_elementary_math": False, "knowledge_id": None,
            "question_type": None, "raw_knowledge": None}):
        r = a.start_session("帮我写一篇作文")
    assert r["ok"] is False
    assert a.state == agent_mod.AgentState.IDLE


def test_reply_continue_then_understood(tmp_path):
    a, p = _new_agent(tmp_path)
    _start_ok(a)
    replies = iter(["那我们想想面积怎么算？[CONTINUE]",
                    "对啦！你自己算出来了！[UNDERSTOOD]"])
    with patch("agent.llm.chat_stream", side_effect=lambda msgs: iter([next(replies)])):
        out1 = "".join(a.reply("不知道"))
        assert "[CONTINUE]" not in out1   # 标记不外泄
        assert a.finished is False
        out2 = "".join(a.reply("12乘8等于96"))
        assert "[UNDERSTOOD]" not in out2
        assert a.finished is True
    assert a.state == agent_mod.AgentState.IDLE  # 归档后回 IDLE
    rows = db.query_history(db_path=p)
    assert len(rows) == 1
    assert rows[0]["understood"] == 1
    assert "12乘8等于96" in rows[0]["dialogue_log"]


def test_max_rounds_fallback(tmp_path):
    a, p = _new_agent(tmp_path)
    _start_ok(a)
    a.state = agent_mod.AgentState.GUIDING
    a.rounds = agent_mod.config.MAX_GUIDE_ROUNDS  # 直接置为上限
    with patch("agent.llm.chat_stream", return_value=iter(["再想想？[CONTINUE]"])):
        out = "".join(a.reply("还是不会"))
    assert a.finished is True
    rows = db.query_history(db_path=p)
    assert rows[0]["understood"] == 0  # 超轮数兜底


def test_abort(tmp_path):
    a, p = _new_agent(tmp_path)
    _start_ok(a)
    a.abort()
    assert a.state == agent_mod.AgentState.IDLE
    assert db.query_history(db_path=p) == []  # 放弃不归档
