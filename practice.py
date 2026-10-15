"""无需模型的改编练习：受控模板、精确计算、事务判分。"""
import json
import random
import re
import unicodedata
import uuid
from fractions import Fraction

import db


def variant(kid, rng=None):
    """50个知识点的参数化模板。返回题干、精确答案、单位、解析。"""
    rng = rng or random.SystemRandom()
    a, b, c = (rng.randint(2, 12) for _ in range(3))
    unit = ''
    if kid == 1: q, value, step = f'用简便方法计算：{a}+{100-a}+{b}。', 100+b, '先把前两个数凑成100'
    elif kid == 2: q, value, step = f'用简便方法计算：25×{a}×4。', 100*a, '先算25×4'
    elif kid == 3: q, value, step = f'用分配律计算：({a}+{b})×{c}。', (a+b)*c, '括号中每一项都乘外面的数'
    elif kid == 4: q, value, step = f'计算：100-{a}-{b}。', 100-a-b, '100减去两个数的和'
    elif kid == 5: q, value, step = f'计算：{a*b*c}÷{b}÷{c}。', a, '连续除以两个数，等于除以它们的积'
    elif kid == 6: q, value, step = f'计算：{a}+{b}×{c}。', a+b*c, '先乘后加'
    elif kid == 7: q, value, step = f'一个数除以{b}，商是{a}，余数是1，这个数是多少？', a*b+1, '被除数=商×除数+余数'
    elif kid in (8, 9, 10):
        op = {8: '+', 9: '×', 10: '÷'}[kid]
        x, y = Fraction(a, b), Fraction(c, a+b)
        q = f'计算：{a}/{b} {op} {c}/{a+b}，用分数或小数作答。'
        value = x+y if kid == 8 else x*y if kid == 9 else x/y
        step = {8:'先通分再相加',9:'分子相乘、分母相乘后约分',10:'除以分数等于乘它的倒数'}[kid]
    elif 11 <= kid <= 23:
        unit = '厘米' if kid in (11, 13, 18) else '立方厘米' if kid in (21, 23) else '平方厘米'
        variants = {
            11:(f'长方形长{a}厘米、宽{b}厘米，周长是多少？',2*(a+b),'(长+宽)×2'),
            12:(f'长方形卡纸长{a}厘米、宽{b}厘米，面积是多少？',a*b,'长×宽'),
            13:(f'正方形边长{a}厘米，周长是多少？',4*a,'边长×4'),
            14:(f'正方形地砖边长{a}厘米，面积是多少？',a*a,'边长×边长'),
            15:(f'平行四边形底{a}厘米、对应高{b}厘米，面积是多少？',a*b,'底×高'),
            16:(f'三角形底{a*2}厘米、对应高{b}厘米，面积是多少？',a*b,'底×高÷2'),
            17:(f'梯形上底{a*2}厘米、下底{b*2}厘米、高{c}厘米，面积是多少？',(a+b)*c,'(上底+下底)×高÷2'),
            18:(f'圆的直径{a}厘米，取π=3.14，周长是多少？',Fraction(314*a,100),'π×直径'),
            19:(f'圆的半径{a}厘米，取π=3.14，面积是多少？',Fraction(314*a*a,100),'π×半径×半径'),
            20:(f'封闭长方体长{a}厘米、宽{b}厘米、高{c}厘米，表面积是多少？',2*(a*b+a*c+b*c),'(长×宽+长×高+宽×高)×2'),
            21:(f'长方体长{a}厘米、宽{b}厘米、高{c}厘米，体积是多少？',a*b*c,'长×宽×高'),
            22:(f'正方体棱长{a}厘米，表面积是多少？',6*a*a,'棱长×棱长×6'),
            23:(f'正方体棱长{a}厘米，体积是多少？',a*a*a,'棱长×棱长×棱长')}
        q, value, step = variants[kid]
    elif kid == 24: q, value, step, unit = f'三角形两个内角分别是{a*3}度和{b*3}度，第三个角是多少？', 180-3*a-3*b, '180减去两个已知角', '度'
    elif kid == 25: q, value, step, unit = f'骑车速度每小时{a}千米，骑行{b}小时，路程是多少？',a*b,'速度×时间','千米'
    elif kid == 26: q, value, step, unit = f'两人相距{(a+b)*c}千米，相向而行，速度每小时{a}和{b}千米，几小时相遇？',c,'总路程÷速度和','小时'
    elif kid == 27: q, value, step, unit = f'快车每小时{a+b}千米，慢车每小时{b}千米，同向行驶且慢车领先{a*c}千米，快车几小时追上？',c,'路程差÷速度差','小时'
    elif kid == 28: q, value, step, unit = f'火车长{a*10}米，桥长{b*100}米，从车头上桥到车尾离桥共行驶多少米？',a*10+b*100,'桥长+车长','米'
    elif kid == 29: q, value, step, unit = f'汽车前{a}小时行驶{a*20}千米，后{b}小时行驶{b*40}千米，平均速度是多少？请用分数或小数。',Fraction(a*20+b*40,a+b),'总路程÷总时间','千米/小时'
    elif kid == 30: q, value, step, unit = f'船在静水中每小时{a+b}千米，水流每小时{b}千米，逆水速度是多少？',a,'船速-水速','千米/小时'
    elif kid == 31: q, value, step, unit = f'一本书原价{a*10}元，打八折，现价是多少？',a*8,'原价×0.8','元'
    elif kid == 32: q, value, step = f'一班有{a*10}人，其中20%参加绘画组，绘画组有多少人？',a*2,'总人数×20%'
    elif kid == 33: q, value, step = f'绘画组有{a*2}人，占全班20%，全班有多少人？',a*10,'部分人数÷20%'
    elif kid == 34: q, value, step = f'把{a*5}%化为小数。',Fraction(a*5,100),'去掉百分号，除以100'
    elif kid == 35: q, value, step, unit = f'{a*10}件产品中有{a*9}件合格，合格率是多少？',90,'合格数÷总数×100%','%'
    elif kid == 36: q, value, step, unit = f'本金{a*1000}元，年利率2%，存{b}年，按单利计算利息是多少？',a*20*b,'本金×年利率×年数','元'
    elif kid == 37: q, value, step = f'去年产量{a*100}吨，今年增产二成，今年产量多少吨？',a*120,'原产量×(1+20%)'
    elif kid == 38: q, value, step, unit = f'把{a}克盐加入{a*9}克水中，盐水浓度是多少？',10,'盐÷(盐+水)×100%','%'
    elif 39 <= kid <= 46:
        items = {39:(f'{a}千米是多少米？',a*1000,'千米换米乘1000','米'),40:(f'{a}平方米是多少平方厘米？',a*10000,'平方米换平方厘米乘10000','平方厘米'),41:(f'{a}升是多少毫升？',a*1000,'升换毫升乘1000','毫升'),42:(f'{a}千克是多少克？',a*1000,'千克换克乘1000','克'),43:(f'{a}小时是多少分钟？',a*60,'小时换分钟乘60','分钟'),44:(f'{a}年是多少个月？',a*12,'年数×12','个月'),45:(f'{a}元是多少角？',a*10,'元换角乘10','角'),46:(f'{a*100}厘米是多少米？',a,'小单位换大单位除以进率100','米')}
        q, value, step, unit = items[kid]
    elif kid == 47: q, value, step = f'三次得分为{a}、{a+b}、{a+2*b}，平均分是多少？',a+b,'三次总分÷3'
    elif kid == 48: q, value, step = f'{b}组平均每组有{a}本书，共有多少本书？',a*b,'平均数×组数'
    elif kid == 49: q, value, step = f'两个盒子分别有{a*2}个和{a*2+b*2}个球，从多的盒子拿多少个给少的，数量相等？',b,'数量差÷2'
    elif kid == 50: q, value, step = f'三科平均分{60+a}，其中两科为60和{60+b}分，第三科是多少分？',60+3*a-b,'平均分×3减去两科已知分数'
    else: raise ValueError('该知识点暂不支持改编练习')
    return dict(question=q, expected=str(Fraction(value)), unit=unit, explanation=step)


def public(row):
    payload = json.loads(row['payload'])
    result = dict(id=row['id'], knowledge_id=row['knowledge_id'],
                knowledge_point=payload['knowledge_point'], question=payload['question'],
                answer_unit=payload['unit'], hinted=bool(row['hinted']),
                answered=row['correct'] is not None)
    if result['answered']:
        result.update(answer=row['answer'], correct=bool(row['correct']),
                      expected=payload['expected'] + payload['unit'],
                      explanation=payload['explanation'],
                      feedback=('答对了！' if row['correct'] else '这次还需要复习。') +
                      (' 使用过提示，本题不计为独立答对。' if row['hinted'] else ''))
    return result


def create(knowledge_id=None, db_path=None):
    formulas = db.get_all_formulas(db_path)
    if knowledge_id is None:
        ids = {f['knowledge_point']: f['id'] for f in formulas}
        ranked = [r for r in db.weak_stats(db_path) if r['knowledge_point'] in ids and r['weak_score'] > 0]
        knowledge_id = ids[ranked[0]['knowledge_point']] if ranked else random.choice(formulas)['id']
    card = next((f for f in formulas if f['id'] == knowledge_id), None)
    if card is None:
        raise ValueError('知识点不存在')
    payload = variant(knowledge_id)
    payload.update(knowledge_point=card['knowledge_point'], hint=card['easy_tip'], formula=card['formula'])
    with db._conn(db_path) as conn:
        # 短题模板的参数空间有限，尽量避免同知识点最近题目重复。
        recent = {json.loads(r['payload'])['question'] for r in conn.execute(
            'SELECT payload FROM practice_exercise WHERE knowledge_id=? ORDER BY rowid DESC LIMIT 5', (knowledge_id,))}
        for _ in range(30):
            if payload['question'] not in recent:
                break
            payload.update(variant(knowledge_id))
        eid = uuid.uuid4().hex
        conn.execute('INSERT INTO practice_exercise(id,knowledge_id,payload) VALUES (?,?,?)',
                     (eid, knowledge_id, json.dumps(payload, ensure_ascii=False)))
        row = conn.execute('SELECT * FROM practice_exercise WHERE id=?', (eid,)).fetchone()
    return public(row)


def get(eid, db_path=None):
    with db._conn(db_path) as conn:
        row = conn.execute('SELECT * FROM practice_exercise WHERE id=?', (eid,)).fetchone()
    if row is None:
        raise LookupError('练习不存在')
    return public(row)


def hint(eid, db_path=None):
    with db._conn(db_path) as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT * FROM practice_exercise WHERE id=?', (eid,)).fetchone()
        if row is None: raise LookupError('练习不存在')
        if row['correct'] is not None: raise RuntimeError('本题已提交，请开始下一题')
        conn.execute('UPDATE practice_exercise SET hinted=1 WHERE id=?', (eid,))
        p = json.loads(row['payload'])
    return dict(hint=p['hint'], formula=p['formula'], hinted=True)


def parse_answer(text, unit):
    """只接受单个数值或分数，允许正确单位；不执行表达式或代码。"""
    value = unicodedata.normalize('NFKC', text).strip().replace(' ', '')
    for alias in {'厘米':'cm', '平方厘米':'cm2', '立方厘米':'cm3',
                  '米':'m', '千米':'km', '千米/小时':'km/h'}.items():
        if unit == alias[0] and value.endswith(alias[1]):
            value = value[:-len(alias[1])]
    if unit and value.endswith(unit):
        value = value[:-len(unit)]
    if not re.fullmatch(r'[+-]?\d+(?:\.\d+)?(?:/[+-]?\d+(?:\.\d+)?)?', value):
        raise ValueError('请填写一个数值或分数，可附指定单位，不要输入完整算式')
    parts = value.split('/')
    try:
        result = Fraction(parts[0])
        if len(parts) == 2: result /= Fraction(parts[1])
    except (ValueError, ZeroDivisionError):
        raise ValueError('数值无效，分母不能为0') from None
    return result


def submit(eid, answer, db_path=None):
    with db._conn(db_path) as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT * FROM practice_exercise WHERE id=?', (eid,)).fetchone()
        if row is None: raise LookupError('练习不存在')
        if row['correct'] is not None: raise RuntimeError('本题已提交，不能重复计入统计')
        p = json.loads(row['payload'])
        value = parse_answer(answer, p['unit'])
        correct = value == Fraction(p['expected'])
        conn.execute('UPDATE practice_exercise SET answer=?, correct=?, answered_at=CURRENT_TIMESTAMP WHERE id=?',
                     (answer, int(correct), eid))
    stats = next(r for r in db.weak_stats(db_path) if r['knowledge_point'] == p['knowledge_point'])
    return dict(correct=correct, independent=correct and not row['hinted'],
                expected=p['expected'] + p['unit'], explanation=p['explanation'],
                stats=stats, feedback=('答对了！' if correct else '这次还需要复习。') +
                (' 使用过提示，本题不计为独立答对。' if row['hinted'] else ''))
