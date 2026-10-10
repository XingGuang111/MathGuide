# -*- coding: utf-8 -*-
import db
import knowledge


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
