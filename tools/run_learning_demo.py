"""Run a clearly labelled learning archive demo in a separate database.

python tools/run_learning_demo.py --port 8020
Open http://127.0.0.1:8020/?view=learning
The displayed history is a fictional product demonstration, not student data.
"""
import argparse
from datetime import datetime, timedelta, timezone
from fractions import Fraction
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import config
import db
import practice

SHANGHAI = timezone(timedelta(hours=8), name='Asia/Shanghai')
MARKER = 'mathguide-learning-demo-v1'


def example(kid, index):
    if kid == 12:
        a, b = [(12, 8), (14, 6), (9, 5), (15, 4)][index]
        return dict(question=f'长方形花园长{a}米、宽{b}米，花园的面积是多少？',
                    reading=f'长{a}米、宽{b}米，要求花园占地的面积。', method='面积是长乘宽。',
                    prompt='这个数量关系找对了，你来把算式和单位一起写出来吧？',
                    expression=f'{a}×{b}={a*b}平方米', type='几何应用题', opening='花园的“面积”和“周长”，你能分清吗？')
    if kid == 31:
        a = [80, 100, 150, 200][index]
        return dict(question=f'一本绘本原价{a}元，书店打八折，现在买这本绘本需要多少元？',
                    reading=f'原价是{a}元，八折后要付多少钱。', method='八折是付原价的80%，用原价乘0.8。',
                    prompt='折扣的意思说清楚了，现在你能算出现价吗？',
                    expression=f'{a}×0.8={a*8//10}元', type='百分数应用题', opening='“打八折”之后，付的钱会比原价多还是少？')
    if kid == 8:
        denominator = [3, 4, 5, 6][index]
        result = Fraction(1, denominator) + Fraction(1, 2*denominator)
        return dict(question=f'计算 1/{denominator} + 1/{2*denominator}，结果写成最简分数。',
                    reading='两个分数的分母不一样，不能直接把分子分母分别加起来。', method=f'先通分成分母{2*denominator}，再加分子。',
                    prompt='分母相同后，你能算出结果并检查是否还能约分吗？',
                    expression=f'1/{denominator}+1/{2*denominator}={result}', type='计算题', opening='这两个分数的分母一样吗？')
    if kid == 39:
        value = [2.5, 3.2, 1.8, 4.6][index]
        return dict(question=f'学校到图书馆有{value}千米，换算成米是多少？',
                    reading='已知千米数，要换成米。', method='1千米等于1000米，大单位换成小单位要乘1000。',
                    prompt='进率找到了，你可以写出换算过程吗？', expression=f'{value}×1000={int(value*1000)}米',
                    type='单位换算题', opening='千米和米，哪个单位更大？')
    if kid == 25:
        speed, hours = [(60, 4), (50, 3), (70, 2), (40, 5)][index]
        return dict(question=f'研学大巴每小时行{speed}千米，学校到营地有{speed*hours}千米，需要几小时？',
                    reading=f'知道路程{speed*hours}千米和速度每小时{speed}千米，要求时间。', method='时间等于路程除以速度。',
                    prompt='数量关系正确，接下来你会怎样列式呢？', expression=f'{speed*hours}÷{speed}={hours}小时',
                    type='行程应用题', opening='题目告诉了路程和速度，你要找的是哪个量？')
    score = 86 + index * 2
    return dict(question=f'小雨三次数学练习得分是{score}、{score+4}、{score+8}分，平均分是多少？',
                reading='把三次得分合起来，再平均分成3份。', method='平均分等于总分除以次数。',
                prompt='次数和总分的关系找对了，你来完成计算吧？', expression=f'({score}+{score+4}+{score+8})÷3={score+4}分',
                type='平均数应用题', opening='求平均分，是只看最高的一次，还是要用到全部得分？')


def prepare_demo(directory):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / 'learning-demo.db'
    if path.exists():
        try:
            with db._conn(str(path)) as connection:
                marker = connection.execute('SELECT value FROM demo_metadata WHERE key=?', ('source',)).fetchone()
        except Exception as exc:
            raise RuntimeError('该目录已有其他数据库，请换一个演示目录。') from exc
        if marker is None or marker['value'] != MARKER:
            raise RuntimeError('此数据库不是本工具创建的演示档案，请换一个目录。')
        return path
    db.init_db(str(path))
    now = datetime.now(SHANGHAI)
    base = now.date() - timedelta(days=6)
    plans = {
        12: dict(understood=[0, 0, 1, 1], practice=[False, 'hint', True]),
        31: dict(understood=[0, 0, 1, 1], practice=[False, True, True]),
        8: dict(understood=[0, 0, 1, 1], practice=[False, True]),
        39: dict(understood=[0, 1, 1, 1], practice=[True, True, True]),
        25: dict(understood=[0, 1, 1, 1], practice=[False, True, True]),
        47: dict(understood=[1, 1, 1, 1], practice=[True, True, True]),
    }
    topics = list(plans)
    for index in range(24):
        kid, variant_index = topics[index % len(topics)], index // len(topics)
        item = example(kid, variant_index)
        card = db.get_formula_by_id(kid, str(path))
        understood = plans[kid]['understood'][variant_index]
        dialogue = [dict(role='teacher', content=item['opening']),
                    dict(role='student', content=item['reading']),
                    dict(role='teacher', content='题意读清楚了。你觉得这些数量之间有什么关系？'),
                    dict(role='student', content=item['method']),
                    dict(role='teacher', content=item['prompt'])]
        if understood:
            dialogue.extend([dict(role='student', content=item['expression']),
                             dict(role='teacher', content='算式、计算结果和单位都对了，这道题是你一步步完成的。')])
        else:
            dialogue.extend([dict(role='student', content='我还是有点不确定，想看完整讲解。'),
                             dict(role='teacher', content=f"先看数量关系：{card['formula']}。\n代入题目中的数：{item['expression']}。\n这次先看了讲解，下一次可以用一道同类题再试试。")])
        date = base + timedelta(days=index * 6 // 23)
        rid = db.save_record(dict(session_id=f'demo-tutor-{index:02d}', record_date=date.isoformat(),
            question_type=item['type'], question_text=item['question'], knowledge_point=card['knowledge_point'],
            formula=card['formula'], dialogue_log=json.dumps(dialogue, ensure_ascii=False), understood=understood), str(path))
        with db._conn(str(path)) as connection:
            connection.execute('UPDATE study_record SET create_time=? WHERE id=?', (f'{date.isoformat()} 16:{index:02d}:00', rid))
    for kid, plan in plans.items():
        card = db.get_formula_by_id(kid, str(path))
        for index, outcome in enumerate(plan['practice']):
            payload = practice.variant(kid, random.Random(kid * 100 + index))
            payload.update(knowledge_point=card['knowledge_point'], hint=card['easy_tip'], formula=card['formula'])
            eid = f'demo-practice-{kid}-{index}'
            with db._conn(str(path)) as connection:
                connection.execute('INSERT INTO practice_exercise(id,knowledge_id,payload) VALUES (?,?,?)',
                                   (eid, kid, json.dumps(payload, ensure_ascii=False)))
            if outcome == 'hint':
                practice.hint(eid, str(path))
            answer = payload['expected'] if outcome is not False else str(Fraction(payload['expected']) + 1)
            practice.submit(eid, answer, str(path))
            date = base + timedelta(days=min(6, index + 3))
            with db._conn(str(path)) as connection:
                connection.execute('UPDATE practice_exercise SET created_at=?,answered_at=? WHERE id=?',
                                   (f'{date.isoformat()} 17:{index:02d}:00', f'{date.isoformat()} 17:{index:02d}:30', eid))
    with db._conn(str(path)) as connection:
        connection.execute('CREATE TABLE demo_metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        connection.execute('INSERT INTO demo_metadata VALUES(?,?)', ('source', MARKER))
        connection.execute('INSERT INTO demo_metadata VALUES(?,?)', ('created', now.isoformat()))
    summary = dict(demo=True, fictional=True, created=now.isoformat(), database=str(path),
                   description='虚构的7天学习轨迹，用于产品展示；不是学生数据或真实模型实测记录。',
                   tutor_records=24, independently_solved=16, practice_records=17,
                   stats=db.weak_stats(str(path)))
    (directory / 'demo-data-description.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8020)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'output/demo-learning-2026-10-29')
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    path = prepare_demo(args.data_dir)
    print('演示数据库：', path, flush=True)
    if args.prepare_only:
        return
    config.DB_PATH = str(path)
    config.DEMO_MODE = True
    import uvicorn
    import web_app
    print(f'演示页面：http://127.0.0.1:{args.port}/?view=learning', flush=True)
    uvicorn.run(web_app.app, host='127.0.0.1', port=args.port, log_level='warning')


if __name__ == '__main__':
    main()
