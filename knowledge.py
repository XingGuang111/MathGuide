# -*- coding: utf-8 -*-
"""公式知识库查询：编号候选列表 + 按 id 查询 + 别名兜底"""
import db


def load_candidates(db_path=None):
    """构建编号候选列表（单行），注入分析提示词，让模型选编号而非编名称"""
    rows = db.get_all_formulas(db_path)
    return " | ".join(f"{r['id']}. {r['knowledge_point']}" for r in rows)


def get_by_id(kp_id, db_path=None):
    """按编号取公式行；无效 id 返回 None"""
    if not isinstance(kp_id, int) or kp_id <= 0:
        return None
    return db.get_formula_by_id(kp_id, db_path)


def resolve(kp_id, raw_name, db_path=None):
    """先按 id 精确查；失败则用模型输出的原始名称走别名表兜底"""
    row = get_by_id(kp_id, db_path)
    if row is not None:
        return row
    if raw_name:
        return db.find_formula_by_alias(raw_name, db_path)
    return None
