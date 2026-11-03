"""Regression for question loops hidden by encouragement and repeated small examples."""
from unittest.mock import patch

import pytest

import agent
import calculation
import config
import db
import llm
import prompts
import reply_guard
import scaffolding
import teaching


@pytest.mark.parametrize('previous,candidate', [
    ('面积的意思已经解释过了。你觉得这道题要用什么方法？',
     '没关系，试着回忆一下。你想到什么公式来求面积？'),
    ('保留你已经写出的算式。计算结果是多少？',
     '我们一步一步来，只看最后一步。你算出的结果是多少？'),
    ('你能说说平均分是什么意思吗？', '先别着急。你觉得平均分表示什么？'),
    ('题目求什么？', '把最后一句读一遍。题目要我们找哪个量？'),
])
def test_encouragement_does_not_disguise_same_question(previous, candidate):
    assert reply_guard.repeated(candidate, [previous])


@pytest.mark.parametrize('previous,candidate', [
    ('你觉得这道题要用什么方法？', '平均分表示每份一样多。把总数分成相等的几份，该用哪种运算？'),
    ('6÷2等于多少？', '24÷6等于多少？'),
    ('数值已经算对了，单位是什么？', '一条边用厘米量，面积是小方格的个数，该用厘米还是平方厘米？'),
    ('题目求什么？', '题目给出的长度是多少？'),
])
def test_new_support_or_a_new_target_is_allowed(previous, candidate):
    assert not reply_guard.repeated(candidate, [previous])


def test_small_step_error_gets_a_hint_instead_of_same_question():
    state = teaching.initial_state()
    scaffolding._set_substep(state, '先看小例子：6颗糖平均分给2个人，每人分到几颗？', '6÷2', 3)
    reply = scaffolding.reply_to_substep(state, '4')
    assert '每人分到几颗' not in reply
    assert '2' in reply and '6' in reply and reply.count('？') == 1
    assert state['substep']['tries'] == 1
    assert '3颗' not in reply


def test_internal_duplicate_sentences_are_collapsed_without_losing_numbers():
    assert reply_guard.clean('先保留这个算式。先保留这个算式。计算结果是多少？') == '先保留这个算式。计算结果是多少？'
    assert reply_guard.clean('6÷2等于多少？24÷6等于多少？') == '6÷2等于多少？24÷6等于多少？'


def test_retry_is_shown_rejected_candidate_and_remains_in_current_stage():
    tutor = agent.TutorAgent()
    tutor.question_text = '长方形长12米宽8米，面积是多少？'
    tutor.card = tutor.question_card = {'formula':'面积=长×宽','knowledge_point':'长方形面积','easy_tip':''}
    tutor._enter_stage(agent.AgentState.STAGE2_METHOD)
    tutor._record_teacher('面积的意思已经解释过了。你觉得这道题要用什么方法？')
    duplicate = '没关系，试着回忆一下。你想到什么公式来求面积？'
    with patch('agent.llm.chat_stream', return_value=iter(['先想一排的格数与排数，它们该怎样合起来？\n[CONTINUE]'])) as model:
        body, explained = tutor._avoid_repetition(duplicate, '我试试', calculation.rectangle(tutor.question_text, tutor.card), False)
    assert model.called and not explained
    assert duplicate in str(model.call_args.args[0])
    assert tutor.state == agent.AgentState.STAGE2_METHOD and not tutor.finished
    assert '格数' in body


def test_compute_fallback_keeps_confirmed_expression_and_result():
    tutor = agent.TutorAgent()
    tutor.question_text = '长方形长12米宽8米，面积是多少？'
    tutor._enter_stage(agent.AgentState.STAGE3_COMPUTE)
    tutor.compute_expression = '12*8'
    tutor.compute_result_correct = True
    hint = tutor._current_hint('我试试')
    assert '单位' in hint and '重' not in hint and '算式' not in hint


def test_repeated_emotion_support_is_not_prefixed_twice():
    tutor = agent.TutorAgent()
    tutor.state = agent.AgentState.STAGE1_UNDERSTAND
    tutor.question_text = '一个班有36名学生，要分组，每组多少人？'
    with patch('agent.llm.chat_stream', return_value=iter(['没关系，我们先看题目最后一句，好吗？\n[CONTINUE]'])):
        reply = ''.join(tutor.reply('我太笨了'))
    assert '没关系，没关系' not in reply


def test_every_supported_student_turn_is_analyzed_before_model_reply(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'ENABLE_MODEL_DIALOGUE', True)
    path = str(tmp_path / 'model-flow.db')
    db.init_db(path)
    tutor = agent.TutorAgent(path)
    tutor.question_text = '长方形长12米宽8米，面积是多少？'
    tutor.card = tutor.question_card = db.get_formula_by_id(12, path)
    tutor.session_id = 'model-flow'
    tutor._enter_stage(agent.AgentState.STAGE3_COMPUTE)
    calls = []

    def analyze(question, history, student, state):
        calls.append(('analysis', student, state['program_check']))
        return teaching.Diagnosis('UNKNOWN', 'GIVE_HINT', reason='结合学生刚写的内容继续')

    replies = iter(['你把长和宽相乘了，接着算这一步会得到多少？',
                    '数值已经有了，这块地的大小该用什么单位表示？',
                    '这次从列式到单位都核对好了，你已经完成这道面积题了。'])

    def compose(messages):
        calls.append(('reply', messages))
        return next(replies)

    with patch('agent.llm.diagnose', side_effect=analyze), patch('agent.llm.compose_reply', side_effect=compose):
        first = ''.join(tutor.reply('12×8'))
        second = ''.join(tutor.reply('96'))
        third = ''.join(tutor.reply('平方米'))
    assert [call[0] for call in calls] == ['analysis', 'reply'] * 3
    assert first.startswith('你把') and '单位' in second and tutor.finished
    assert '数量关系' not in third
    assert db.query_history(db_path=path)[0]['understood'] == 1
    assert calls[0][2]['expression'] == '12*8'


def test_failed_analysis_does_not_emit_template_or_advance(monkeypatch):
    monkeypatch.setattr(config, 'ENABLE_MODEL_DIALOGUE', True)
    tutor = agent.TutorAgent()
    tutor.question_text = '长方形长12米宽8米，面积是多少？'
    tutor._enter_stage(agent.AgentState.STAGE3_COMPUTE)
    with patch('agent.llm.diagnose', return_value=None), patch('agent.llm.compose_reply') as compose:
        output = ''.join(tutor.reply('12×8'))
    assert '重试' in output and tutor.last_error and not tutor.finished
    compose.assert_not_called()
    assert not tutor.dialogue and not tutor.compute_expression


def test_rejected_generated_reply_is_retried_without_false_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'ENABLE_MODEL_DIALOGUE', True)
    path = str(tmp_path / 'rejected.db'); db.init_db(path)
    tutor = agent.TutorAgent(path)
    tutor.question_text = '长方形长12米宽8米，面积是多少？'
    tutor.card = tutor.question_card = db.get_formula_by_id(12, path)
    tutor._enter_stage(agent.AgentState.STAGE3_COMPUTE)
    analysis = teaching.Diagnosis('UNKNOWN', 'GIVE_HINT')
    with patch('agent.llm.diagnose', return_value=analysis), patch('agent.llm.compose_reply', return_value='答案是999平方米。') as compose:
        output = ''.join(tutor.reply('12×8'))
    assert compose.call_count == 2 and '重试' in output
    assert not db.query_history(db_path=path) and not tutor.finished
    assert not tutor.compute_expression and not tutor.dialogue


def test_final_unit_is_not_claimed_missing_when_student_supplied_it(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'ENABLE_MODEL_DIALOGUE', True)
    path = str(tmp_path / 'final-unit.db'); db.init_db(path)
    tutor = agent.TutorAgent(path)
    tutor.session_id = 'final-unit'
    tutor.question_text = '长方形长12米宽8米，面积是多少？'
    tutor.card = tutor.question_card = db.get_formula_by_id(12, path)
    tutor._enter_stage(agent.AgentState.STAGE3_COMPUTE)
    analysis = teaching.Diagnosis('UNKNOWN', 'GIVE_HINT')
    with patch('agent.llm.diagnose', return_value=analysis), patch('agent.llm.compose_reply', side_effect=[
            '你的计算正确，只是最后忘记加上单位哦！', '算式、结果和平方米这个单位都核对好了，这题完成了。']) as compose:
        reply = ''.join(tutor.reply('12×8=96平方米'))
    assert compose.call_count == 2 and '忘记' not in reply and tutor.finished
    assert db.query_history(db_path=path)[0]['understood'] == 1


def test_question_cleaning_removes_only_redundant_confirmations():
    assert reply_guard.clean('这里该用什么单位？160这个数要带什么单位？') == '这里该用什么单位？160这个数要带什么单位？'
    assert reply_guard.clean('你记得这个过程了吗？现在检查一下小数点的位置，好吗？') == '现在检查一下小数点的位置，好吗？'


def test_unit_prompt_keeps_student_analysis_and_history():
    messages = prompts.build_reply_messages('24颗糖平均分给6人，每人几颗？',
        [{'role': 'teacher', 'content': '你准备怎么检查除法？'},
         {'role': 'student', 'content': '24÷6=4'}], 'compute',
        {'error_type': 'UNIT_ERROR', 'next_action': 'CHECK_UNIT', 'expected_unit': '颗'},
        {'reason': '学生已纠正除法，尚未写单位'}, '数值已正确，只补单位')
    assert '24÷6=4' in messages[1]['content']
    assert '学生已纠正除法' in messages[1]['content']
    assert '你准备怎么检查除法' in messages[1]['content']
    assert '提醒学生补上“颗”' not in messages[1]['content']


def test_naming_formula_and_using_formula_are_different_questions():
    previous = '知道长12米宽8米，你认为用哪个公式来求面积？'
    assert not reply_guard.repeated('把长12米和宽8米代入公式，列出怎样的算式呢？', [previous])
    assert not reply_guard.repeated('将长12米和宽8米代入公式，会得到什么样的数值呢？', [previous])


def test_same_amount_is_a_valid_concept_explanation():
    tutor = agent.TutorAgent()
    tutor.question_text = '24颗糖平均分给6人，每人几颗？'
    tutor.dialogue = [{'role': 'student', 'content': '不明白'}]
    tutor.teaching_state['error_type'] = 'CONCEPT_ERROR'
    candidate = '平均分的意思是每个人分得同样多，能让一个人多拿一些吗？'
    with patch('agent.llm.compose_reply', return_value=candidate) as compose:
        result = tutor._natural_reply('平均分表示每份一样多。', teaching.Diagnosis(), agent.AgentState.STAGE1_UNDERSTAND)
    assert result == candidate and compose.call_count == 1


def test_unit_focus_removes_only_the_already_answered_quantity_question():
    assert reply_guard.focus_on_unit('每个人有多少颗糖？单位是什么？') == '单位是什么？'
    assert reply_guard.focus_on_unit('数值已经算对了。每个人有几颗？还需要什么单位？') == '数值已经算对了。还需要什么单位？'
    assert reply_guard.focus_on_unit('每个人有几颗？') == '每个人有几颗？'
