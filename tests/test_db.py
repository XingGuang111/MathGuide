# -*- coding: utf-8 -*-
import db
import config
import sqlite3
import json
import pytest


def test_init_db_creates_tables_and_imports_formulas(tmp_path):
    p = str(tmp_path / "t.db")
    db.init_db(p)
    rows = db.get_all_formulas(p)
    assert len(rows) == 50
    assert rows[11]["knowledge_point"] == "长方形面积"
    assert "formula" in rows[11] and "easy_tip" in rows[11]


def test_init_db_is_idempotent(tmp_path):
    p = str(tmp_path / "t.db")
    db.init_db(p)
    db.init_db(p)  # 第二次调用不应重复导入
    assert len(db.get_all_formulas(p)) == 50


def test_get_formula_by_id(tmp_path):
    p = str(tmp_path / "t.db")
    db.init_db(p)
    row = db.get_formula_by_id(12, p)
    assert row["knowledge_point"] == "长方形面积"
    assert db.get_formula_by_id(999, p) is None


def test_find_formula_by_alias_exact(tmp_path):
    p = str(tmp_path / "t.db")
    db.init_db(p)
    row = db.find_formula_by_alias("矩形面积", p)  # "长方形面积"的别名
    assert row["knowledge_point"] == "长方形面积"


def test_find_formula_by_alias_fuzzy(tmp_path):
    p = str(tmp_path / "t.db")
    db.init_db(p)
    row = db.find_formula_by_alias("圆的周长公式", p)  # 精确查不到，LIKE 命中"圆的周长"
    assert row["knowledge_point"] == "圆的周长"


def test_save_and_query_record(tmp_path):
    p = str(tmp_path / "t.db")
    db.init_db(p)
    rid = db.save_record({
        "session_id": "s1",
        "record_date": "2026-10-08",
        "question_type": "几何应用题",
        "question_text": "长方形花园长12米宽8米",
        "knowledge_point": "长方形面积",
        "formula": "长方形面积=长×宽",
        "dialogue_log": '[{"role":"student","content":"96"}]',
        "understood": 1,
    }, p)
    assert isinstance(rid, int)
    rows = db.query_history(date="2026-10-08", db_path=p)
    assert len(rows) == 1
    assert rows[0]["session_id"] == "s1"
    assert db.query_history(qtype="几何应用题", db_path=p)[0]["id"] == rid
    assert db.query_history(qtype="行程应用题", db_path=p) == []


def test_weak_stats(tmp_path):
    p = str(tmp_path / "t.db")
    db.init_db(p)
    for i, u in enumerate([1, 0, 0]):
        db.save_record({
            "session_id": f"s{i}", "record_date": "2026-10-08",
            "question_type": "几何应用题", "question_text": "t",
            "knowledge_point": "长方形面积", "formula": "f",
            "dialogue_log": "[]", "understood": u,
        }, p)
    db.save_record({
        "session_id": "s9", "record_date": "2026-10-08",
        "question_type": "计算题", "question_text": "t",
        "knowledge_point": "乘法分配律", "formula": "f",
        "dialogue_log": "[]", "understood": 0,
    }, p)
    stats = db.weak_stats(p)
    assert stats[0]["knowledge_point"] == "长方形面积"
    assert stats[0]["total"] == 3
    assert stats[0]["not_understood"] == 2


def test_compressed_record_and_legacy_history_are_lossless(tmp_path):
    p = str(tmp_path / "compressed.db")
    db.init_db(p)
    log = json.dumps([{"role": "teacher", "content": "请想想长和宽的关系。" * 30}] * 12, ensure_ascii=False)
    record = dict(session_id="compressed", record_date="2026-10-13",
                  question_type="几何应用题", question_text="面积题", knowledge_point="长方形面积",
                  formula="面积=长×宽", dialogue_log=log, understood=0)
    rid = db.save_record(record, p)
    with sqlite3.connect(p) as conn:
        packed = conn.execute("SELECT dialogue_log FROM study_record WHERE id=?", (rid,)).fetchone()[0]
        assert isinstance(packed, bytes)
        assert packed.startswith(b"MGZ1")
        assert len(packed) < len(log.encode("utf-8"))
        conn.execute("INSERT INTO study_record(session_id,record_date,question_type,dialogue_log) VALUES(?,?,?,?)",
                     ("legacy", "2026-10-12", "计算题", "[]"))
    db.init_db(p)
    assert db.query_history(date="2026-10-13", qtype="几何应用题", db_path=p)[0]["dialogue_log"] == log
    assert db.query_history(date="2026-10-12", db_path=p)[0]["dialogue_log"] == "[]"
    assert db.weak_stats(p)[0]["not_understood"] == 1


def test_short_record_stays_plain_text():
    assert db.encode_dialogue("[]") == "[]"
    assert db.decode_dialogue("[]") == "[]"


def test_corrupt_compression_is_not_silently_replaced():
    with pytest.raises(Exception):
        db.decode_dialogue(b"MGZ1invalid")
    with pytest.raises(ValueError, match="未知"):
        db.decode_dialogue(b"invalid")
