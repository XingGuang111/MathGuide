# -*- coding: utf-8 -*-
from unittest.mock import patch
import pytest
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


@pytest.mark.parametrize('kid,point,expected', [
    (26, '相遇问题', '行程应用题'),
    (27, '追及问题', '行程应用题'),
    (28, '火车过桥问题', '行程应用题'),
    (36, '利息问题', '百分数应用题'),
    (None, '鸡兔同笼问题', '计算题'),
])
def test_classic_word_problem_types_follow_the_matched_knowledge_point(tmp_path, kid, point, expected):
    tutor, path = _new_agent(tmp_path)
    tutor.question_text = '经典应用题测试题'
    tutor.question_type = '几何应用题'
    card = (db.get_formula_by_id(kid, path) if kid else
            {'id': None, 'knowledge_point': point, 'formula': '假设法', 'is_temp': True})
    tutor.card = tutor.question_card = card
    tutor.refresh_question_card()
    assert tutor.question_type == expected


def test_start_session_rejects_non_math(tmp_path):
    a, _ = _new_agent(tmp_path)
    with patch("agent.llm.analyze", return_value={
            "is_elementary_math": False, "knowledge_id": None,
            "question_type": None, "raw_knowledge": None}):
        r = a.start_session("帮我写一篇作文")
    assert r["ok"] is False
    assert a.state == agent_mod.AgentState.IDLE


@pytest.mark.parametrize('question', ['帮我写作文', '给我写首诗', '帮我润色作文', '请翻译这句话'])
def test_non_math_request_without_numbers_is_refused_instead_of_clarified(question):
    tutor = agent_mod.TutorAgent()
    with patch('agent.llm.analyze', side_effect=AssertionError('明确的文字请求无需分析数学题')):
        response = tutor.start_session(question)
    assert response['ok'] is False
    assert not response.get('clarify')
    assert '只能辅导小学数学' in response['message']
    assert tutor.state == agent_mod.AgentState.IDLE


def test_reply_continue_then_understood(tmp_path):
    """模拟三阶段推进：读题→找方法→计算，每步 UNDERSTOOD 进入下一阶段，最终归档。"""
    a, p = _new_agent(tmp_path)
    _start_ok(a)
    with patch("agent.llm.chat_stream", side_effect=[
        iter(["题意清楚了。[UNDERSTOOD]"]),
        iter(["方法正确。[UNDERSTOOD]"]),
    ]) as model:
        out0 = "".join(a.begin_guiding())
        assert "不明白" in out0
        model.assert_not_called()
        assert a.state == agent_mod.AgentState.STAGE1_UNDERSTAND

        # 第一次学生回答 → 第一阶段 UNDERSTOOD → 切到第二阶段
        out1 = "".join(a.reply("题目讲的是长方形花园，长12米宽8米，求面积"))
        assert a.finished is False
        assert a.state == agent_mod.AgentState.STAGE2_METHOD

        # 第二次学生回答 → 第二阶段 UNDERSTOOD → 切到第三阶段
        out2 = "".join(a.reply("用长乘宽，因为求的是长方形面积"))
        assert a.finished is False
        assert a.state == agent_mod.AgentState.STAGE3_COMPUTE

        # 第三次学生回答 → 第三阶段 UNDERSTOOD → 归档
        out3 = "".join(a.reply("12乘8等于96平方米"))
        assert a.finished is True
        assert model.call_count == 0  # 开场和已支持的正确题意、方法、计算均由代码核验。
    assert "[" not in out0 + out1 + out2 + out3
    assert len(a.dialogue) == 7
    assert a.state == agent_mod.AgentState.IDLE
    rows = db.query_history(db_path=p)
    assert len(rows) == 1
    assert rows[0]["understood"] == 1


def test_max_rounds_fallback(tmp_path):
    a, p = _new_agent(tmp_path)
    _start_ok(a)
    # 直接放到第三阶段，并把总轮数置为上限-1，本轮触发超限
    a._enter_stage(agent_mod.AgentState.STAGE3_COMPUTE)
    a.rounds = agent_mod.config.MAX_GUIDE_ROUNDS - 1
    a.stage_rounds = 0
    a.stage_messages = [a.stage_messages[0]]  # 保留 system prompt
    with patch("agent.calculation.rectangle", return_value=None), \
         patch("agent.llm.chat_stream", return_value=iter(["再想想？[CONTINUE]"])):
        out = "".join(a.reply("还是不会"))
    assert a.finished is True
    rows = db.query_history(db_path=p)
    assert rows[0]["understood"] == 0  # 超轮数兜底


def test_second_session_starts_clean(tmp_path):
    a, p = _new_agent(tmp_path)
    _start_ok(a)
    with patch("agent.llm.chat_stream", side_effect=[
        iter(["s1u[UNDERSTOOD]"]), iter(["s2u[UNDERSTOOD]"]),
    ]):
        "".join(a.begin_guiding())
        "".join(a.reply("我知道题了"))
        "".join(a.reply("面积=长×宽，因为求的是长方形面积"))
        "".join(a.reply("12乘8等于96平方米"))
    assert a.finished is True
    r2 = _start_ok(a)
    assert r2["ok"] is True
    assert a.rounds == 0
    assert a.dialogue == []
    assert a.finished is False
    assert a.stage_messages == []
    assert a.compute_expression == ""
    with patch("agent.llm.chat_stream", side_effect=[
        iter(["s1u[UNDERSTOOD]"]), iter(["s2u[UNDERSTOOD]"]),
    ]):
        "".join(a.begin_guiding())
        "".join(a.reply("我知道题了"))
        "".join(a.reply("面积=长×宽，因为求的是长方形面积"))
        "".join(a.reply("12×8=96平方米"))
    rows = db.query_history(db_path=p)
    assert len(rows) == 2
    assert "12×8=96平方米" in rows[0]["dialogue_log"]
    assert "12乘8等于96平方米" not in rows[0]["dialogue_log"]


@pytest.mark.parametrize('state,answer', [
    (agent_mod.AgentState.STAGE1_UNDERSTAND, '不知道'),
    (agent_mod.AgentState.STAGE1_UNDERSTAND, '还没懂'),
    (agent_mod.AgentState.STAGE1_UNDERSTAND, '好的'),
    (agent_mod.AgentState.STAGE2_METHOD, '我懂了'),
    (agent_mod.AgentState.STAGE2_METHOD, '面积=长加宽'),
    (agent_mod.AgentState.STAGE2_METHOD, '面积=长乘宽乘2'),
])
def test_model_cannot_pass_unclear_or_wrong_answer(tmp_path, state, answer):
    a, path = _new_agent(tmp_path)
    _start_ok(a)
    a._enter_stage(state)
    with patch('agent.prompts.build_understanding_hint', return_value=None), \
         patch('agent.llm.chat_stream', return_value=iter(['答对了！计算答案吧。[UNDERSTOOD]'])) as model:
        output = ''.join(a.reply(answer))
    assert a.state == state and not a.finished
    assert '答对了' not in output
    assert model.call_count == 1
    assert not db.query_history(db_path=path)


def test_transition_replaces_context_and_asks_one_question(tmp_path):
    a, _ = _new_agent(tmp_path)
    _start_ok(a)
    list(a.begin_guiding())
    with patch('agent.llm.chat_stream', return_value=iter(['题意没问题。你想用什么方法？[UNDERSTOOD]'])):
        output = ''.join(a.reply('明白了'))
    assert output.count('？') == 1
    assert len(a.stage_messages) == 2
    assert '第二步：找方法' in a.stage_messages[0]['content']
    assert all('第一步：读懂题目' not in m['content'] for m in a.stage_messages)


@pytest.mark.parametrize('state,answer,expected', [
    (agent_mod.AgentState.STAGE1_UNDERSTAND, '不懂面积是什么意思', '占地方'),
    (agent_mod.AgentState.STAGE2_METHOD, '不知道用什么方法', '数量关系'),
])
def test_uncertainty_gets_one_hint_without_model(tmp_path, state, answer, expected):
    a, _ = _new_agent(tmp_path)
    _start_ok(a)
    a._enter_stage(state)
    with patch('agent.llm.chat_stream', side_effect=AssertionError('常见疑问由代码控制节奏')):
        output = ''.join(a.reply(answer))
    assert expected in output
    assert output.count('？') == 1
    assert a.state == state and not a.finished


def test_confirmed_understanding_and_verified_method_need_no_model(tmp_path):
    a, _ = _new_agent(tmp_path)
    _start_ok(a)
    with patch('agent.llm.chat_stream', side_effect=AssertionError('明确确认和已核验方法由代码推进')):
        list(a.begin_guiding())
        list(a.reply('明白了，长12米宽8米，要求长方形的面积'))
        assert a.state == agent_mod.AgentState.STAGE2_METHOD
        list(a.reply('长乘宽，因为求长方形面积'))
        assert a.state == agent_mod.AgentState.STAGE3_COMPUTE


@pytest.mark.parametrize('response', [
    '长方形面积怎么计算？比如正方形边长4米，它的面积是多少？\n[CONTINUE]',
    '先算面积，再算周长吧。\n[CONTINUE]',
])
def test_reading_stage_rejects_computation_and_unrelated_topic(tmp_path, response):
    a, _ = _new_agent(tmp_path)
    _start_ok(a)
    list(a.begin_guiding())
    with patch('agent.llm.chat_stream', return_value=iter([response])):
        output = ''.join(a.reply('能解释一下面积这个词吗'))
    assert '占地方' in output
    assert '计算' not in output and '周长' not in output and '正方形' not in output
    assert a.state == agent_mod.AgentState.STAGE1_UNDERSTAND


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


def test_supplementary_card_cannot_change_goal_or_disable_verification(tmp_path):
    a, path = _new_agent(tmp_path)
    _start_ok(a)
    list(a.begin_guiding())
    with patch('agent.llm.chat_stream', return_value=iter(['先看一下另一个概念。\n[CARD:11]\n[CONTINUE]'])):
        list(a.reply('周长是什么意思'))
    assert a.card['id'] == 11
    with patch('agent.llm.chat_stream', side_effect=AssertionError('本题面积仍由代码核验')):
        list(a.reply('明白了'))
        assert '长方形面积=长×宽' in a.stage_messages[0]['content']
        list(a.reply('长乘宽，因为求面积'))
        list(a.reply('12×8=95平方米'))
        assert not a.finished
        list(a.reply('12×8=96平方米'))
    rows = db.query_history(db_path=path)
    assert len(rows) == 1 and rows[0]['knowledge_point'] == '长方形面积'


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
