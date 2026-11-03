# -*- coding: utf-8 -*-
"""公式知识库查询：编号候选列表 + 按 id 查询 + 别名兜底"""
import db
import calculation
import prompts
import re


def match_question(question, db_path=None):
    """已可靠识别的单步题使用通用关系式，不把本题数值算式显示为公式。"""
    sharing = calculation.equal_share(question)
    if sharing:
        # 现有47号练习是“几次得分求平均数”，不把分物品题伪装成同类练习。
        card = dict(get_by_id(47, db_path) or {})
        card.update(id=None, knowledge_point='平均分', formula='每份数=总数÷份数',
                    easy_tip='平均分要求每份一样多；求每人分到的数量，用总数除以人数。')
        return card
    if calculation.discount(question):
        card = dict(get_by_id(31, db_path) or {'id': 31, 'knowledge_point': '折扣问题'})
        values = prompts.discount_values(question)
        card['formula'] = '现价=原价×折扣率'
        card['easy_tip'] = (f'折扣率=折数÷10；{values["discount"]}={values["percent"]}%={values["per_one"]}，'
                            f'表示付原价的{values["percent"]}%，不是便宜{values["percent"]}%。')
        return card
    # Only explicit single-target clues override the model's catalogue choice.
    # Mixed tasks and questions with several requested quantities remain with it.
    compact = re.sub(r'\s+', '', question)
    if '面积' in compact and '周长' in compact:
        return None
    for shape, area, perimeter in [('长方形', 12, 11), ('正方形', 14, 13), ('三角形', 16, None)]:
        if shape in compact and '面积' in compact:
            return get_by_id(area, db_path)
        if shape in compact and '周长' in compact and perimeter:
            return get_by_id(perimeter, db_path)
    if re.search(r'计算\d+/\d+[+＋−-]\d+/\d+', compact):
        return get_by_id(8, db_path)
    if re.search(r'得分|成绩|分数', compact) and re.search(r'平均分|平均数|平均成绩', compact):
        return get_by_id(47, db_path)
    if re.search(r'千米.*(?:换算成|合|等于|是多少)米', compact) and not re.search(r'每|速度|小时|分钟', compact):
        return get_by_id(39, db_path)
    if re.search(r'小时.*(?:多少分钟|几分钟)', compact) and not re.search(r'千米|速度|每', compact):
        return get_by_id(43, db_path)
    if (re.search(r'每小时.*千米', compact) and re.search(r'(?:骑行|行驶|走了)\d+小时', compact)
            and re.search(r'(?:一共|共).*多少千米', compact)):
        return get_by_id(25, db_path)
    return None


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
