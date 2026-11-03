# -*- coding: utf-8 -*-
import db
import knowledge
import pytest


def _setup(tmp_path):
    p = str(tmp_path / "t.db")
    db.init_db(p)
    return p


def test_load_candidates_format(tmp_path):
    p = _setup(tmp_path)
    s = knowledge.load_candidates(p)
    assert s.startswith("1. 加法交换律和结合律")
    assert "12. 长方形面积" in s
    assert "50. 加法式体重组" in s
    assert "\n" not in s  # 单行注入提示词


def test_get_by_id(tmp_path):
    p = _setup(tmp_path)
    row = knowledge.get_by_id(12, p)
    assert row["formula"] == "长方形面积=长×宽"
    assert knowledge.get_by_id(None, p) is None
    assert knowledge.get_by_id(0, p) is None


def test_resolve_prefers_id(tmp_path):
    p = _setup(tmp_path)
    row = knowledge.resolve(19, "不相关名字", p)
    assert row["knowledge_point"] == "圆的面积"


def test_resolve_alias_fallback(tmp_path):
    p = _setup(tmp_path)
    row = knowledge.resolve(999, "矩形面积", p)  # id 无效 → 别名兜底
    assert row["knowledge_point"] == "长方形面积"


def test_resolve_returns_none_when_no_match(tmp_path):
    p = _setup(tmp_path)
    assert knowledge.resolve(None, None, p) is None
    assert knowledge.resolve(999, "不存在的知识点", p) is None


@pytest.mark.parametrize('question,kid', [
    ('长方形花园长12米、宽8米，面积是多少？', 12),
    ('长方形操场长30米、宽20米，周长是多少？', 11),
    ('正方形地砖边长6厘米，面积是多少？', 14),
    ('三角形底12厘米，对应高8厘米，面积是多少？', 16),
    ('计算1/3+1/6，结果写成最简分数。', 8),
    ('学校到图书馆有2.5千米，换算成米是多少？', 39),
    ('骑车每小时行12千米，骑行3小时，一共行了多少千米？', 25),
    ('三次数学练习得分为80分、90分、100分，平均分是多少？', 47),
    ('2小时30分钟一共是多少分钟？', 43),
])
def test_explicit_topic_clues_choose_the_corresponding_card(tmp_path, question, kid):
    card = knowledge.match_question(question, _setup(tmp_path))
    assert card is not None and card['id'] == kid
