"""Record real-model anti-loop checks in an isolated, persistent learning archive."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CASES = [
    ('square', '正方形地砖边长6厘米，面积是多少？', ['明白了，边长6厘米，求地砖面积。', '面积等于边长乘边长。', '6×6=36平方厘米'], 1),
    ('fraction', '计算1/3+1/6，结果写成最简分数。', ['明白了，要求两个分数的和。', '先通分，再相加，最后约分。', '1/3+1/6=2/6+1/6=3/6=1/2'], 1),
    ('length', '学校到图书馆有2.5千米，换算成米是多少？', ['明白了，2.5千米换算成米。', '1千米等于1000米，用千米数乘1000。', '2.5×1000=2500米'], 1),
    ('travel', '骑车每小时行12千米，骑行3小时，一共行了多少千米？', ['明白了，速度每小时12千米，时间3小时，求路程。', '路程等于速度乘时间。', '12×3=36千米'], 1),
    ('average', '三次数学练习得分为80分、90分、100分，平均分是多少？', ['明白了，求三次得分的平均分。', '平均分等于总分除以次数。', '(80+90+100)÷3=270÷3=90分'], 1),
    ('unknown-loop', '一个班有36名学生，要分组，每组有多少人？', ['我试试'] * 7, 0),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    import config
    config.DB_PATH = str(out/'learning.db')
    from fastapi.testclient import TestClient
    import web_app
    import db
    report = dict(started=datetime.now().astimezone().isoformat(), model=config.MODEL_NAME,
                  real_model=True, scripted_student=True, database=config.DB_PATH, cases=[])

    def save():
        (out/'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        lines = ['# 本地模型防重复实测', '', '学生输入为测试脚本；教师回复来自实际产品，没有替换模型。', '']
        for case in report['cases']:
            lines += ['## '+case['key'], '', case['question'], '']
            for turn in case['turns']:
                if turn.get('student'): lines += ['**学生：** '+turn['student'], '']
                lines += ['**老师：** '+turn['reply'], '']
            lines += ['检查：'+('通过' if case.get('passed') else '未通过'), '']
            lines += ['- '+item for item in case['problems']]
        (out/'transcripts.md').write_text('\n'.join(lines), encoding='utf-8')

    with TestClient(web_app.app) as client:
        health=client.get('/api/health').json()
        if not health['ok']: raise RuntimeError(health['message'])
        for key, question, messages, understood in CASES:
            case=dict(key=key, question=question, turns=[], problems=[])
            report['cases'].append(case)
            sid=None
            try:
                def request(path, payload, student=None):
                    t=time.perf_counter()
                    response=client.post(path,json=payload)
                    response.raise_for_status()
                    body=response.json()
                    case['turns'].append(dict(student=student,reply=body.get('reply',body.get('message','')),
                                             seconds=round(time.perf_counter()-t,3),response=body))
                    if body.get('retryable'): case['problems'].append('模型调用未正常完成')
                    save()
                    print(key, student or '开场', '=>',case['turns'][-1]['reply'],flush=True)
                    return body
                body=request('/api/sessions',dict(question=question))
                sid=body.get('session_id')
                if body.get('clarify') and key=='unknown-loop':
                    case['clarified']=True
                elif not sid:
                    case['problems'].append('未创建有效会话')
                else:
                    for message in messages:
                        if body.get('finished'): break
                        body=request('/api/replies',dict(session_id=sid,message=message),message)
                    if not body.get('finished'): case['problems'].append('已提交完整答案或连续卡住后仍未结束')
                    rows=[r for r in db.query_history() if r['session_id']==sid]
                    if len(rows)!=1 or rows[0]['understood']!=understood:
                        case['problems'].append('归档结果不符合实际表现')
                    if rows: case['record_id']=rows[0]['id']
                    replies=[re.sub(r'\W','',turn['reply']) for turn in case['turns']]
                    if len(replies)!=len(set(replies)): case['problems'].append('本题重复相同的教师回复')
                    if key=='unknown-loop' and any(re.search(r'答对|算对|说清楚了|方法找对|都对了', turn['reply']) for turn in case['turns'][1:]):
                        case['problems'].append('等待用语被错误表扬为答对')
            except Exception as exc:
                case['problems'].append(str(exc))
            case['passed']=not case['problems']
            save()
    report.update(finished=datetime.now().astimezone().isoformat(),passed=all(c['passed'] for c in report['cases']))
    save()
    print('RESULT',sum(c['passed'] for c in report['cases']),'/',len(report['cases']),flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
