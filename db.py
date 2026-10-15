# -*- coding: utf-8 -*-
"""SQLite 数据访问层：公式库、别名表、学习记录"""
import json
import sqlite3
import zlib
from pathlib import Path

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS math_formula (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    knowledge_point TEXT UNIQUE,
    formula TEXT,
    easy_tip TEXT
);
CREATE TABLE IF NOT EXISTS kp_alias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alias_name TEXT UNIQUE,
    standard_kp TEXT,
    FOREIGN KEY (standard_kp) REFERENCES math_formula(knowledge_point)
);
CREATE TABLE IF NOT EXISTS study_record (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    record_date TEXT,
    question_type TEXT,
    question_text TEXT,
    knowledge_point TEXT,
    formula TEXT,
    dialogue_log TEXT,
    understood INTEGER,
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS practice_exercise (
    id TEXT PRIMARY KEY,
    knowledge_id INTEGER NOT NULL,
    payload TEXT NOT NULL,
    hinted INTEGER NOT NULL DEFAULT 0,
    answer TEXT,
    correct INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    answered_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS practice_knowledge_time
ON practice_exercise(knowledge_id, answered_at);
CREATE INDEX IF NOT EXISTS study_date_type ON study_record(record_date, question_type);
"""


def _conn(db_path=None):
    path = db_path or config.DB_PATH
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path=None):
    """建表（幂等）；公式表为空时从 formulas.json 导入公式与别名"""
    with _conn(db_path) as conn:
        conn.executescript(SCHEMA)
        count = conn.execute("SELECT COUNT(*) AS c FROM math_formula").fetchone()["c"]
        if count == 0:
            with open(config.FORMULAS_JSON, encoding="utf-8") as f:
                items = json.load(f)
            for it in items:
                conn.execute(
                    "INSERT INTO math_formula(id, knowledge_point, formula, easy_tip) VALUES (?,?,?,?)",
                    (it["id"], it["knowledge_point"], it["formula"], it["easy_tip"]),
                )
                for alias in it.get("aliases", []):
                    conn.execute(
                        "INSERT INTO kp_alias(alias_name, standard_kp) VALUES (?,?)",
                        (alias, it["knowledge_point"]),
                    )


def get_all_formulas(db_path=None):
    with _conn(db_path) as conn:
        rows = conn.execute(
            "SELECT id, knowledge_point, formula, easy_tip FROM math_formula ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]


def get_formula_by_id(kp_id, db_path=None):
    with _conn(db_path) as conn:
        row = conn.execute(
            "SELECT id, knowledge_point, formula, easy_tip FROM math_formula WHERE id=?",
            (kp_id,),
        ).fetchone()
    return dict(row) if row else None


def find_formula_by_alias(name, db_path=None):
    """别名精确查 → 别名 LIKE 包含查 → 知识点名称 LIKE 包含查，命中后返回对应公式行；未命中返回 None"""
    with _conn(db_path) as conn:
        row = conn.execute(
            "SELECT standard_kp FROM kp_alias WHERE alias_name=?", (name,)
        ).fetchone()
        if row is None:
            row = conn.execute(
                "SELECT standard_kp FROM kp_alias WHERE ? LIKE '%' || alias_name || '%' LIMIT 1",
                (name,),
            ).fetchone()
        if row is None:
            # 别名未命中时退到知识点名称包含查（如“圆的周长公式”命中“圆的周长”）
            row = conn.execute(
                "SELECT knowledge_point AS standard_kp FROM math_formula "
                "WHERE ? LIKE '%' || knowledge_point || '%' LIMIT 1",
                (name,),
            ).fetchone()
        if row is None:
            return None
        formula = conn.execute(
            "SELECT id, knowledge_point, formula, easy_tip FROM math_formula WHERE knowledge_point=?",
            (row["standard_kp"],),
        ).fetchone()
    return dict(formula) if formula else None


def save_record(record, db_path=None):
    """写入一条学习记录，返回新行 id"""
    with _conn(db_path) as conn:
        cur = conn.execute(
            """INSERT INTO study_record
               (session_id, record_date, question_type, question_text,
                knowledge_point, formula, dialogue_log, understood)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                record["session_id"], record["record_date"], record["question_type"],
                record["question_text"], record["knowledge_point"], record["formula"],
                encode_dialogue(record["dialogue_log"]), record["understood"],
            ),
        )
        return cur.lastrowid


def query_history(date=None, qtype=None, db_path=None):
    sql = "SELECT * FROM study_record"
    conds, params = [], []
    if date:
        conds.append("record_date=?")
        params.append(date)
    if qtype:
        conds.append("question_type=?")
        params.append(qtype)
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY create_time DESC, id DESC"
    with _conn(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    result = [dict(r) for r in rows]
    for row in result:
        row["dialogue_log"] = decode_dialogue(row["dialogue_log"])
    return result


def encode_dialogue(text):
    """版本前缀区分压缩BLOB；短文本保留原文，只有节省空间时才压缩。"""
    raw = text.encode("utf-8")
    packed = b"MGZ1" + zlib.compress(raw, level=6)
    return packed if len(packed) < len(raw) else text


def decode_dialogue(value):
    if isinstance(value, bytes):
        if not value.startswith(b"MGZ1"):
            raise ValueError("未知的学习记录编码")
        return zlib.decompress(value[4:]).decode("utf-8")
    return value


def weak_stats(db_path=None):
    """历史次数不变，融合专项作答计算复习优先分与初步巩固状态。"""
    with _conn(db_path) as conn:
        rows = conn.execute(
            """SELECT knowledge_point,
                      COUNT(*) AS total,
                      SUM(CASE WHEN understood=0 THEN 1 ELSE 0 END) AS not_understood
               FROM study_record
               GROUP BY knowledge_point
               ORDER BY not_understood DESC, total DESC"""
        ).fetchall()
        practiced = conn.execute(
            "SELECT knowledge_id, correct, hinted FROM practice_exercise "
            "WHERE correct IS NOT NULL ORDER BY answered_at, rowid"
        ).fetchall()
        formulas = conn.execute("SELECT id, knowledge_point FROM math_formula").fetchall()
    result = {r['knowledge_point']: dict(r) for r in rows}
    names = {r['id']: r['knowledge_point'] for r in formulas}
    for row in result.values():
        row.update(practice_total=0, independent_correct=0, streak=0,
                   weak_score=row['not_understood'] * 2)
    for attempt in practiced:
        name = names.get(attempt['knowledge_id'])
        if not name:
            continue
        row = result.setdefault(name, dict(knowledge_point=name, total=0,
            not_understood=0, practice_total=0, independent_correct=0,
            streak=0, weak_score=0))
        independent = bool(attempt['correct']) and not attempt['hinted']
        row['practice_total'] += 1
        row['independent_correct'] += int(independent)
        row['streak'] = row['streak'] + 1 if independent else 0
        row['weak_score'] = max(0, row['weak_score'] - 1) if independent else row['weak_score'] + 2
        if row['streak'] >= 3:
            row['weak_score'] = 0
    for row in result.values():
        row['practice_status'] = ('初步巩固' if row['streak'] >= 3 else
                                  '继续复习' if row['practice_total'] else '待练习')
        if row['practice_total'] and row['streak'] < 3:
            row['weak_score'] = max(1, row['weak_score'])
    return sorted(result.values(), key=lambda r: (-r['weak_score'], -r['not_understood'], r['knowledge_point']))
