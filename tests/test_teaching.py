"""计划方案回归：按证据诊断、递进帮助、保存状态、保留正确中间步骤。"""
from copy import deepcopy
import json
from unittest.mock import patch

import pytest

import agent
import calculation
import config
import db
import llm
import teaching


QUESTION = '一件商品原价200元，打八折后多少钱？'


@pytest.fixture
def tutor(tmp_path):
    path = str(tmp_path / 'teaching.db')
    db.init_db(path)
    tutor = agent.TutorAgent(path)
    tutor.question_text = QUESTION
    tutor.card = tutor.question_card = db.get_formula_by_id(31, path)
    tutor.state = agent.AgentState.FORMULA_SHOWN
    list(tutor.begin_guiding())
    return tutor


@pytest.mark.parametrize('student,error,action', [
    ('200×0.8', 'UNKNOWN', 'GUIDE_CALCULATION'),
    ('200×0.8=180元', 'CALCULATION_ERROR', 'GUIDE_CALCULATION'),
    ('200×0.8=160', 'UNIT_ERROR', 'CHECK_UNIT'),
    ('200×0.8=160元', 'MASTERED', 'SUMMARIZE'),
    ('200×8=1600', 'EQUATION_ERROR', 'CHECK_REASONABLENESS'),
    ('200×0.8=1600', 'CALCULATION_ERROR', 'CHECK_REASONABLENESS'),
])
def test_calculation_diagnosis_distinguishes_equation_result_and_unit(student, error, action):
    work = teaching.assess_work(calculation.discount(QUESTION), student)
    assert (work.error_type, work.next_action) == (error, action)


def test_equation_error_does_not_turn_into_calculation_error_when_old_expression_exists():
    work = teaching.assess_work(calculation.discount(QUESTION), '200+0.8=160', '200*0.8')
    assert work.error_type == 'EQUATION_ERROR'


def test_known_numeric_work_skips_unnecessary_reading_and_method_questions(tutor):
    with (patch('agent.llm.diagnose', side_effect=AssertionError('本地能核验')),
          patch('agent.llm.chat_stream', side_effect=AssertionError('本地能核验'))):
        output = ''.join(tutor.reply('200×0.8=180元'))
    assert tutor.state == agent.AgentState.STAGE3_COMPUTE
    assert tutor.compute_expression == '200*0.8'
    assert '计算' in output or '检查' in output
    assert '八折就是' not in output and '求什么' not in output
    assert tutor.teaching_state['error_type'] == 'CALCULATION_ERROR'
    assert tutor.teaching_state['confirmed_steps'] == ['understand', 'method']


def test_numeric_work_can_also_be_given_in_method_stage(tutor):
    list(tutor.reply('明白了'))
    list(tutor.reply('200×0.8'))
    assert tutor.state == agent.AgentState.STAGE3_COMPUTE
    assert tutor.compute_expression == '200*0.8'


def test_wrong_expression_gets_reasonableness_check_without_reasking_reading(tutor):
    output = ''.join(tutor.reply('200×8=1600'))
    assert '多还是少' in output and '求什么' not in output
    assert tutor.teaching_state['error_type'] == 'EQUATION_ERROR'
    assert not tutor.teaching_state['confirmed_steps']
    assert not tutor.finished and not tutor.compute_expression


def test_complete_correct_work_is_not_forced_through_all_questions(tutor):
    output = ''.join(tutor.reply('200×0.8=160元'))
    assert tutor.finished
    assert '结果和单位都对' in output
    assert tutor.teaching_state['mastery'] == 'solved_current'
    assert db.query_history(db_path=tutor.db_path)[0]['understood'] == 1


def test_repeated_computation_errors_get_small_example_and_preserve_original_expression(tutor):
    list(tutor.reply('200×0.8=180'))
    second = ''.join(tutor.reply('170'))
    assert '10元' in second and '小例子' in second
    assert tutor.teaching_state['next_action'] == 'SIMPLIFY_NUMBERS'
    assert tutor.teaching_state['substep']['expected'] == '8'
    assert tutor.compute_expression == '200*0.8'
    assert '160' not in second
    followup = ''.join(tutor.reply('8'))
    assert '回到原题' in followup
    assert tutor.teaching_state['next_action'] == 'GUIDE_CALCULATION'
    assert not tutor.finished and not tutor.compute_result_correct
    list(tutor.reply('160'))
    assert tutor.teaching_state['error_type'] == 'UNIT_ERROR'
    assert tutor.teaching_state['consecutive_errors'] == 0
    list(tutor.reply('元'))
    assert tutor.finished and tutor.needs_practice


def test_original_full_answer_can_finish_while_small_example_is_pending(tutor):
    list(tutor.reply('200×0.8=180'))
    list(tutor.reply('170'))
    assert tutor.teaching_state['substep']
    list(tutor.reply('200×0.8=160元'))
    assert tutor.finished and tutor.teaching_state['substep'] is None


def test_small_step_is_demonstrated_after_two_misses_without_revealing_original_answer(tutor):
    list(tutor.reply('200×0.8=180'))
    list(tutor.reply('170'))
    first = ''.join(tutor.reply('7'))
    second = ''.join(tutor.reply('9'))
    assert '10元' in first
    assert '10×0.8=8' in second and '160' not in second
    assert tutor.teaching_state['substep'] is None
    assert not tutor.compute_result_correct and not tutor.finished


def test_units_do_not_restart_computation(tutor):
    list(tutor.reply('200×0.8=160'))
    output = ''.join(tutor.reply('不知道单位'))
    assert '单位' in output and '重新' not in output
    assert tutor.compute_result_correct and tutor.compute_expression == '200*0.8'
    assert tutor.teaching_state['error_type'] == 'UNIT_ERROR'
    list(tutor.reply('元'))
    assert tutor.finished


def test_concept_question_in_compute_keeps_confirmed_expression(tutor):
    list(tutor.reply('200×0.8'))
    output = ''.join(tutor.reply('八折是什么意思'))
    assert '每10元' in output
    assert tutor.teaching_state['error_type'] == 'CONCEPT_ERROR'
    assert tutor.compute_expression == '200*0.8'
    assert tutor.state == agent.AgentState.STAGE3_COMPUTE


@pytest.mark.parametrize('explanation_request', ['直接告诉我答案', '我想看完整过程', '请完整讲解'])
def test_explicit_explanation_is_archived_as_explained_not_mastered(tutor, explanation_request):
    output = ''.join(tutor.reply(explanation_request))
    assert '200×0.8=160元' in output and '专项练习' in output
    assert tutor.finished and tutor.teaching_state['mastery'] == 'explanation_seen'
    assert db.query_history(db_path=tutor.db_path)[0]['understood'] == 0


def test_declining_full_answer_does_not_authorize_explanation(tutor):
    assert not teaching.requests_explanation('不要直接告诉我答案')
    with patch('agent.llm.chat_stream', return_value=iter(['题目要求什么？[CONTINUE]'])):
        output = ''.join(tutor.reply('不要直接告诉我答案'))
    assert '160' not in output and not tutor.finished


def test_consecutive_concept_difficulties_escalate_and_eventually_explain(tutor):
    levels = []
    for index in range(6):
        output = ''.join(tutor.reply('八折不懂' if index == 0 else '还是没明白'))
        levels.append(tutor.teaching_state['teaching_level'])
        if tutor.finished:
            break
    assert levels[:3] == [2, 3, 4]
    assert levels[-1] == 7 and tutor.finished
    assert '160元' in output
    assert db.query_history(db_path=tutor.db_path)[0]['understood'] == 0


def test_negative_emotion_gets_support_and_a_smaller_step(tutor):
    list(tutor.reply('200×0.8'))
    output = ''.join(tutor.reply('我太笨了，数学好难'))
    assert output.startswith('没关系，') and output.count('？') == 1
    assert tutor.teaching_state['emotional_support']
    assert tutor.teaching_state['teaching_level'] >= 3
    assert tutor.compute_expression == '200*0.8'


def test_clear_difficulty_in_first_message_is_answered_without_asking_again(tutor):
    with patch('agent.llm.analyze', return_value=dict(is_elementary_math=True, knowledge_id=31,
               question_type='百分数应用题', raw_knowledge=None)):
        result = tutor.start_session(QUESTION + '我不知道八折是什么意思。')
    assert result['ok']
    output = ''.join(tutor.begin_guiding())
    assert '每10元' in output and '哪里' not in output
    assert tutor.teaching_state['error_type'] == 'CONCEPT_ERROR'


def test_student_who_knows_concept_but_not_method_is_not_reasked_concept(tutor):
    output = ''.join(tutor.reply('我知道八折，但不知道怎么算'))
    assert tutor.state == agent.AgentState.STAGE2_METHOD
    assert '数量关系' in output and '每10元' not in output


def test_complex_answer_gets_separate_model_diagnosis_and_hidden_state(tutor, monkeypatch):
    monkeypatch.setattr(config, 'ENABLE_MODEL_DIAGNOSIS', True)
    proposal = teaching.Diagnosis('READ_ERROR', 'BREAK_DOWN', 0.9, source='model')
    with (patch('agent.llm.diagnose', return_value=proposal) as diagnose,
          patch('agent.llm.chat_stream', return_value=iter(['先看题目最后一句，它要找什么？[CONTINUE]'])) as respond):
        output = ''.join(tutor.reply('我把两个价格弄混了'))
    diagnose.assert_called_once()
    assert tutor.teaching_state['source'] == 'model'
    assert tutor.teaching_state['attempt_count'] == 1
    assert 'BREAK_DOWN' in tutor.stage_messages[0]['content']
    assert '原价' in output and '实际付的钱' in output
    assert 'error_type' not in output and 'next_action' not in output


def test_model_diagnosis_alone_cannot_mark_mastered_or_reveal_answer(tutor, monkeypatch):
    monkeypatch.setattr(config, 'ENABLE_MODEL_DIAGNOSIS', True)
    with (patch('agent.llm.diagnose', return_value=teaching.Diagnosis('MASTERED', 'FULL_EXPLANATION', 1, source='model')),
          patch('agent.llm.chat_stream', return_value=iter(['我们核对最后一句，好吗？[CONTINUE]']))):
        output = ''.join(tutor.reply('我试试'))
    assert tutor.teaching_state['error_type'] == 'UNKNOWN'
    assert tutor.teaching_state['next_action'] == 'GIVE_HINT'
    assert not tutor.teaching_state['give_final_answer']
    assert not tutor.finished and '160' not in output


def test_diagnosis_failure_does_not_block_response(tutor, monkeypatch):
    monkeypatch.setattr(config, 'ENABLE_MODEL_DIAGNOSIS', True)
    with (patch('agent.llm.diagnose', side_effect=llm.LLMError('诊断不可用')),
          patch('agent.llm.chat_stream', return_value=iter(['先看题目最后一句，好吗？[CONTINUE]']))):
        output = ''.join(tutor.reply('我试试'))
    assert '最后一句' in output and not tutor.last_error
    assert tutor.teaching_state['source'] == 'rules'


def test_response_failure_rolls_back_diagnosis_attempts_and_context(tutor, monkeypatch):
    monkeypatch.setattr(config, 'ENABLE_MODEL_DIAGNOSIS', True)
    old = deepcopy(tutor.teaching_state)
    messages = deepcopy(tutor.stage_messages)
    with (patch('agent.llm.diagnose', return_value=teaching.Diagnosis('READ_ERROR', 'GIVE_HINT', 0.9, source='model')),
          patch('agent.llm.chat_stream', side_effect=llm.LLMError('超时'))):
        list(tutor.reply('我试试'))
    assert tutor.teaching_state == old and tutor.stage_messages == messages


@pytest.mark.parametrize('data', [[], {}, {'error_type': [], 'next_action': 'GIVE_HINT', 'confidence': 1},
    {'error_type': 'OTHER', 'next_action': 'GIVE_HINT', 'confidence': 1},
    {'error_type': 'READ_ERROR', 'next_action': 'GIVE_HINT', 'confidence': float('nan')},
    {'error_type': 'READ_ERROR', 'next_action': 'GIVE_HINT', 'confidence': True},
    {'error_type': 'READ_ERROR', 'next_action': 'GIVE_HINT', 'confidence': 2},
])
def test_invalid_diagnosis_is_rejected(data):
    with pytest.raises(ValueError):
        teaching.validate_diagnosis(data)


def test_llm_diagnosis_uses_short_json_request_and_no_user_facing_response():
    payload = dict(error_type='CALCULATION_ERROR', next_action='GUIDE_CALCULATION', confidence=0.9,
                   reason='已经列式，当前需要检查计算')
    with patch('llm.model_gateway.chat', return_value={'message': {'content': json.dumps(payload)}}) as chat:
        diagnosis = llm.diagnose(QUESTION, [], '200×0.8=180', teaching.initial_state())
    assert diagnosis.error_type == 'CALCULATION_ERROR'
    schema = chat.call_args.kwargs['format']
    assert schema['properties']['error_type']['enum'] == sorted(teaching.ERROR_TYPES)
    assert set(schema['properties']['next_action']['enum']) == set(teaching.ACTION_RULES)
    assert chat.call_args.kwargs['options']['num_predict'] <= 256


def test_bad_diagnosis_response_falls_back_without_retries():
    with patch('llm.model_gateway.chat', return_value={'message': {'content': '不是JSON'}}) as chat:
        assert llm.diagnose(QUESTION, [], '我试试', {}) is None
    chat.assert_called_once()


def test_diagnosis_timeout_falls_back():
    with patch('llm.model_gateway.chat', side_effect=TimeoutError('timeout')):
        assert llm.diagnose(QUESTION, [], '我试试', {}) is None
