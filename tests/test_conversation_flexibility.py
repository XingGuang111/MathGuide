"""按题目组织开场，平均分解释，以及协议异常后的安全续聊。"""
import json
from unittest.mock import patch

import pytest

import agent
import config
import calculation
import db
import knowledge
import llm
import prompts
import tutor_profile


QUESTION = '老师有24颗糖，平均分给6个小朋友，每个人有几颗？'


def make_tutor(question=QUESTION):
    tutor = agent.TutorAgent()
    tutor.question_text = question
    tutor.state = agent.AgentState.FORMULA_SHOWN
    return tutor


def test_openings_follow_problem_instead_of_one_fixed_script():
    questions = [QUESTION, '商品原价200元，打八折后多少钱？',
                 '长方形长12米宽8米，面积是多少？', '汽车开了2小时，走了多少千米？']
    replies = [prompts.build_stage_opening('understand', q) for q in questions]
    assert len(set(replies)) == len(questions)
    assert '平均分' in replies[0] and '打折' in replies[1] and '面积' in replies[2]
    assert all(r.count('？') == 1 for r in replies)


def test_enabled_opening_uses_local_model_language(monkeypatch):
    monkeypatch.setattr(config, 'ENABLE_MODEL_OPENING', True)
    tutor = make_tutor()
    with patch('agent.llm.opening', return_value='糖要分给6个小朋友，这里的“平均分”你是怎么理解的？') as model:
        reply = ''.join(tutor.begin_guiding())
    model.assert_called_once()
    assert '怎么理解' in reply and not tutor.finished
    assert '[CONTINUE]' not in reply and tutor.rounds == 1


@pytest.mark.parametrize('bad', ['每人4颗，知道了吗？', '先用24除以6，结果是多少？',
    '老师：平均分清楚吗？', '你懂了吗？[UNDERSTOOD]', '先想面积，好吗？',
    '题目里除了数字和对象，你还理解了什么？', None])
def test_bad_model_opening_falls_back_without_answer_or_internal_tags(monkeypatch, bad):
    monkeypatch.setattr(config, 'ENABLE_MODEL_OPENING', True)
    tutor = make_tutor()
    with patch('agent.llm.opening', return_value=bad):
        reply = ''.join(tutor.begin_guiding())
    assert '平均分' in reply and '4颗' not in reply and '[UNDERSTOOD]' not in reply


@pytest.mark.parametrize('bad', [
    '给学生的开场问句：长方形的长和宽你理解了吗？',
    '开场问句：面积这个词有没有不明白的地方？',
    '参考问句：长方形的长和宽你理解了吗？',
])
def test_model_opening_narration_is_not_shown_to_student(monkeypatch, bad):
    monkeypatch.setattr(config, 'ENABLE_MODEL_OPENING', True)
    question = '长方形长12米宽8米，面积是多少？'
    tutor = make_tutor(question)
    with patch('agent.llm.opening', return_value=bad):
        reply = ''.join(tutor.begin_guiding()).strip()
    assert reply == prompts.build_stage_opening('understand', question)
    assert '问句' not in reply and not tutor.finished


def test_average_sharing_confusion_explains_and_then_changes_example():
    tutor = make_tutor()
    list(tutor.begin_guiding())
    with patch('agent.llm.chat_stream', side_effect=AssertionError('明确的平均分疑问应有本地解释')):
        first = ''.join(tutor.reply('不明白'))
        second = ''.join(tutor.reply('还是没明白'))
        third = ''.join(tutor.reply('还是不懂'))
    assert '一样多' in first and '平均数' not in first
    assert '小例子' in second and '6颗糖' in second
    assert '一轮' in third and len({first, second, third}) == 3
    assert '4颗' not in first+second+third
    assert tutor.help_counts['understand:equal_share'] == 3
    assert not tutor.last_error and tutor.state == agent.AgentState.STAGE1_UNDERSTAND
    assert tutor_profile.topic_for(QUESTION) == 'equal_share'


def test_format_failure_stays_on_current_stage_and_keeps_student_turn():
    tutor = make_tutor('一个班有36名学生，分组后每组多少人？')
    list(tutor.begin_guiding())
    with patch('agent.llm.chat_stream', side_effect=llm.LLMFormatError('格式不符合约定')):
        reply = ''.join(tutor.reply('不明白'))
    assert '已知条件' in reply and '开小差' not in reply and '格式' not in reply
    assert reply.count('？') == 1  # 不把开场已经问过的所求换句话再问。
    assert tutor.stage_messages[-2] == {'role': 'user', 'content': '不明白'}
    assert not tutor.last_error and not tutor.finished


def test_first_message_with_difficulty_does_not_generate_another_opening(monkeypatch):
    monkeypatch.setattr(config, 'ENABLE_MODEL_OPENING', True)
    tutor = make_tutor()
    with (patch('agent.llm.analyze', return_value=dict(is_elementary_math=True, knowledge_id=None,
             question_type='计算题', raw_knowledge=None)),
          patch('agent.llm.generate_formula', return_value={'kind':'card', 'card':{
             'id':None, 'knowledge_point':'平均分', 'formula':'每份数=总数÷份数', 'is_temp':True}}),
          patch('agent.llm.opening', side_effect=AssertionError('学生已经说明疑问'))):
        assert tutor.start_session(QUESTION+'不明白平均分。')['ok']
        reply = ''.join(tutor.begin_guiding())
    assert '一样多' in reply and '4颗' not in reply


def test_opening_json_has_no_student_grading_status():
    with patch('llm._opening_client.chat', return_value={'message':{'content':json.dumps({'reply':'你觉得平均分是什么意思？'})}}) as model:
        assert llm.opening(QUESTION, '参考问句') == '你觉得平均分是什么意思？'
    kwargs = model.call_args.kwargs
    assert kwargs['format'] == 'json'
    assert '[UNDERSTOOD]' not in kwargs['messages'][0]['content']


def test_opening_timeout_does_not_block_fallback():
    with patch('llm._opening_client.chat', side_effect=TimeoutError()):
        assert llm.opening(QUESTION, '参考问句') is None


@pytest.mark.parametrize('expression,complete', [('24÷6=4颗', True), ('24/6=4颗', True),
    ('24除以6等于4颗', True), ('6÷24=4颗', False), ('24÷6=5颗', False), ('24÷6=4', False)])
def test_equal_share_checks_equation_result_and_unit(expression, complete):
    work = calculation.equal_share(QUESTION)
    assert work.guide(expression)[1] is complete


@pytest.mark.parametrize('question', [
    QUESTION.replace('24','25'), QUESTION.replace('6个','0个'), QUESTION+'还剩2颗。',
    '24颗糖平均分给6人，求还剩几颗？', QUESTION.replace('几颗','几个'),
    '有24颗糖，分给6个小朋友，每个人有几颗？',
    '老师有24颗糖，平均分给6个小朋友，每人先吃1颗，现在每人有几颗？',
])
def test_equal_share_does_not_guess_on_unsupported_conditions(question):
    assert calculation.equal_share(question) is None


def test_sharing_completion_keeps_prior_work_and_does_not_ask_to_recalculate(tmp_path):
    path = str(tmp_path/'sharing.db')
    db.init_db(path)
    tutor = agent.TutorAgent(path)
    with patch('agent.llm.analyze', return_value=dict(is_elementary_math=True, knowledge_id=12,
        question_type='几何应用题', raw_knowledge=None)):
        result = tutor.start_session(QUESTION)
    assert result['card']['formula'] == '每份数=总数÷份数'
    assert result['card']['id'] is None  # 不能导向47号的平均得分练习。
    assert result['question_type'] == '计算题'
    list(tutor.begin_guiding())
    with patch('agent.llm.chat_stream', side_effect=AssertionError('支持的平均分用程序核验')):
        list(tutor.reply('不明白'))
        reply = ''.join(tutor.reply('24÷6=5颗'))
        assert '除法' in reply and not tutor.finished
        reply = ''.join(tutor.reply('6'))
        assert '小例子' in reply
        reply = ''.join(tutor.reply('3颗'))
        assert '回到原题' in reply
        reply = ''.join(tutor.reply('4'))
        assert '单位' in reply and not tutor.finished
        reply = ''.join(tutor.reply('颗'))
    assert tutor.finished and '单位都对' in reply
    assert db.query_history(db_path=path)[0]['understood'] == 1


def test_supported_sharing_card_can_repair_old_generated_formula(tmp_path):
    path = str(tmp_path/'cards.db'); db.init_db(path)
    tutor = agent.TutorAgent(path); tutor.question_text = QUESTION
    tutor.card = tutor.question_card = {'is_temp':True,'formula':'24÷6','knowledge_point':'平均数'}
    tutor.refresh_question_card()
    assert tutor.card['knowledge_point'] == '平均分'
    assert tutor.card['formula'] == '每份数=总数÷份数'


def test_restored_sharing_session_answers_confusion_instead_of_starting_again(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import web_app
    monkeypatch.setattr(config, 'DB_PATH', str(tmp_path/'restore.db'))
    web_app._sessions.clear(); web_app._activity.clear(); web_app._turn_locks.clear()
    try:
        with TestClient(web_app.app) as client:
            with patch('agent.llm.analyze', return_value=dict(is_elementary_math=True, knowledge_id=12,
                       question_type='几何应用题', raw_knowledge=None)):
                started = client.post('/api/sessions', json={'question':QUESTION}).json()
            sid = started['session_id']
            web_app._sessions.clear(); web_app._activity.clear(); web_app._restore()
            snapshot = client.get('/api/sessions/'+sid).json()
            assert len(snapshot['dialogue']) == 1
            with patch('agent.llm.chat_stream', side_effect=AssertionError('恢复后的疑问走本地解释')):
                response = client.post('/api/replies', json={'session_id':sid, 'message':'不明白'}).json()
            assert '一样多' in response['reply']
            assert not response['retryable'] and not response['finished']
            assert '我们先读题' not in response['reply']
    finally:
        web_app._sessions.clear(); web_app._activity.clear(); web_app._turn_locks.clear()
