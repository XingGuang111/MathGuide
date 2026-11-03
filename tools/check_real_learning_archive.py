"""Read-only browser verification of actual tutoring records in the normal archive."""
import argparse
import json
from pathlib import Path
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = json.loads(args.report.read_text(encoding='utf-8'))
    with urllib.request.urlopen(args.base_url + '/api/history') as response:
        rows = json.load(response)
    by_id = {row['id']: row for row in rows}
    for case in report['cases']:
        row = by_id[case['record_id']]
        assert row['session_id'] == case['session_id']
        assert row['knowledge_point'] == case['topic']
        assert row['dialogue'] == case['archived_dialogue']
        assert row['understood'] == case['understood']
    from playwright.sync_api import sync_playwright, expect
    result = dict(passed=False, source='正常学习档案；真实产品API与模型回复；没有预填对话或替换接口', checks=[])
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width':1440, 'height':1050})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(args.base_url + '/?view=learning')
        expect(page.locator('#learning-load-status')).to_have_text('')
        expect(page.locator('#learning-record-count')).to_have_text(str(len(rows)))
        expect(page.locator('#learning-demo-notice')).to_be_hidden()
        result['checks'].append(f"主服务可看到全部{len(report['cases'])}道实测题，知识点、独立解出标记与完整对话一致")
        # Use the ordinary collapse control for a clear presentation screenshot.
        if page.locator('#shop-tab').count():
            page.locator('#shop-tab').click()
        else:
            page.locator('#tutor-tab').click()
        page.locator('#pet-collapse').click()
        page.locator('#learning-tab').click()
        expect(page.locator('#learning-load-status')).to_have_text('')
        page.screenshot(path=str(output/'actual-learning-desktop.png'), full_page=True)
        for topic in ('分数', '平均', '折扣', '长方形', '千米'):
            page.locator('#learning-search').fill(topic)
            assert int(page.locator('#learning-record-count').inner_text()) > 0
        page.locator('#learning-search').fill('外套')
        page.locator('[data-view-record]').first.click()
        expect(page.locator('#record-detail')).to_contain_text('200×0.8=180元')
        expect(page.locator('#record-detail')).to_contain_text('200×0.8=160元')
        page.locator('#records').screenshot(path=str(output/'actual-discount-detail.png'))
        page.locator('#close-records').click()
        page.locator('#learning-search').fill('三角形')
        expect(page.locator('#learning-record-list')).to_contain_text('讲解后复习')
        result['checks'].append('知识点搜索、错后纠正对话回放、讲解后复习状态可见')
        page.locator('#learning-search').clear()
        page.set_viewport_size({'width':390, 'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.screenshot(path=str(output/'actual-learning-mobile.png'), full_page=True)
        page.reload()
        expect(page.locator('#learning-record-count')).to_have_text(str(len(rows)))
        assert not errors, errors
        browser.close()
        result.update(passed=True, total_archive_records=len(rows), verified_real_cases=len(report['cases']),
                      verified_topics=len({case['topic'] for case in report['cases']}), errors=errors)
        result['checks'].append('手机布局无横向溢出，刷新后真实记录保留，页面无脚本异常')
    (output/'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
