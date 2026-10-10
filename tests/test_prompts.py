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
    assert "公式" not in p.split("规则")[0]  # 无公式段落
