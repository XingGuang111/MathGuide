"""Record real local-model tutoring through the Web API using isolated demo data.

Run explicitly; this is not part of the offline pytest suite. No model responses
are mocked. Each run keeps its transcript, checks, timings and demo database.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sys
import time
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SHANGHAI = timezone(timedelta(hours=8), name='Asia/Shanghai')

import config


def contains_answer(reply, answer):
    # “24颗” is a condition, not an accidental occurrence of the answer “4颗”.
    return bool(re.search(r'(?<![\d.])' + re.escape(answer), reply))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    config.DB_PATH = str(output / ('tutor-demo-' + uuid.uuid4().hex + '.db'))

    from fastapi.testclient import TestClient
    import db
    import llm
    import web_app

    report = {
        'started': datetime.now(SHANGHAI).isoformat(),
        'model': config.MODEL_NAME,
        'model_responses_mocked': False,
        'database': config.DB_PATH,
        'scenarios': [],
        'model_dialogue_enabled': config.ENABLE_MODEL_DIALOGUE,
        'model_calls': [],
    }

    # Observe real calls without replacing their outputs. Keep evidence of the
    # analyze-before-speaking order for each student turn in the report.
    def observe(name, function):
        def call(*args, **kwargs):
            entry = {'kind': name, 'started': datetime.now(SHANGHAI).isoformat()}
            report['model_calls'].append(entry)
            result = function(*args, **kwargs)
            entry['ok'] = result is not None
            return result
        return call

    llm.diagnose = observe('student_analysis', llm.diagnose)
    llm.compose_reply = observe('student_reply', llm.compose_reply)

    def save():
        (output / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        lines = ['# MathGuide 真实本地模型辅导记录', '',
                 f"测试时间：{report['started']}（Asia/Shanghai）", '',
                 f"模型：`{report['model']}`；通过实际 Web API 调用，未替换模型回复。", '',
                 '学生输入为测试脚本；每轮先由本地模型分析学生回复，再生成教师回答。程序核验计算、阶段及重复问题，记录真实输出与失败结果。', '']
        for scenario in report['scenarios']:
            lines.extend([f"## {scenario['name']}", '', f"题目：{scenario['question']}", ''])
            for turn in scenario['turns']:
                if turn.get('student'):
                    lines.extend([f"**学生：** {turn['student']}", ''])
                lines.extend([f"**老师：** {turn.get('reply', '')}", '',
                              f"耗时 {turn['seconds']:.2f} 秒；完成状态：{turn.get('finished', False)}。", ''])
            for check in scenario['checks']:
                lines.append(f"- {'通过' if check['passed'] else '失败'}：{check['description']}")
            if scenario.get('error'):
                lines.extend(['', '执行异常：' + scenario['error']])
            lines.append('')
        (output / 'transcripts.md').write_text('\n'.join(lines), encoding='utf-8')

    def check(scenario, condition, description):
        scenario['checks'].append({'description': description, 'passed': bool(condition)})
        if not condition:
            print('FAIL:', scenario['name'], description, flush=True)

    with TestClient(web_app.app) as client:
        health = client.get('/api/health')
        report['health'] = health.json()
        save()
        if health.status_code != 200 or not report['health'].get('ok'):
            raise RuntimeError('本地模型健康检查未通过，详情见 results.json')

        def request(scenario, url, payload, student=None, expected_status=200):
            before = time.perf_counter()
            first_call = len(report['model_calls'])
            response = client.post(url, json=payload)
            elapsed = time.perf_counter() - before
            body = response.json()
            scenario['turns'].append({'student': student, 'seconds': round(elapsed, 3),
                                      'http_status': response.status_code,
                                      'reply': body.get('reply', body.get('message', body.get('detail', ''))),
                                      'finished': body.get('finished', False), 'response': body})
            check(scenario, response.status_code == expected_status,
                  f'接口按预期返回 {expected_status}：' + (student or '开始辅导'))
            reply = scenario['turns'][-1]['reply']
            check(scenario, isinstance(reply, str) and bool(reply.strip()), '回复有可读内容')
            if isinstance(reply, str):
                check(scenario, not re.search(r'\[(?:CONTINUE|UNDERSTOOD|CARD:|ALERT)|<think>', reply), '不展示内部协议或推理标记')
                check(scenario, not re.search(r'^(?:给学生的)?(?:开场问句|开场白|参考问句)\s*[:：]', reply), '不展示教学旁白或问句标签')
                check(scenario, len(re.findall(r'[？?]', reply)) <= 1, '一次最多提一个问题')
                if student and body.get('finished') and not scenario.get('understood') == 0:
                    check(scenario, not re.search(r'别忘|记得.{0,12}(?:加|补|写)|(?:忘记|忘了|漏|没有).{0,12}单位|已经掌握|熟练掌握', reply), '已完成时不再索要已补齐的单位或夸大掌握')
            if student and config.ENABLE_MODEL_DIALOGUE:
                calls = report['model_calls'][first_call:]
                check(scenario, len(calls) >= 2 and calls[0]['kind'] == 'student_analysis'
                      and any(c['kind'] == 'student_reply' for c in calls[1:]), '先分析学生本轮回答，再由模型生成实际回复')
            check(scenario, not body.get('retryable', False), '本轮无需用户重试')
            save()
            print(f"{scenario['name']} | {student or '开场'} | {elapsed:.2f}s | {reply}", flush=True)
            return body

        cases = [
            dict(name='平均分：解释概念、纠错、分轮补全', question='老师有24颗糖，平均分给6个小朋友，每个人有几颗？',
                 formula='每份数=总数÷份数', answer='4颗',
                 messages=['不明白', '还是没明白', '24÷6=5颗', '24÷6=4', '颗'], understood=1),
            dict(name='折扣：连续算错后拆小步', question='一件商品原价200元，打八折后多少钱？',
                 formula='现价=原价×折扣率', answer='160元',
                 messages=['200×0.8=180', '170', '8', '160', '元'], understood=1),
            dict(name='面积：读题、找方法、计算归档', question='长方形花园长12米宽8米，面积是多少？',
                 formula='长方形面积=长×宽', answer='96平方米',
                 messages=['长12米宽8米，要求花园的面积', '长乘宽，因为求面积', '12×8=96平方米'], understood=1),
            dict(name='复杂疑问：承接表达后完成', question='一件商品原价200元，打八折后多少钱？',
                 formula='现价=原价×折扣率', answer='160元',
                 messages=['我把两个价格弄混了', '200×0.8=160元'], understood=1),
            dict(name='完整讲解：正确记录尚未独立掌握', question='长方形长8厘米宽3厘米，面积是多少？',
                 formula='长方形面积=长×宽', answer='24平方厘米',
                 messages=['请完整讲解'], understood=0),
            dict(name='条件不足：先澄清', question='圆的面积', messages=[], clarify=True),
            dict(name='非数学请求：明确拒绝', question='帮我写一篇300字的作文', messages=[], rejected=True),
            dict(name='不含数字的非数学请求：明确拒绝', question='帮我写作文', messages=[], rejected=True),
        ]
        for case in cases:
            scenario = {**case, 'turns': [], 'checks': []}
            report['scenarios'].append(scenario)
            try:
                started = request(scenario, '/api/sessions', {'question': case['question']},
                                  expected_status=422 if case.get('rejected') else 200)
                if case.get('clarify'):
                    check(scenario, started.get('clarify') and not started.get('session_id'), '缺少题目条件时澄清，不创建辅导会话')
                    continue
                if case.get('rejected'):
                    check(scenario, not started.get('session_id') and not started.get('clarify')
                          and '小学数学' in started.get('detail', ''), '拒绝非数学请求，不创建辅导会话')
                    continue
                sid = started.get('session_id')
                check(scenario, bool(sid), '创建有效辅导会话')
                if not sid:
                    continue
                check(scenario, started.get('card', {}).get('formula') == case['formula'], '展示与题目一致的通用公式')
                check(scenario, not contains_answer(started.get('reply', ''), case['answer']), '开场不直接泄露本题答案')
                last = started
                for index, message in enumerate(case['messages']):
                    last = request(scenario, '/api/replies', {'session_id': sid, 'message': message}, message)
                    if index < len(case['messages']) - 1:
                        check(scenario, not last.get('finished'), '尚未完成作答时继续辅导')
                        result_number = re.match(r'\d+(?:\.\d+)?', case['answer'])[0]
                        supplied = bool(re.search(r'(?<![\d.])' + re.escape(result_number) + r'(?![\d.])', message))
                        check(scenario, supplied or not contains_answer(last.get('reply', ''), case['answer']), '引导过程中不代替学生给出本题答案')
                        if last.get('finished'):
                            break
                check(scenario, last.get('finished') is True, '完整作答或主动请求讲解后正常结束')
                records = [row for row in db.query_history(db_path=config.DB_PATH) if row['session_id'] == sid]
                check(scenario, len(records) == 1 and records[0]['understood'] == case['understood'], '仅归档一次，掌握标记与实际表现一致')
                history = client.get('/api/history').json()
                check(scenario, any(row.get('session_id') == sid and row.get('dialogue') for row in history), '学习档案可回看完整对话')
            except Exception as exc:
                scenario['error'] = str(exc)
                scenario['traceback'] = traceback.format_exc()
                check(scenario, False, '场景执行无异常')
            finally:
                scenario['passed'] = bool(scenario['checks']) and all(item['passed'] for item in scenario['checks'])
                save()

    report['finished'] = datetime.now(SHANGHAI).isoformat()
    report['passed'] = all(scenario['passed'] for scenario in report['scenarios'])
    save()
    good = sum(scenario['passed'] for scenario in report['scenarios'])
    print(f"RESULT: {good}/{len(report['scenarios'])} scenarios passed; records: {output}", flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
