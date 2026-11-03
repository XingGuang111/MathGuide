# -*- coding: utf-8 -*-
import prompts


def test_analyze_prompt_contains_contract():
    p = prompts.build_analyze_prompt("长方形面积题", "1. 加法 | 12. 长方形面积")
    assert "长方形面积题" in p            # 题干注入
    assert "12. 长方形面积" in p          # 候选列表注入
    assert "is_elementary_math" in p      # JSON 契约
    assert "knowledge_id" in p
    assert "question_type" in p
    for qt in ["计算题", "几何应用题", "行程应用题", "百分数应用题", "单位换算题", "平均数应用题"]:
        assert qt in p                     # 题型枚举完整


def test_tutor_prompt_rules_and_tags():
    card = {"knowledge_point": "长方形面积", "formula": "长方形面积=长×宽", "easy_tip": "区分周长面积"}
    p = prompts.build_tutor_system_prompt("题目文本", card)
    assert "题目文本" in p
    assert "长方形面积=长×宽" in p
    assert "区分周长面积" in p
    assert prompts.TAG_CONTINUE in p
    assert prompts.TAG_UNDERSTOOD in p
    assert "严禁" in p or "禁止" in p      # 不许直接给答案的铁律
    assert "一个" in p                     # 每次只问一个问题


def test_tutor_prompt_without_card():
    p = prompts.build_tutor_system_prompt("题目文本", None)
    assert "题目文本" in p
    assert "【核心公式】" not in p
    assert "【学生易错点】" not in p


def test_stage_prompts_keep_separate_goals():
    question = "一件衣服原价80元，打八折，现价是多少？"
    card = {"knowledge_point": "折扣", "formula": "现价=原价×折扣", "easy_tip": "八折是80%"}
    first = prompts.build_stage1_prompt(question)
    second = prompts.build_stage2_prompt(question, card)
    third = prompts.build_stage3_prompt(question, card)
    assert "第一步：读懂题目" in first
    assert card["formula"] not in first
    assert "第二步：找方法" in second and card["formula"] in second
    assert "第三步：列式计算" in third and card["formula"] in third
    for prompt in (first, second, third):
        assert question in prompt
        assert "面积" not in prompt  # 折扣题不能被提示词里的无关例子带偏。
        assert prompts.TAG_CONTINUE in prompt and prompts.TAG_UNDERSTOOD in prompt


def test_understanding_hint_explains_only_the_requested_word():
    question = '一件衣服原价80元，打八折，现价是多少？'
    hint = prompts.build_understanding_hint(question, '不懂八折是什么意思')
    assert '每10元' in hint and '8元' in hint
    assert '面积' not in hint and '64' not in hint
    assert hint.count('？') == 1
    assert prompts.build_understanding_hint('班上有36个学生，要分组', '不知道') is None
