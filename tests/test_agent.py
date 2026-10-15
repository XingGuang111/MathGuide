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
        out2 = "".join(a.reply("12乘8等于96平方米"))
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


def test_second_session_starts_clean(tmp_path):
    a, p = _new_agent(tmp_path)
    _start_ok(a)
    with patch("agent.llm.chat_stream", return_value=iter(["对啦！[UNDERSTOOD]"])):
        "".join(a.reply("12乘8等于96平方米"))
    assert a.finished is True  # 会话 1 已结束
    r2 = _start_ok(a)
    assert r2["ok"] is True
    assert a.rounds == 0
    assert a.dialogue == []
    assert a.finished is False
    with patch("agent.llm.chat_stream", return_value=iter(["答对了！[UNDERSTOOD]"])):
        "".join(a.reply("12×8=96平方米"))
    rows = db.query_history(db_path=p)
    assert len(rows) == 2
    assert "12乘8等于96" in rows[1]["dialogue_log"]
    assert "12×8=96平方米" in rows[0]["dialogue_log"]
    assert "12乘8等于96" not in rows[0]["dialogue_log"]  # 最新会话不混入会话 1


def test_abort(tmp_path):
    a, p = _new_agent(tmp_path)
    _start_ok(a)
    a.abort()
    assert a.state == agent_mod.AgentState.IDLE
    assert db.query_history(db_path=p) == []  # 放弃不归档


# ---------- 新增：AI 生成轨 + 动态换卡 + 超纲提醒 ----------

ANALYZE_UNMATCHED = {"is_elementary_math": True, "knowledge_id": None,
                     "question_type": "几何应用题", "raw_knowledge": None}


def test_start_session_falls_back_to_generate_formula(tmp_path):
    a, _ = _new_agent(tmp_path)
    gen_card = {"id": None, "knowledge_point": "圆的面积", "formula": "S=πr²",
                "easy_tip": "半径²是r×r", "grade": "六年级上册", "is_temp": True}
    with patch("agent.llm.analyze", return_value=ANALYZE_UNMATCHED), \
         patch("agent.llm.generate_formula", return_value={"kind": "card", "card": gen_card}):
        r = a.start_session("一个圆的半径是5cm，求面积")
    assert r["ok"] is True
    assert a.card == gen_card
    assert a.card["is_temp"] is True


def test_start_session_discards_mismatched_local_card_and_uses_generate(tmp_path):
    """analyze 强行匹配相近候选时（鸡兔同笼→长方形面积），plausible 校验应弃用并走生成轨"""
    a, _ = _new_agent(tmp_path)
    # analyze 返回 id=12 长方形面积，但题目里没有「长/方/形」任何一个字
    mismatched = {"is_elementary_math": True, "knowledge_id": 12,
                  "question_type": "几何应用题", "raw_knowledge": None}
    gen_card = {"id": None, "knowledge_point": "鸡兔同笼", "formula": "假设法",
                "easy_tip": "先假设全是鸡", "grade": "五年级上册", "is_temp": True}
    with patch("agent.llm.analyze", return_value=mismatched), \
         patch("agent.llm.generate_formula", return_value={"kind": "card", "card": gen_card}):
        r = a.start_session("笼子里有鸡和兔一共 8 只，腿一共 26 条，鸡兔各有几只？")
    assert r["ok"] is True
    assert a.card == gen_card  # 弃用了乱选的长方形面积卡


def test_start_session_keeps_plausible_local_card(tmp_path):
    """analyze 选对的本地卡（特征字在题目里），plausible 校验应放行"""
    a, _ = _new_agent(tmp_path)
    # 用默认 ANALYZE_OK：id=12 长方形面积，题目里有「长方形」
    r = _start_ok(a)
    assert r["ok"] is True
    assert a.card["id"] == 12  # 本地卡未被弃用


def test_start_session_returns_clarify_when_question_incomplete(tmp_path):
    a, _ = _new_agent(tmp_path)
    clarify = {"kind": "clarify", "question": "题目里没有半径，能补上吗？"}
    with patch("agent.llm.analyze", return_value=ANALYZE_UNMATCHED), \
         patch("agent.llm.generate_formula", return_value=clarify):
        r = a.start_session("圆的面积")
    assert r["ok"] is False
    assert r["clarify"] is True
    assert "半径" in r["message"]
    assert a.state == agent_mod.AgentState.IDLE


def test_start_session_generate_formula_not_math(tmp_path):
    a, _ = _new_agent(tmp_path)
    with patch("agent.llm.analyze", return_value=ANALYZE_UNMATCHED), \
         patch("agent.llm.generate_formula", return_value={"kind": "not_math"}):
        # 含数字避免触发"输入不完整"启发式
        r = a.start_session("解 x=1 时的微积分")
    assert r["ok"] is False
    assert "不是小学数学" in r["message"]


def test_reply_switches_card_on_card_tag(tmp_path):
    a, _ = _new_agent(tmp_path)
    _start_ok(a)
    assert a.card["id"] == 12
    # patch calculation.rectangle 让 verified 为空，强制走 LLM 分支以验证标记解析
    with patch("agent.calculation.rectangle", return_value=None), \
         patch("agent.llm.chat_stream",
               return_value=iter(["你混淆了，周长是另一张卡片\n[CARD:11]\n[CONTINUE]"])):
        out = "".join(a.reply("那周长怎么算？"))
    assert a.card["id"] == 11
    assert "[CARD:" not in out  # 标记不外泄
    assert "[CONTINUE]" not in out


def test_reply_ignores_invalid_card_id(tmp_path):
    a, _ = _new_agent(tmp_path)
    _start_ok(a)
    original = a.card
    with patch("agent.calculation.rectangle", return_value=None), \
         patch("agent.llm.chat_stream", return_value=iter(["继续加油\n[CARD:999]\n[CONTINUE]"])):
        out = "".join(a.reply("嗯"))
    assert a.card is original  # 未切换
    assert "[CARD:" not in out


def test_reply_captures_alert_and_pop_clears(tmp_path):
    a, _ = _new_agent(tmp_path)
    _start_ok(a)
    # 学生消息命中超纲关键词「一元二次」时，后端启发式直接置 last_alert
    with patch("agent.calculation.rectangle", return_value=None), \
         patch("agent.llm.chat_stream", return_value=iter(["咱们先把这道题做完\n[CONTINUE]"])):
        out = "".join(a.reply("我还想知道一元二次方程怎么解"))
    assert "ALERT" not in out
    assert "更高年级" in a.pop_alert()
    assert a.pop_alert() is None  # 一次性


def test_reply_no_alert_for_in_scope_message(tmp_path):
    a, _ = _new_agent(tmp_path)
    _start_ok(a)
    with patch("agent.calculation.rectangle", return_value=None), \
         patch("agent.llm.chat_stream", return_value=iter(["继续\n[CONTINUE]"])):
        "".join(a.reply("我不会做这道题"))
    assert a.pop_alert() is None  # 普通回答不触发提醒
