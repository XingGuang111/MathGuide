"""Regression for complete work being reasked and repeated fallback/model questions."""
from unittest.mock import patch

import pytest

import agent
import db


@pytest.mark.parametrize('kid,question,answer', [
    (14, '正方形地砖边长6厘米，面积是多少？', '6×6=36平方厘米'),
    (8, '计算1/3+1/6，结果写成最简分数。', '1/3+1/6=2/6+1/6=3/6=1/2'),
    (39, '学校到图书馆有2.5千米，换算成米是多少？', '2.5×1000=2500米'),
    (25, '骑车每小时行12千米，骑行3小时，一共行了多少千米？', '12×3=36千米'),
    (47, '三次数学练习得分为80分、90分、100分，平均分是多少？', '(80+90+100)÷3=270÷3=90分'),
])
def test_complete_work_finishes_without_model_reasking(tmp_path, kid, question, answer):
    path=str(tmp_path/'progress.db'); db.init_db(path)
    tutor=agent.TutorAgent(path)
    tutor.question_text=question; tutor.session_id='checked'
    tutor.card=tutor.question_card=db.get_formula_by_id(kid,path)
    tutor._enter_stage(agent.AgentState.STAGE3_COMPUTE)
    with patch('agent.llm.chat_stream', return_value=iter(['单位是对的吗？\n[CONTINUE]'])):
        reply=''.join(tutor.reply(answer))
    assert tutor.finished
    assert '？' not in reply
    assert db.query_history(db_path=path)[0]['understood']==1


def test_repeating_model_and_fallback_cannot_keep_the_same_question(tmp_path):
    path=str(tmp_path/'loop.db'); db.init_db(path)
    tutor=agent.TutorAgent(path)
    tutor.question_text='两个班共有48人，要分组，每组多少人？'
    tutor.session_id='loop'; tutor.card={'id':None,'knowledge_point':'分组','formula':'每组人数=总人数÷组数','easy_tip':''}
    tutor._enter_stage(agent.AgentState.STAGE2_METHOD)
    outputs=[]
    with patch('agent.llm.chat_stream', side_effect=lambda messages: iter(['你觉得这道题要用什么方法？\n[CONTINUE]'])):
        for _ in range(4):
            if tutor.finished: break
            outputs.append(''.join(tutor.reply('我试试')).strip())
    assert len(set(outputs))==len(outputs)
    assert not db.query_history(db_path=path) or db.query_history(db_path=path)[0]['understood']==0


@pytest.mark.parametrize('stage', [agent.AgentState.STAGE1_UNDERSTAND, agent.AgentState.STAGE2_METHOD,
                                   agent.AgentState.STAGE3_COMPUTE])
@pytest.mark.parametrize('student', ['我试试','我再想想','继续'])
def test_waiting_for_student_is_not_evidence_of_understanding(stage, student):
    tutor=agent.TutorAgent()
    tutor.state=stage
    assert not tutor._can_advance(student, None)


def test_model_cannot_mark_waiting_student_as_mastered(tmp_path):
    path=str(tmp_path/'waiting.db'); db.init_db(path)
    tutor=agent.TutorAgent(path)
    tutor.question_text='一个班有36名学生，要分组，每组有多少人？'
    tutor.session_id='waiting'; tutor.card={'id':None,'knowledge_point':'分组','formula':'每组人数=总人数÷组数','easy_tip':''}
    tutor._enter_stage(agent.AgentState.STAGE1_UNDERSTAND)
    with patch('agent.llm.chat_stream', side_effect=lambda messages: iter(['你明白了吗？\n[UNDERSTOOD]'])):
        for _ in range(5):
            if tutor.finished: break
            output=''.join(tutor.reply('我试试'))
    assert tutor.finished and '没有给出分成几组' in output
    assert db.query_history(db_path=path)[0]['understood']==0
    assert not any(word in output for word in ('答对了','说清楚了','方法找对'))


def test_waiting_student_is_not_praised_even_if_model_says_understood():
    tutor=agent.TutorAgent()
    tutor.state=agent.AgentState.STAGE1_UNDERSTAND
    with patch('agent.llm.chat_stream', return_value=iter(['对，这一步说清楚了。\n[UNDERSTOOD]'])):
        output=''.join(tutor.reply('我试试'))
    assert '可以，先想一小步' in output
    assert '说清楚了' not in output and not tutor.finished
