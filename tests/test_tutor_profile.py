import json
from unittest.mock import patch

import pytest

import agent
import config
import db
import llm
import prompts
import tutor_profile


def _paths(tmp_path, monkeypatch):
    for setting, name in (('TUTOR_SYSTEM_PATH', 'system.txt'), ('TUTOR_EXAMPLES_PATH', 'examples.jsonl'),
                          ('TUTOR_DIALOGUE_PATH', 'dialogue.md')):
        path = tmp_path / name
        path.write_text('', encoding='utf-8')
        monkeypatch.setattr(config, setting, path)


def test_three_documents_are_loaded_and_examples_do_not_cross_stage_or_topic():
    sections, examples = tutor_profile.load_profile()
    assert set(sections) == {'global', 'understand', 'method', 'compute'}
    assert len(examples) >= 40
    assert any(item['id'] == 'dialogue-discount-example' for item in examples)
    reading = tutor_profile.build_context('understand', '一件商品原价200元，打八折后多少钱？', '还是没懂')
    assert '棒棒糖' in reading
    assert '160' not in reading and '面积' not in reading
    assert '8×3' not in reading
    area = tutor_profile.build_context('understand', '长方形长12米宽8米，面积是多少？', '还是没懂')
    assert '棒棒糖' not in area and '200' not in area
    assert '小方格' in area


def test_average_score_is_not_treated_as_sharing_objects():
    question = '三次数学练习得分为80分、90分、100分，平均分是多少？'
    assert tutor_profile.topic_for(question) == 'average'
    assert '小朋友' not in prompts.build_stage_opening('understand', question)
    assert all(item['term'] != '平均分' for item in tutor_profile.term_examples(question, '不明白'))


def test_area_opening_does_not_invent_a_rectangle_for_other_shapes():
    assert '长方形' not in prompts.build_stage_opening('understand', '三角形底12厘米，高8厘米，面积是多少？')


def test_user_edits_take_effect_on_next_reply_without_restarting(tmp_path, monkeypatch):
    _paths(tmp_path, monkeypatch)
    config.TUTOR_SYSTEM_PATH.write_text('[global]\n只用一句话问学生。\n[understand]\n先听学生。', encoding='utf-8')
    item = {'id': 'read', 'stage': 'understand', 'topics': ['general'], 'action': 'opening',
            'messages': [{'role': 'user', 'content': '题目'}, {'role': 'assistant', 'content': '哪个词没读懂？'}]}
    config.TUTOR_EXAMPLES_PATH.write_text(json.dumps(item, ensure_ascii=False), encoding='utf-8')
    tutor = agent.TutorAgent()
    tutor.question_text = '班上有36名学生，要分组。'
    tutor.state = agent.AgentState.FORMULA_SHOWN
    assert '哪个词没读懂' in ''.join(tutor.begin_guiding())
    config.TUTOR_SYSTEM_PATH.write_text('[global]\n新规则：一次只说一句，耐心等待学生。\n[understand]\n先听学生。', encoding='utf-8')
    with patch('agent.llm.chat_stream', return_value=iter(['我们先说题目里要做什么？\n[CONTINUE]'])) as model:
        list(tutor.reply('题目里说学生要分组'))
    assert '新规则' in model.call_args.args[0][0]['content']


def test_invalid_jsonl_line_warns_and_does_not_break_valid_entries(tmp_path, monkeypatch, caplog):
    _paths(tmp_path, monkeypatch)
    valid = {'id': 'valid', 'stage': 'method', 'topics': ['area'],
             'messages': [{'role': 'user', 'content': '用什么方法？'}, {'role': 'assistant', 'content': '你觉得边长有什么关系？'}]}
    config.TUTOR_EXAMPLES_PATH.write_text('bad json\n' + json.dumps(valid, ensure_ascii=False), encoding='utf-8')
    _, examples = tutor_profile.load_profile()
    assert [item['id'] for item in examples] == ['valid']
    assert '已跳过' in caplog.text


def test_jsonl_template_and_markdown_edits_both_change_runtime_context(tmp_path, monkeypatch):
    _paths(tmp_path, monkeypatch)
    row = {'id': 'opening', 'stage': 'method', 'topics': ['general'], 'action': 'opening',
           'messages': [{'role': 'user', 'content': '懂了'}, {'role': 'assistant', 'content': '先想数量关系吧？'}]}
    config.TUTOR_EXAMPLES_PATH.write_text(json.dumps(row, ensure_ascii=False), encoding='utf-8')
    assert prompts.build_stage_opening('method', '长方形面积') == '先想数量关系吧？'
    row['messages'][1]['content'] = '换个问法：题目的数量可以怎样联系？'
    config.TUTOR_EXAMPLES_PATH.write_text(json.dumps(row, ensure_ascii=False), encoding='utf-8')
    assert '换个问法' in prompts.build_stage_opening('method', '长方形面积')
    fragment = ('<!-- tutor-example: {"id":"dialogue-new","stage":"method","topics":["area"]} -->\n'
                '```text\n学生：从哪里开始？\n老师：先看看每排有几个格子，好吗？\n```')
    config.TUTOR_DIALOGUE_PATH.write_text(fragment, encoding='utf-8')
    assert '每排有几个格子' in tutor_profile.build_context('method', '长方形面积')
    assert '每排有几个格子' not in tutor_profile.build_context('understand', '长方形面积')
    assert '每排有几个格子' not in tutor_profile.build_context('method', '一件商品打八折')


@pytest.mark.parametrize('discount,per_one,percent', [('八折', '0.8', '80'), ('九五折', '0.95', '95'), ('7.5折', '0.75', '75')])
def test_discount_examples_use_actual_discount(discount, per_one, percent):
    hint = prompts.build_understanding_hint(f'一件商品原价200元，打{discount}后多少钱？', '还是没懂', 2)
    assert per_one + '元' in hint and percent + '%' in hint
    assert '160' not in hint and hint.count('？') == 1


def test_repeated_confusion_progresses_and_completion_suggests_practice(tmp_path):
    path = str(tmp_path / 'tutor.db')
    db.init_db(path)
    tutor = agent.TutorAgent(path)
    with patch('agent.llm.analyze', return_value={'is_elementary_math': True, 'knowledge_id': 12,
               'question_type': '几何应用题', 'raw_knowledge': None}):
        tutor.start_session('长方形长12米宽8米，面积是多少？')
    with patch('agent.llm.chat_stream', side_effect=AssertionError('这些明确的疑问与计算走代码控制')):
        list(tutor.begin_guiding())
        first = ''.join(tutor.reply('没有'))
        second = ''.join(tutor.reply('还是没明白'))
        assert first != second and '小例子' in second
        assert tutor.needs_practice
        list(tutor.reply('明白了'))
        list(tutor.reply('长乘宽，因为求面积'))
        result = ''.join(tutor.reply('12×8=96平方米'))
    assert tutor.finished and '专项练习' in result
    assert '专项练习' in db.query_history(db_path=path)[0]['dialogue_log']


def test_failed_reply_keeps_help_progress_and_exact_context(tmp_path):
    tutor = agent.TutorAgent()
    tutor.question_text = '一个班有36名学生，分组后每组多少人？'
    tutor.state = agent.AgentState.FORMULA_SHOWN
    list(tutor.begin_guiding())
    old_messages = list(tutor.stage_messages)
    with patch('agent.llm.chat_stream', side_effect=llm.LLMError('暂时失败')):
        list(tutor.reply('还是没读懂'))
    assert tutor.stage_messages == old_messages
    assert tutor.help_counts == {} and not tutor.needs_practice


@pytest.mark.parametrize('message', ['我没说我懂了', '明白了，不过还是不会', '我懂了但是不确定'])
def test_negative_confirmation_does_not_advance(message):
    tutor = agent.TutorAgent()
    tutor.question_text = '一件商品原价200元，打八折后多少钱？'
    tutor.state = agent.AgentState.FORMULA_SHOWN
    list(tutor.begin_guiding())
    with patch('agent.llm.chat_stream', return_value=iter(['正确\n[UNDERSTOOD]'])):
        list(tutor.reply(message))
    assert tutor.state == agent.AgentState.STAGE1_UNDERSTAND


def test_original_discount_example_can_finish_with_separate_result_and_unit(tmp_path):
    path = str(tmp_path / 'discount.db')
    db.init_db(path)
    tutor = agent.TutorAgent(path)
    tutor.question_text = '一件商品原价200元，打八折后多少钱？'
    tutor.state = agent.AgentState.FORMULA_SHOWN
    with patch('agent.llm.chat_stream', side_effect=AssertionError('普通打折题不能依赖模型判分')):
        list(tutor.begin_guiding())
        first = ''.join(tutor.reply('没有'))
        second = ''.join(tutor.reply('还是有点没明白'))
        third = ''.join(tutor.reply('能再换个例子吗'))
        assert '每10元' in first and '棒棒糖' in second and '一支笔' in third
        list(tutor.reply('明白了，是要算现在付多少钱'))
        list(tutor.reply('原价乘0.8，因为八折是原价的80%'))
        assert tutor.state == agent.AgentState.STAGE3_COMPUTE
        list(tutor.reply('200*0.8'))
        assert not tutor.finished
        error = ''.join(tutor.reply('16元'))
        assert not tutor.finished and '检查' in error
        list(tutor.reply('160'))
        assert not tutor.finished
        final = ''.join(tutor.reply('元'))
    assert tutor.finished
    assert '80%' in final and '专项练习' in final
    assert len(db.query_history(db_path=path)) == 1


def test_specific_discount_question_is_answered_without_repeating_generic_hint():
    tutor = agent.TutorAgent()
    tutor.question_text = '一件商品原价200元，打八折后多少钱？'
    tutor._enter_stage(agent.AgentState.STAGE2_METHOD)
    with patch('agent.llm.chat_stream', side_effect=AssertionError('明确的折扣追问使用资料解释')):
        output = ''.join(tutor.reply('为什么八折要乘0.8，不是乘8呢？'))
    assert '80%' in output and '0.8倍' in output
    assert tutor.state == agent.AgentState.STAGE2_METHOD


def test_only_matching_topic_can_load_discount_clarification():
    assert prompts.build_method_clarification('长方形长8米宽3米，面积是多少？', '为什么要乘8？') is None
