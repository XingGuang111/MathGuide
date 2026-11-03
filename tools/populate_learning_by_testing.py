"""Exercise the running tutor, retaining actual API responses in its learning archive.

Student messages are scripted test inputs. Teacher responses and archive writes
come from the running product. This tool never inserts fabricated history rows.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    dict(key='rectangle-area', topic='长方形面积', question='长方形花园长12米、宽8米，面积是多少？',
         messages=['长12米、宽8米，要求花园的面积。', '用长乘宽，因为求长方形面积。', '12×8=96平方米'], understood=1),
    dict(key='rectangle-review', topic='长方形面积', question='长方形卡纸长9厘米、宽5厘米，面积是多少？',
         messages=['面积和周长我分不清，想请你完整讲解这道题。'], understood=0),
    dict(key='rectangle-perimeter', topic='长方形周长', question='长方形操场长30米、宽20米，周长是多少？',
         messages=['长30米、宽20米，要求围着操场一圈的长度。', '周长等于长加宽的和乘2。', '(30+20)×2=100米'], understood=1),
    dict(key='square-area', topic='正方形面积', question='正方形地砖边长6厘米，面积是多少？',
         messages=['边长6厘米，求正方形的面积。', '面积等于边长乘边长。', '6×6=36平方厘米'], understood=1),
    dict(key='triangle-review', topic='三角形面积', question='三角形底12厘米，对应高8厘米，面积是多少？',
         messages=['我不知道为什么要除以2，请完整讲解这道题。'], understood=0),
    dict(key='fraction-add', topic='分数的加减法', question='计算1/3+1/6，结果写成最简分数。',
         messages=['求三分之一与六分之一的和，两个分母不一样。', '先通分，把1/3化成2/6，再把分子相加，分母不变。', '1/3+1/6=2/6+1/6=3/6=1/2'], understood=1),
    dict(key='discount-corrected', topic='折扣问题', question='一件外套原价200元，打八折后现价是多少元？',
         messages=['200×0.8=180元', '200×0.8=160元'], understood=1),
    dict(key='length-convert', topic='长度单位换算', question='学校到图书馆有2.5千米，换算成米是多少？',
         messages=['已知2.5千米，要换成米。', '1千米等于1000米，大单位化成小单位要乘1000。', '2.5×1000=2500米'], understood=1),
    dict(key='travel-distance', topic='路程速度时间', question='骑车每小时行12千米，骑行3小时，一共行了多少千米？',
         messages=['速度每小时12千米，时间3小时，求路程。', '路程等于速度乘时间。', '12×3=36千米'], understood=1),
    dict(key='average', topic='平均数', question='三次数学练习得分为80分、90分、100分，平均分是多少？',
         messages=['三次得分分别是80、90、100，求这三次得分的平均数。', '平均数等于总分除以次数，要先把三个分数相加，再除以3。', '(80+90+100)÷3=270÷3=90分'], understood=1),
    dict(key='time-review', topic='时间单位换算', question='2小时30分钟一共是多少分钟？',
         messages=['我把小时和分钟的进率忘了，请完整讲解。'], understood=0),
    dict(key='equal-share', topic='平均分', question='老师有24颗糖，平均分给6个小朋友，每个人有几颗？',
         messages=['平均分就是每个人分得一样多，24颗糖分给6人，求每个人几颗。', '每份数等于总数除以份数，用24除以6。', '24÷6=4颗'], understood=1),
    dict(key='waiting-loop', topic='整除', question='一个班有36名学生，要分组，每组有多少人？',
         messages=['我试试'] * 5, understood=0),
    dict(key='classic-chicken-rabbit', topic='鸡兔同笼问题', question='鸡兔同笼共35个头，94条腿，鸡和兔各有多少只？',
         messages=['一共有35个头和94条腿，要找鸡和兔各有多少只。',
                   '先假设35只全是鸡，再用多出来的腿数除以每只兔比鸡多的2条腿，求兔子只数。',
                   '(94-35×2)÷(4-2)=12只兔，35-12=23只鸡'], understood=1),
    dict(key='classic-pursuit', topic='追及问题', question='小明每分钟跑120米，小华每分钟跑150米。小明先跑了2分钟，小华才出发；小华出发后几分钟能追上小明？',
         messages=['已知小明先跑2分钟，速度每分钟120米；小华每分钟150米，要求小华出发后多久追上。',
                   '先求小明领先的路程，再用路程差除以两人的速度差。',
                   '120×2÷(150-120)=240÷30=8分钟'], understood=1),
    dict(key='classic-meeting', topic='相遇问题', question='甲乙两地相距360千米，两辆汽车同时从两地相向而行，甲车每小时行40千米，乙车每小时行50千米，几小时相遇？',
         messages=['两地相距360千米，两车相向而行，速度分别是每小时40千米和50千米，要求相遇时间。',
                   '相遇时间=总路程÷速度和，因为两车相向而行，速度相加。',
                   '360÷(40+50)=360÷90=4小时'], understood=1),
    dict(key='classic-train-bridge', topic='火车过桥问题', question='一列长200米的火车以每秒20米的速度通过一座长600米的桥，从车头上桥到车尾离桥一共需要多少秒？',
         messages=['火车长200米，桥长600米，速度每秒20米，要求车头上桥到车尾离桥的时间。',
                   '火车完全过桥要走桥长加车长，再用总路程除以速度。',
                   '(600+200)÷20=800÷20=40秒'], understood=1),
    dict(key='classic-interest', topic='利息问题', question='小华把5000元存入银行，年利率2%，存期2年，不计复利，到期利息是多少元？',
         messages=['本金5000元，年利率2%，存2年，不计复利，要求利息。',
                   '利息=本金×年利率×时间，按题目说的不计复利计算。',
                   '5000×2%×2=200元'], understood=1),
    dict(key='classic-triangle-review', topic='三角形面积', question='三角形底10厘米，对应高6厘米，面积是多少？',
         messages=['我不懂三角形面积为什么要除以2，请完整讲解，并说明与平行四边形的关系。'], understood=0),
    dict(key='classic-fraction-review', topic='分数的加减法', question='计算3/4-1/6，结果写成最简分数。',
         messages=['我不明白异分母的分数怎样相减，请完整讲解通分和计算过程。'], understood=0),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--only', nargs='*')
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    base = args.base_url.rstrip('/')

    def api(path, payload=None):
        raw = json.dumps(payload, ensure_ascii=False).encode('utf-8') if payload is not None else None
        req = urllib.request.Request(base + path, data=raw, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=180) as response:
            return json.load(response)

    report = dict(started=datetime.now().astimezone().isoformat(), base_url=base,
                  source='实际运行产品API；学生输入为脚本测试作答，教师回复未替换；记录由产品正常归档',
                  model_responses_mocked=False, initial_record_count=len(api('/api/history')), cases=[])

    def save():
        (output / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        lines = ['# 多知识点实际测试与学习档案', '', report['source'], '', f'服务：{base}', '']
        for case in report['cases']:
            lines += [f"## {case['topic']} · {case['key']}", '', case['question'], '']
            for turn in case['turns']:
                if turn.get('student'): lines += ['**测试作答：** ' + turn['student'], '']
                lines += ['**产品回复：** ' + turn.get('reply', ''), '']
            lines += [f"归档编号：{case.get('record_id', '尚未归档')}；检查：{'通过' if case.get('passed') else '待处理'}", '']
            if case.get('problems'): lines += ['问题：' + '；'.join(case['problems']), '']
        (output / 'transcripts.md').write_text('\n'.join(lines), encoding='utf-8')

    for plan in CASES:
        if args.only and plan['key'] not in args.only: continue
        case = {**plan, 'turns': [], 'problems': []}
        report['cases'].append(case)
        try:
            def send(path, payload, student=None):
                start = time.perf_counter()
                body = api(path, payload)
                case['turns'].append(dict(student=student, reply=body.get('reply', body.get('message', '')),
                                          seconds=round(time.perf_counter()-start, 3), response=body))
                reply = case['turns'][-1]['reply']
                if body.get('retryable'): case['problems'].append('产品提示需要重试')
                if re.search(r'\[(?:CONTINUE|UNDERSTOOD|CARD:)|<think>', reply): case['problems'].append('泄露内部标记')
                print(plan['key'], student or '开始', '=>', reply, flush=True)
                save()
                return body
            body = send('/api/sessions', {'question': plan['question']})
            sid = body.get('session_id')
            case['session_id'] = sid
            if not sid: raise RuntimeError('完整题目未创建辅导会话')
            case['matched_topic'] = body.get('card', {}).get('knowledge_point')
            for index, message in enumerate(plan['messages']):
                if index == 0 and plan['understood'] and not re.search(r'[=＝]', message):
                    message = '明白了，' + message
                if body.get('finished'): break
                body = send('/api/replies', {'session_id': sid, 'message': message}, message)
            if plan['key'] == 'waiting-loop':
                teacher_replies = [re.sub(r'\W', '', turn['reply']) for turn in case['turns']]
                if len(teacher_replies) != len(set(teacher_replies)):
                    case['problems'].append('连续等待时产品回复出现完全重复')
                if any(re.search(r'答对|算对|说清楚了|方法找对|都对了|(?:^|[，。])(?:对|没错)[，。]', turn['reply'])
                       for turn in case['turns'][1:]):
                    case['problems'].append('等待用语被错误表扬为答对')
            # Some questions need an explicit explanation of the student's reasoning.
            if not body.get('finished') and plan['understood']:
                for _ in range(5):
                    reply = body.get('reply', '')
                    followup = plan['messages'][-1]
                    if re.search(r'算式|单位|结果|计算', reply):
                        followup = plan['messages'][-1]
                    elif re.search(r'关系|方法|公式', reply) and len(plan['messages']) >= 3:
                        followup = plan['messages'][1]
                    elif re.search(r'明白|理解|题里.*求|要找什么', reply):
                        followup = '明白了，' + plan['messages'][0]
                    elif plan['key'] == 'average' and re.search(r'先.*和|总分.*多少', reply):
                        followup = '80+90+100=270分，然后270÷3=90分'
                    body = send('/api/replies', {'session_id': sid, 'message': followup}, followup)
                    if body.get('finished'): break
            records = [r for r in api('/api/history') if r['session_id'] == sid]
            if len(records) != 1:
                case['problems'].append('未正常归档一次')
            else:
                row = records[0]
                case.update(record_id=row['id'], archived_topic=row['knowledge_point'],
                            archived_understood=row['understood'], archived_dialogue=row['dialogue'])
                if row['knowledge_point'] != plan['topic']: case['problems'].append('知识点归类不符预期')
                if row['understood'] != plan['understood']: case['problems'].append('独立解出标记不符实际测试作答')
                if not row['dialogue']: case['problems'].append('归档没有完整对话')
        except Exception as exc:
            case['problems'].append(str(exc))
        case['passed'] = not case['problems']
        save()
    report.update(finished=datetime.now().astimezone().isoformat(), final_record_count=len(api('/api/history')),
                  passed=all(case['passed'] for case in report['cases']))
    save()
    print('RESULT', sum(c['passed'] for c in report['cases']), '/', len(report['cases']), flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
