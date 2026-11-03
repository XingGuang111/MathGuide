"""Check the learning archive in a real browser, using fictional isolated data."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    fixture = output / ('fixture-' + uuid.uuid4().hex[:8])
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    result = dict(started=datetime.now().astimezone().isoformat(), passed=False,
                  fictional_demo_data=True, checks=[], errors=[])

    def passed(label):
        result['checks'].append(label)
        print('PASS:', label, flush=True)

    with (output / 'server.log').open('w', encoding='utf-8') as server_log:
        server = subprocess.Popen([sys.executable, str(ROOT / 'tools/run_learning_demo.py'),
            '--port', str(port), '--data-dir', str(fixture)], cwd=ROOT,
            stdout=server_log, stderr=server_log)
        try:
            for _ in range(100):
                try:
                    with urllib.request.urlopen(base, timeout=1):
                        break
                except OSError:
                    if server.poll() is not None:
                        raise RuntimeError('演示服务启动失败，见 server.log')
                    time.sleep(.3)
            else:
                raise RuntimeError('演示服务启动超时')
            from playwright.sync_api import sync_playwright, expect
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(viewport={'width':1440, 'height':1050},
                                              record_video_dir=str(output / 'videos'))
                page = context.new_page()
                page.on('pageerror', lambda error: result['errors'].append(str(error)))
                try:
                    page.goto(base + '/?view=learning')
                    expect(page.locator('#learning-view')).to_be_visible()
                    expect(page.locator('#learning-load-status')).to_have_text('')
                    expect(page.locator('#learning-demo-notice')).to_be_visible()
                    expect(page.locator('#learning-metrics .metric-value')).to_have_text(['24道', '16道', '4个', '7天'])
                    expect(page.locator('.weakness-card')).to_have_count(6)
                    expect(page.locator('.weakness-card.is-consolidated')).to_have_count(2)
                    expect(page.locator('#learning-record-count')).to_have_text('24')
                    expect(page.locator('.activity-day')).to_have_count(7)
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    page.screenshot(path=str(output / 'learning-desktop.png'), full_page=True)
                    passed('桌面概览：24条辅导、16道独立解出、4个待练知识点、7天足迹，与真实接口一致')
                    passed('6张知识点卡片：优先复习、正在巩固、2个初步巩固，进度按连续作答展示')
                    page.locator('[data-record-state="review"]').click()
                    expect(page.locator('#learning-record-count')).to_have_text('8')
                    expect(page.locator('#learning-record-list .learning-badge.green')).to_have_count(0)
                    page.locator('[data-record-state="solved"]').click()
                    expect(page.locator('#learning-record-count')).to_have_text('16')
                    page.locator('[data-record-state="all"]').click()
                    page.locator('#learning-search').fill('分数的加减法')
                    expect(page.locator('#learning-record-count')).to_have_text('4')
                    page.locator('#learning-search').fill('没有这道题')
                    expect(page.locator('#learning-record-count')).to_have_text('0')
                    expect(page.locator('#learning-record-list')).to_contain_text('没有找到符合条件')
                    page.locator('#learning-search').clear()
                    page.locator('#learning-more').click()
                    expect(page.locator('.learning-record-row')).to_have_count(24)
                    page.locator('#learning-more').click()
                    expect(page.locator('.learning-record-row')).to_have_count(6)
                    passed('记录筛选、知识点搜索、无匹配提示及展开收起，数量准确')
                    page.locator('.learning-record-row').filter(has_text='长方形花园').locator('button').first.click()
                    expect(page.locator('#records')).to_be_visible()
                    expect(page.locator('#record-detail h3')).to_contain_text('长方形花园')
                    expect(page.locator('.record-message')).to_have_count(7)
                    page.locator('#records').screenshot(path=str(output / 'learning-record-detail.png'))
                    page.locator('#record-type').select_option('百分数应用题')
                    page.locator('#filters button').click()
                    expect(page.locator('.record-select')).to_have_count(4)
                    expect(page.locator('#record-detail h3')).to_contain_text('绘本')
                    with urllib.request.urlopen(base + '/api/history') as response:
                        history = json.load(response)
                    record = next(row for row in history if row['question_type'] == '百分数应用题')
                    page.locator('#record-date').fill(record['record_date'])
                    page.locator('#filters button').click()
                    count = sum(row['question_type']=='百分数应用题' and row['record_date']==record['record_date'] for row in history)
                    expect(page.locator('.record-select')).to_have_count(count)
                    expect(page.locator('#record-detail .record-knowledge-card')).to_contain_text('折扣问题')
                    page.locator('#close-records').click()
                    passed('完整对话回放、公式卡片、独立解出状态、日期与题型联合筛选')
                    with page.expect_request(lambda request: request.url.endswith('/api/practice') and request.method == 'POST') as created:
                        page.locator('[data-practice-topic="12"]').click()
                    assert created.value.post_data_json['knowledge_id'] == 12
                    expect(page.locator('#practice-topic')).to_have_text('长方形面积')
                    page.locator('#practice-close').click()
                    page.locator('#tutor-tab').click()
                    expect(page.locator('#tutor-workspace')).to_be_visible()
                    expect(page.locator('#learning-view')).to_be_hidden()
                    page.locator('#history').click()
                    expect(page.locator('#learning-view')).to_be_visible()
                    passed('卡片直接进入对应知识点练习；辅导与学习档案切换正常')
                    page.reload()
                    expect(page.locator('#learning-metrics .metric-value').first).to_have_text('24道')
                    passed('刷新后演示数据与学习记录保留')
                    mobile = browser.new_context(viewport={'width':390, 'height':844}, is_mobile=True, has_touch=True,
                                                 record_video_dir=str(output / 'videos'))
                    phone = mobile.new_page()
                    phone.on('pageerror', lambda error: result['errors'].append(str(error)))
                    phone.goto(base + '/?view=learning')
                    expect(phone.locator('.weakness-card')).to_have_count(6)
                    assert phone.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    phone.screenshot(path=str(output / 'learning-mobile.png'), full_page=True)
                    phone.locator('[data-view-record]').first.click()
                    expect(phone.locator('#records')).to_be_visible()
                    expect(phone.locator('#record-detail h3')).not_to_be_empty()
                    assert phone.locator('#records').evaluate('(el)=>el.scrollWidth<=el.clientWidth')
                    phone.locator('#records').screenshot(path=str(output / 'learning-record-mobile.png'))
                    phone.locator('#close-records').click()
                    passed('390像素手机布局、卡片与对话弹窗均无横向溢出')
                    empty = browser.new_page(viewport={'width':390, 'height':844})
                    empty.on('pageerror', lambda error: result['errors'].append(str(error)))
                    empty.route('**/api/history', lambda route: route.fulfill(json=[]))
                    empty.route('**/api/stats', lambda route: route.fulfill(json=[]))
                    empty.goto(base + '/?view=learning')
                    expect(empty.locator('#learning-metrics .metric-value').first).to_have_text('0道')
                    expect(empty.locator('#learning-weaknesses')).to_contain_text('先来完成一道题')
                    expect(empty.locator('#learning-record-list')).to_contain_text('从第一道题开始')
                    assert empty.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    empty.screenshot(path=str(output / 'learning-empty-mobile.png'), full_page=True)
                    passed('新档案空状态正常，展示零记录与清晰的开始提示（此项接口使用空数据替身）')
                    empty.close()
                    assert not result['errors'], result['errors']
                    mobile.close(); context.close(); browser.close()
                    result['passed'] = True
                except Exception:
                    try:
                        page.screenshot(path=str(output / 'failure.png'), full_page=True)
                        (output / 'failure-body.txt').write_text(page.locator('body').inner_text(), encoding='utf-8')
                    except Exception:
                        pass
                    raise
        except Exception as exc:
            result['errors'].append(str(exc))
            raise
        finally:
            server.terminate(); server.wait(timeout=15)
            result['finished'] = datetime.now().astimezone().isoformat()
            (output / 'learning-browser-results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
