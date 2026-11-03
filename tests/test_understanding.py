"""读题重复追问的回归：合并多轮答案，同时拦住错误或不确定的回答。"""
from unittest.mock import patch

import pytest

import agent
import db
import llm


QUESTION = '一件商品原价200元，打八折后多少钱？'


def tutor_for(question=QUESTION, card=None):
    tutor = agent.TutorAgent()
    tutor.question_text = question
    tutor.card = tutor.question_card = card
    tutor.state = agent.AgentState.FORMULA_SHOWN
    list(tutor.begin_guiding())
    return tutor


@pytest.mark.parametrize('target', ['打折后的价格', '打折后价格', '现价', '现在要付多少钱'])
def test_target_then_known_advances_without_reasking_target(target):
    tutor = tutor_for()
    with patch('agent.llm.chat_stream', side_effect=AssertionError('明确题意用跨轮记录判断')):
        first = ''.join(tutor.reply(target))
        assert tutor.state == agent.AgentState.STAGE1_UNDERSTAND
        assert '原价和折扣' in first and '求什么' not in first
        second = ''.join(tutor.reply('原价和打折数'))
    assert tutor.state == agent.AgentState.STAGE2_METHOD
    assert '原价和折扣' in second and '关系' in second
    assert target in tutor.previous_stage_answer and '原价和打折数' in tutor.previous_stage_answer


def test_known_then_target_and_separate_known_values():
    tutor = tutor_for()
    with patch('agent.llm.chat_stream', side_effect=AssertionError('不能重复问已回答的信息')):
        first = ''.join(tutor.reply('原价200元'))
        assert '求什么' in first
        second = ''.join(tutor.reply('打折后的价格'))
        assert '折扣' in second and '原价和折扣' not in second
        list(tutor.reply('八折'))
    assert tutor.state == agent.AgentState.STAGE2_METHOD


@pytest.mark.parametrize('wrong', ['原价300元和八折', '原价200元和九折', '原价200元，十二折', '求便宜多少钱', '求原价'])
def test_wrong_conditions_or_goal_cannot_pass_even_if_model_would_pass(wrong):
    tutor = tutor_for()
    list(tutor.reply('打折后价格'))
    with patch('agent.llm.chat_stream', return_value=iter(['对了。[UNDERSTOOD]'])):
        reply = ''.join(tutor.reply(wrong))
    assert tutor.state == agent.AgentState.STAGE1_UNDERSTAND
    assert '对了' not in reply
    list(tutor.reply('原价200元，八折，求打折后的价格'))
    assert tutor.state == agent.AgentState.STAGE2_METHOD


def test_uncertain_information_and_teacher_hints_are_not_student_evidence():
    tutor = tutor_for()
    list(tutor.reply('打折后的价格'))
    list(tutor.reply('原价和折扣我还不懂'))
    assert tutor.state == agent.AgentState.STAGE1_UNDERSTAND
    assert set(tutor._reading_progress().facts) == {'target'}
    list(tutor.reply('原价200元'))
    assert tutor.state == agent.AgentState.STAGE1_UNDERSTAND
    list(tutor.reply('八折'))
    assert tutor.state == agent.AgentState.STAGE2_METHOD


def test_repeated_question_does_not_count_as_understood():
    tutor = tutor_for()
    with patch('agent.llm.chat_stream', side_effect=AssertionError('重复题目不需要重新调用模型')):
        output = ''.join(tutor.reply(QUESTION))
    assert '求什么' in output and '就是' not in output
    assert not tutor._reading_progress().facts
    list(tutor.reply('打折后的价格'))
    assert tutor.state == agent.AgentState.STAGE1_UNDERSTAND
    list(tutor.reply('原价和打折数'))
    assert tutor.state == agent.AgentState.STAGE2_METHOD


def test_reposted_question_does_not_pass_guard():
    tutor = tutor_for()
    assert not tutor._can_advance(QUESTION, None)


def test_failed_model_turn_is_not_counted_in_reading_progress():
    tutor = tutor_for()
    before = list(tutor.stage_messages)
    with patch('agent.llm.chat_stream', side_effect=llm.LLMError('超时')):
        list(tutor.reply('我想先看看题意'))
    assert tutor.stage_messages == before
    assert not tutor._reading_progress().facts


def test_rectangle_can_combine_conditions_with_goal():
    tutor = tutor_for('长方形长12米宽8米，面积是多少？', {
        'id': 12, 'knowledge_point': '长方形面积', 'formula': '长方形面积=长×宽', 'easy_tip': '',
    })
    with patch('agent.llm.chat_stream', side_effect=AssertionError('合并已知条件')):
        list(tutor.reply('面积'))
        list(tutor.reply('长12米'))
        last = ''.join(tutor.reply('宽8米'))
    assert tutor.state == agent.AgentState.STAGE2_METHOD
    assert '边长' in last and '利用' in last


@pytest.mark.parametrize('knowledge_id', [None, 12, 32])
def test_discount_uses_local_general_formula_even_when_analysis_misses(tmp_path, knowledge_id):
    path = str(tmp_path / 'card.db')
    db.init_db(path)
    tutor = agent.TutorAgent(path)
    with patch('agent.llm.analyze', return_value={'is_elementary_math': True,
               'knowledge_id': knowledge_id, 'raw_knowledge': None, 'question_type': '计算题'}), \
         patch('agent.llm.generate_formula', side_effect=AssertionError('已有折扣知识卡')):
        result = tutor.start_session(QUESTION)
    assert result['ok'] and result['question_type'] == '百分数应用题'
    assert result['card']['knowledge_point'] == '折扣问题'
    assert result['card']['formula'] == '现价=原价×折扣率'
    assert '80%=0.8' in result['card']['easy_tip']
    assert '160' not in result['card']['formula'] and '保留' not in result['card']['easy_tip']
    assert not result['card'].get('is_temp')
