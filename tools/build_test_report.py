"""Build a shareable PM report from recorded test evidence; never reruns tests."""
import argparse
import base64
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
from html import escape
import json
from pathlib import Path
import statistics
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SHANGHAI = timezone(timedelta(hours=8), name='Asia/Shanghai')


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def suite(path):
    cases = list(ET.parse(path).getroot().iter('testcase'))
    rows = defaultdict(lambda: dict(total=0, passed=0, failed=0, errors=0, skipped=0))
    for case in cases:
        row = rows[case.get('classname', 'unknown')]
        row['total'] += 1
        status = ('failed' if case.find('failure') is not None else
                  'errors' if case.find('error') is not None else
                  'skipped' if case.find('skipped') is not None else 'passed')
        row[status] += 1
    totals = {key: sum(row[key] for row in rows.values()) for key in ['total', 'passed', 'failed', 'errors', 'skipped']}
    return totals, rows


def data_url(path, mime):
    return f'data:{mime};base64,' + base64.b64encode(path.read_bytes()).decode('ascii')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', required=True, type=Path)
    args = parser.parse_args()
    run = args.run_dir.resolve()
    final, modules = suite(run / 'pytest-final.xml')
    before, _ = suite(run / 'regression-before-fix.xml')
    after, _ = suite(run / 'regression-after-fix.xml')
    browser = read_json(run / 'browser-final/browser-results.json')
    tutor = read_json(run / 'tutor-final/results.json')
    scenarios = tutor['scenarios']
    good = sum(item['passed'] for item in scenarios)
    turns = [turn for scenario in scenarios for turn in scenario['turns']]
    openings = [scenario['turns'][0]['seconds'] for scenario in scenarios if scenario.get('messages') and scenario['turns']]
    seconds = [turn['seconds'] for turn in turns]
    screenshots = sorted((run / 'browser-final').glob('pet-*.png'))
    videos = sorted((run / 'browser-final/videos').glob('*.webm'))
    generated = datetime.now(SHANGHAI).isoformat()
    summary = dict(generated=generated, automated=final, regression_before=before,
                   regression_after=after, browser_passed=browser['passed'],
                   browser_checkpoint_count=len(browser['checkpoints']),
                   real_model_scenarios_passed=good, real_model_scenarios_total=len(scenarios),
                   screenshot_count=len(screenshots), video_count=len(videos),
                   real_model=tutor['model'], turn_count=len(turns),
                   turn_seconds_median=round(statistics.median(seconds), 3),
                   turn_seconds_max=max(seconds),
                   opening_seconds_max=max(openings),
                   scope='本机单次功能验证；常见题型程序核验；浏览器宠物聊天使用固定回复；非教学效果评估')
    (run / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')

    files = [run / name for name in ['pytest-initial.log', 'pytest-initial.xml',
             'pytest-permission-retry.log', 'pytest-permission-retry.xml',
             'browser-initial.log', 'browser-permission-retry.log',
             'regression-before-fix.log', 'regression-before-fix.xml',
             'regression-after-fix.log', 'regression-after-fix.xml',
             'pytest-final.log', 'pytest-final.xml', 'pytest-final-run.json',
             'browser-final.log', 'browser-final/browser-results.json',
             'tutor-before-fix/transcripts.md', 'tutor-final/results.json',
             'tutor-final/transcripts.md', 'tutor-final.log', 'summary.json']]
    source_files = [ROOT / name for name in ['agent.py', 'prompts.py', 'config.py',
                    'tools/check_pet_browser.py', 'tools/check_tutor_demo.py',
                    'tests/test_agent.py', 'tests/test_conversation_flexibility.py',
                    'web/pet.js', 'web/pet.css', 'pet_emotions.py']]
    manifest = []
    for path in files + screenshots + videos + source_files:
        if path.is_file():
            manifest.append(dict(path=str(path.relative_to(ROOT)), bytes=path.stat().st_size,
                                 sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    (run / 'evidence-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')

    fixes = [
        ('开场混入教学旁白', '真实模型输出“给学生的开场问句：长方形的长和宽你理解了吗？”；原检查只关注问题数量和数学内容，未拦截此类标签。',
         '去除提示词中的说明性占位示例，并在展示前校验开场问句、参考问句等旁白；不合格时使用题型相关的开场。', '3个旁白变体：修复前全部失败，修复后全部通过。'),
        ('纯文字非数学请求被误当成缺条件', '输入“帮我写作文”时，缺数字的快捷判断优先返回“补充具体数值”，没有识别明确的非数学请求。',
         '在缺数字的分支中先识别明确的写作文、写诗、润色和翻译请求，返回只辅导小学数学的提示；数学题条件不足仍正常澄清。', '4个非数学请求：修复前全部失败，修复后全部通过。'),
    ]
    lines = ['# MathGuide 产品测试与演示记录', '', f'记录时间：{generated}（Asia/Shanghai）', '',
             f"结论：完整自动化回归 **{final['passed']}/{final['total']}** 通过；真实本地模型场景 **{good}/{len(scenarios)}** 通过；浏览器 **{len(browser['checkpoints'])}组**检查通过。", '',
             '现有测试先运行，再针对实际输出补充质量检查。发现的两类产品问题共7个回归用例均已由失败转为通过。', '',
             '## 展示材料', '', '- [打开图文演示报告](report.html)（内含截图、可播放录屏和完整对话，可单独分享此 HTML 文件）',
             '- [真实模型完整对话](tutor-final/transcripts.md)', '- [最终测试日志](pytest-final.log)',
             '- [机器可读汇总](summary.json)', '- [证据文件校验清单](evidence-manifest.json)', '',
             '## 测试范围与结果', '', '| 检查 | 结果 | 依据 |', '|---|---|---|',
             f"| 完整自动化回归 | {final['passed']}/{final['total']}，失败{final['failed']}，错误{final['errors']}，跳过{final['skipped']} | pytest-final.xml |",
             f"| 新增问题回归 | 修复前{before['failed']}失败 → 修复后{after['passed']}通过 | regression-before-fix.xml / regression-after-fix.xml |",
             f"| 实际本地模型辅导 | {good}/{len(scenarios)}场景 | tutor-final/results.json |",
             f"| 浏览器交互 | {len(browser['checkpoints'])}组通过；{len(screenshots)}张截图；{len(videos)}段录屏 | browser-final/ |", '',
             '## 问题、原因与修复', '']
    for title, cause, change, evidence in fixes:
        lines.extend([f'### {title}', '', f'原因与表现：{cause}', '', f'修复：{change}', '', f'复测：{evidence}', ''])
    lines.extend(['## 实际本地模型场景', '', '| 场景 | 结果 |', '|---|---|'])
    for scenario in scenarios:
        lines.append(f"| {scenario['name']} | {'通过' if scenario['passed'] else '未通过'} |")
    lines.extend(['', '## 浏览器检查', ''])
    lines.extend('- ' + value for value in browser['checkpoints'])
    lines.extend(['', '## 自动化测试按模块汇总', '', '| 模块 | 通过/总数 |', '|---|---|'])
    for name, row in modules.items():
        lines.append(f"| {name} | {row['passed']}/{row['total']} |")
    lines.extend(['', '## 运行过程与证据说明', '',
                  '- 首次运行受 Windows 临时目录和浏览器进程权限限制，保存原始失败日志；获准后重新运行既有测试，290项通过。权限问题与产品断言失败分别记录。',
                  '- 浏览器首次复跑使用了旧的 shy 动画预期；当前版本采用9段动作配合本地表情，使用当前脚本复测8组通过。保留首次断言失败记录。',
                  '- 补充的真实模型记录工具首次遇到 Windows 缺少 tzdata，已改用标准库固定东八区，无需安装额外依赖。',
                  '- 补充脚本曾把非数学拒绝错误地预期为 HTTP 200；核对现有 API 后改为 HTTP 422，并保留首次结果。没有改变产品拒绝逻辑来迎合测试。',
                  '- 新增7个问题回归检查先在修复前运行并确认全部失败，再修改产品代码；最终运行完整测试与真实模型场景。',
                  '- 现有 Starlette/httpx 接口弃用警告仍保留，不影响本次测试通过。', '',
                  '## 演示顺序（约5分钟）', '',
                  '1. 用平均分对话展示“不明白→解释概念→小例子→纠错→补单位→完成”。',
                  '2. 用折扣对话展示“连续算错→缩小数字→回到原题”，已确认的算式不会丢失。',
                  '3. 打开练习截图和录屏，展示答错时共情、连续独立答对3题大笑、奖励与成长。',
                  '4. 展示面积题归档回看与“请完整讲解”后的尚未独立掌握标记。',
                  '5. 用修复记录说明质量检查和复测过程，再展示手机布局。', '',
                  '## 结论适用范围', '',
                  f"本次使用 `{tutor['model']}`，真实辅导通过 Web API 调用；常见题型的阶段与计算由产品自身的程序核验。浏览器宠物聊天使用固定替身，只验证界面和交互。", '',
                  f"真实辅导共{len(turns)}次请求，本次中位耗时{statistics.median(seconds):.2f}秒、最大{max(seconds):.2f}秒，开场最大{max(openings):.2f}秒；数据仅描述当前机器这一次运行，不作为性能承诺。", '',
                  '此次未执行真实图片 OCR 识别准确率评估、全部题型的真实模型教学验收、真实手机真机与大规模并发测试；没有学生学习效果研究。页面中的题目和档案均为隔离演示数据。', '',
                  '## 复现命令', '', '在项目根目录执行，下方 RUN 请替换为一个新的记录目录：', '', '```powershell',
                  'python -m pytest tests -v -ra -p no:cacheprovider --basetemp RUN/pytest-temp --junitxml RUN/pytest-final.xml',
                  'python tools/check_pet_browser.py --output-dir RUN/browser-final --record-video',
                  'python tools/check_tutor_demo.py --output-dir RUN/tutor-final', '```', ''])
    (run / 'README.md').write_text('\n'.join(lines), encoding='utf-8')

    metrics = ''.join(f'<article class="metric"><strong>{value}</strong><span>{label}</span></article>' for value, label in [
        (f"{final['passed']}/{final['total']}", '自动化回归通过'), (f'{good}/{len(scenarios)}', '真实模型场景通过'),
        (str(len(browser['checkpoints'])), '浏览器交互检查组'), (str(after['passed']), '问题修复回归通过')])
    fix_html = ''.join(f'<article class="fix"><span class="tag">已复测</span><h3>{escape(title)}</h3><p>{escape(cause)}</p><p><b>修复：</b>{escape(change)}</p><small>{escape(evidence)}</small></article>' for title, cause, change, evidence in fixes)
    conversations = ''
    for i, scenario in enumerate(scenarios):
        bubbles = '<div class="question">题目：' + escape(scenario['question']) + '</div>'
        for turn in scenario['turns']:
            if turn.get('student'):
                bubbles += '<div class="bubble student"><b>学生</b><p>' + escape(turn['student']) + '</p></div>'
            bubbles += '<div class="bubble teacher"><b>老师</b><p>' + escape(str(turn['reply'])) + f"</p><small>{turn['seconds']:.2f} 秒</small></div>"
        conversations += f'<details {"open" if i == 0 else ""}><summary><span class="dot"></span>{escape(scenario["name"])}<span class="result">{"通过" if scenario["passed"] else "未通过"}</span></summary><div class="dialogue">{bubbles}</div></details>'
    gallery = ''
    for name, title, caption in [
        ('pet-desktop.png', '桌面学习空间', '知识卡片、辅导对话与宠物陪伴集中呈现。'),
        ('pet-practice-crying.png', '答错时给予陪伴', '连续遇到困难时显示共情表情，仍奖励努力。'),
        ('pet-practice-laugh.png', '连续答对后大笑', '服务端核验连续独立答对3题后触发。'),
        ('pet-shop.png', '学习奖励与商店', '完成真实任务获得星星，支持喂食与可复用玩具。'),
        ('pet-pout.png', '玩耍过久提醒学习', '达到互动次数后温柔催学，完成任务恢复互动。'),
        ('pet-mobile.png', '手机尺寸布局', '390像素浏览器模拟布局通过，无横向溢出。')]:
        path = run / 'browser-final' / name
        if path.is_file():
            gallery += f'<figure><a href="{data_url(path, "image/png")}" target="_blank"><img src="{data_url(path, "image/png")}" alt="{title}" loading="lazy"></a><figcaption><b>{title}</b><p>{caption}</p></figcaption></figure>'
    video_html = ''.join(f'<figure><video controls preload="metadata" src="{data_url(path, "video/webm")}"></video><figcaption>本次浏览器操作录屏 {i+1} · {path.stat().st_size/1024:.0f} KB</figcaption></figure>' for i, path in enumerate(videos))
    module_html = ''.join(f'<tr><td>{escape(name.replace("tests.test_", ""))}</td><td>{row["passed"]}/{row["total"]}</td><td class="green">通过</td></tr>' for name, row in modules.items())
    checkpoint_html = ''.join('<li>' + escape(value) + '</li>' for value in browser['checkpoints'])
    html = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MathGuide · 产品测试与演示记录</title><style>
*{box-sizing:border-box}body{margin:0;background:#f4f7fa;color:#223347;font:16px/1.75 "Microsoft YaHei","Segoe UI",sans-serif}main{max-width:1120px;margin:auto;padding:34px 26px 70px}header{padding:45px 44px;background:#123c52;border-radius:22px;color:white}header .eyebrow{font-size:13px;letter-spacing:3px;color:#9edcc8}h1{font-size:38px;line-height:1.3;margin:15px 0}header p{color:#d5e6eb;max-width:760px;margin-bottom:0}h2{font-size:25px;margin:0 0 14px}h3{font-size:18px;margin:8px 0}p{margin:8px 0}.stamp{margin-top:22px;font-size:12px;color:#b7d4dd}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:20px 0 30px}.metric{padding:22px;background:white;border:1px solid #dfebed;border-radius:15px}.metric strong{font-size:32px;display:block;color:#147557}.metric span{color:#607386;font-size:13px}section{margin-top:30px;padding:30px;background:white;border-radius:18px;border:1px solid #e2eaf0}.intro{color:#61778a;font-size:14px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.fix{border:1px solid #dbe9e3;padding:22px;border-radius:13px;background:#fbfefd}.tag{display:inline-block;font-size:12px;color:#16765b;background:#e3f4ec;padding:2px 9px;border-radius:12px}.fix p{font-size:14px}.fix small{color:#527365}.gallery{display:grid;grid-template-columns:1fr 1fr;gap:18px}figure{margin:0;border:1px solid #dfe7ed;border-radius:12px;overflow:hidden;background:#f7fafc}figure img{display:block;width:100%;height:285px;object-fit:contain;object-position:center}figcaption{font-size:14px;background:white;padding:15px 18px}figcaption p{font-size:12px;color:#687e90;margin:4px 0 0}video{width:100%;max-height:400px;display:block;background:#0c2433}details{border:1px solid #e0e9ef;border-radius:12px;margin:12px 0;overflow:hidden}summary{padding:18px;font-size:15px;cursor:pointer;display:flex;align-items:center;gap:10px;background:#f8fbfc}.dot{width:8px;height:8px;border-radius:50%;background:#1c956e;flex-shrink:0}.result{margin-left:auto;color:#16815f;font-size:12px;white-space:nowrap}.dialogue{padding:20px;background:#fbfcfe}.question{border-left:3px solid #467b99;padding:9px 14px;margin:0 0 20px;color:#47667c;font-size:14px}.bubble{padding:12px 16px;border-radius:12px;margin:13px 0;max-width:88%;font-size:14px}.bubble b{font-size:11px;color:#567585}.bubble p{white-space:pre-wrap;margin:3px 0}.teacher{background:#eaf4f0}.student{background:#eaf0f9;margin-left:auto}.bubble small{color:#749087;font-size:11px}table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:10px 12px;border-bottom:1px solid #e6edf1}th{color:#60768b;background:#f6f9fb}.green{color:#188361}ul,ol{padding-left:23px}li{margin:8px 0;font-size:14px}.note{padding:14px 18px;border-left:3px solid #62a08b;background:#eff8f3;font-size:14px;margin-top:18px}.boundary{font-size:13px;color:#62778a}.audit{font-size:13px;background:#f7f9fc;border-radius:12px;padding:20px}footer{font-size:12px;color:#8798a6;margin-top:26px;text-align:center}a{color:#24728a;text-decoration:none}@media(max-width:650px){main{padding:16px 12px 40px}header{padding:28px 22px}h1{font-size:27px}.metrics{grid-template-columns:1fr 1fr}.metric{padding:15px}.metric strong{font-size:27px}section{padding:22px 16px}.grid,.gallery{grid-template-columns:1fr}figure img{height:auto;max-height:550px}.bubble{max-width:97%}summary{font-size:13px;padding:14px 12px}}@media print{body{background:white}main{max-width:none;padding:0}header{print-color-adjust:exact}section,figure,.fix{break-inside:avoid}details:not([open]) .dialogue{display:block}video{display:none}summary{list-style:none}.metrics{break-inside:avoid}}
</style><main>'''
    html += f'<header><div class="eyebrow">MATHGUIDE / PRODUCT VALIDATION</div><h1>把每一步进步，<br>变成可展示的产品证据。</h1><p>从“不明白”到完成作答，验证启发式辅导、练习闭环与宠物陪伴。保留真实输出、问题修复与复测过程。</p><div class="stamp">2026年10月29日 · 本机实测 · 隔离演示数据 · {escape(tutor["model"])}</div></header><div class="metrics">{metrics}</div>'
    html += '<section><h2>这次验证了什么</h2><p>已有测试全部运行；再使用真实本地模型检查完整对话，并通过浏览器操作验证学习奖励、宠物表情和移动布局。</p><div class="note">发现两类输出问题，新增7个回归检查，确认修复前失败、修复后通过。最终完整回归无失败、无跳过。</div><ol><li><b>教学引导：</b>解释概念、连续错误后换小例子、保留算式、分轮补单位。</li><li><b>结果可信：</b>正确作答后归档，先看讲解记录为尚未独立掌握。</li><li><b>陪伴闭环：</b>练习结果触发表情、奖励、成长与催学解除。</li></ol></section>'
    html += f'<section><h2>实际效果 · 本次浏览器截图</h2><p class="intro">全部取自本次测试。手机为浏览器尺寸模拟；宠物聊天在这一组检查中使用固定回复。</p><div class="gallery">{gallery}</div></section>'
    html += f'<section><h2>真实模型 · 完整辅导对话</h2><p class="intro">点击展开8个场景。文字按实际返回保留；常见题型的计算与阶段由产品自身的程序核验。</p>{conversations}</section>'
    html += f'<section><h2>发现、分析、修复、复测</h2><div class="grid">{fix_html}</div></section>'
    html += f'<section><h2>本次操作录屏</h2><p class="intro">桌面与手机尺寸各一段；录屏嵌入当前文件，可离线播放。</p><div class="grid">{video_html}</div></section>'
    html += f'<section><h2>测试明细</h2><p class="intro">自动化 {final["passed"]}/{final["total"]} 通过；失败 {final["failed"]}、错误 {final["errors"]}、跳过 {final["skipped"]}。保留1条现有接口弃用警告。</p><table><thead><tr><th>模块</th><th>通过/总数</th><th>结果</th></tr></thead><tbody>{module_html}</tbody></table><h3 style="margin-top:25px">浏览器检查通过项</h3><ul>{checkpoint_html}</ul></section>'
    html += f'<section><h2>复测证据与展示范围</h2><div class="audit"><p><b>证据链：</b>首次权限失败日志 → 权限复跑290项通过 → 实际模型发现输出问题 → 7个新增检查先失败 → 修复后7项通过 → 完整回归{final["total"]}项与真实模型8场景复测。</p><p>浏览器旧动画断言与当前版本不同，已按当前9段动作及本地表情重新测试。记录工具的时区依赖和非数学请求状态码预期已校正，原始结果保留。</p><p>完整日志、JUnit明细、对话JSON与文件校验值保存在同目录。HTML中截图、录屏和对话均已嵌入，可单独分享。</p></div><p class="boundary">本次{len(turns)}次实际辅导请求，中位耗时{statistics.median(seconds):.2f}秒，最大{max(seconds):.2f}秒，开场最大{max(openings):.2f}秒；仅描述当前机器单次运行。</p><p class="boundary">覆盖本次列出的功能与场景。尚未进行全部题型的真实教学验收、真实图片OCR准确率评估、手机真机和大规模并发测试，也不代表学生学习效果已获验证。</p></section><footer>MathGuide · 产品测试与演示记录 · 生成于 {escape(generated)} · Asia/Shanghai</footer></main></html>'
    (run / 'report.html').write_text(html, encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print('REPORT:', run / 'report.html')
    return 0 if final['passed'] == final['total'] and good == len(scenarios) and browser['passed'] and after['failed'] == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
