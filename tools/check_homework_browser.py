"""Verify the browser-local homework UI using an isolated server and database."""
from pathlib import Path
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / '.pet-qa' / 'homework'


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    command = (
        'from pathlib import Path; import config; '
        f'config.DB_PATH=Path({str(OUTPUT / ("test-" + uuid.uuid4().hex[:8] + ".db"))!r}); '
        'import uvicorn; '
        'import llm,ocr; '
        'config.ENABLE_MODEL_OPENING=False; config.ENABLE_MODEL_DIAGNOSIS=False; config.ENABLE_MODEL_DIALOGUE=False; '
        'llm.analyze=lambda *args: dict(is_elementary_math=True,knowledge_id=12,question_type="几何应用题",raw_knowledge=None); '
        'llm.generate_formula=lambda question: dict(kind="card",card=dict(id=None,knowledge_point="四则运算",formula="先乘除再加减",easy_tip="仔细验算",is_temp=True)); '
        'ocr.recognize_layout=lambda path: [dict(text=text,box=[[10,y],[500,y],[500,y+25],[10,y+25]],confidence=.99) for text,y in [("1. 计算：36÷6=?",20),("2. 计算：8+5=?",70)]]; '
        'import homework_review,vision,visual_reasoning; '
        'visual_reasoning.solve=lambda *args,**kwargs: dict(verified=True,task_kind="numeric",answer="6",explanation="36÷6=6。",knowledge_point="除法",image_question="36÷6=?",verification="local_vision",quality_version=2); '
        'vision.json_reply=lambda system,payload,images,schema,*args,**kwargs: dict(reply="先观察图中的对称轴。你觉得对应点到轴的距离有什么关系？") if "reply" in schema.get("properties",{}) else dict(text="看图转录：选择不正确的点（见配图）。",visual_summary="图形和选项保留在配图中",needs_review=False); '
        'homework_review.analyze=lambda question,answer: dict(verdict="correct" if answer=="6" else "incorrect", '
        'feedback="测试模型反馈：检查计算。",explanation="测试模型分析：36÷6=6。", '
        'reflection_prompt="怎样检查自己的结果？",knowledge_point="除法"); '
        'homework_review.analyze_visual=lambda question,answer,images: homework_review.analyze(question,answer); '
        f'uvicorn.run("web_app:app",host="127.0.0.1",port={port})'
    )
    errors = []
    with (OUTPUT / 'server.log').open('w', encoding='utf-8') as log:
        server = subprocess.Popen([sys.executable, '-c', command], cwd=ROOT,
                                  stdout=log, stderr=log,
                                  creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            for _ in range(80):
                try:
                    urllib.request.urlopen(base, timeout=1).close()
                    break
                except OSError:
                    if server.poll() is not None:
                        raise RuntimeError('Isolated server failed; see server.log')
                    time.sleep(.2)
            from playwright.sync_api import sync_playwright, expect
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={'width':1440,'height':1100})
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.route('**/api/health', lambda route: route.fulfill(json={'ok':False,'message':'UI test','demo':False}))
                page.goto(base+'/?view=homework')
                expect(page.locator('#hw-empty')).to_be_visible()
                expect(page.locator('#tutor-workspace')).to_be_hidden()
                page.screenshot(path=str(OUTPUT/'empty-desktop.png'),full_page=True)
                page.locator('#hw-demo').click()
                expect(page.locator('#hw-total')).to_have_text('5')
                expect(page.locator('#hw-tutor')).to_be_disabled()
                page.screenshot(path=str(OUTPUT/'student-desktop.png'),full_page=True)
                page.locator('#hw-exit-demo').click()
                page.locator('#hw-empty-create').click()
                page.locator('#hw-title').fill('周末数学作业')
                page.locator('#hw-batch').fill('1. 长方形长 8 厘米，宽 5 厘米。\n面积是多少？\n2. 计算：36 ÷ 6 = ?\n3. 计算：125 + 276 = ?')
                page.locator('#hw-split').click()
                expect(page.locator('.hw-edit-row')).to_have_count(3)
                expect(page.locator('.hw-edit-row textarea').first).to_have_value('长方形长 8 厘米，宽 5 厘米。\n面积是多少？')
                page.locator('.hw-edit-row').nth(1).get_by_role('button',name='第2题上移').click()
                expect(page.locator('.hw-edit-row textarea').first).to_have_value('计算：36 ÷ 6 = ?')
                page.reload()
                page.locator('#hw-parent-mode').click()
                expect(page.locator('.hw-edit-row')).to_have_count(3)
                page.locator('#hw-photo-tab').click()
                page.locator('#hw-photos').set_input_files(str(OUTPUT/'empty-desktop.png'))
                expect(page.locator('.hw-photo')).to_have_count(1)
                page.screenshot(path=str(OUTPUT/'parent-desktop.png'),full_page=True)
                page.locator('#hw-publish').click()
                expect(page.locator('#hw-question')).to_have_text('计算：36 ÷ 6 = ?')
                page.locator('#hw-answer').fill('6')
                page.locator('#hw-save-answer').click()
                expect(page.locator('#hw-question-status')).to_have_text('AI 分析通过')
                expect(page.locator('#hw-done')).to_have_text('1')
                page.locator('#hw-reflection').fill('我用乘法检查结果。')
                page.locator('#hw-in-notes').check()
                page.locator('#hw-save-reflection').click()
                expect(page.locator('#hw-message')).to_contain_text('反思和收录选择已保存')
                page.locator('#hw-next').click()
                page.locator('#hw-skip').click()
                expect(page.locator('#hw-question-status')).to_have_text('稍后再做')
                page.reload()
                expect(page.locator('#hw-question-status')).to_have_text('稍后再做')
                page.locator('.hw-item').first.click()
                expect(page.locator('#hw-answer')).to_have_value('6')
                expect(page.locator('#hw-reflection')).to_have_value('我用乘法检查结果。')
                page.locator('#hw-answer').fill('5')
                page.locator('#hw-save-answer').click()
                expect(page.locator('#hw-question-status')).to_have_text('需要订正')
                expect(page.locator('#hw-done')).to_have_text('0')
                page.locator('#hw-in-notes').uncheck()
                page.locator('#hw-in-mistakes').check()
                page.locator('#hw-save-reflection').click()
                expect(page.locator('#hw-message')).to_contain_text('反思和收录选择已保存')
                page.screenshot(path=str(OUTPUT/'analysis-desktop.png'),full_page=True)
                page.locator('#hw-tutor').click()
                expect(page.locator('#tutor-workspace')).to_be_visible()
                expect(page.locator('#input')).to_have_value('计算：36 ÷ 6 = ?')
                page.locator('#homework-tab').click()
                page.locator('#learning-tab').click()
                expect(page.locator('#homework-view')).to_be_hidden()
                expect(page.locator('.hw-record')).to_have_count(2)
                page.locator('[data-collection="notes"]').click()
                expect(page.locator('.hw-record')).to_have_count(1)
                page.locator('.hw-record summary').click()
                expect(page.locator('.hw-record-body')).to_contain_text('我用乘法检查结果。')
                page.locator('[data-collection="mistakes"]').click()
                expect(page.locator('.hw-record')).to_have_count(1)
                expect(page.locator('.hw-record')).to_contain_text('需要订正')
                page.screenshot(path=str(OUTPUT/'collections-desktop.png'),full_page=True)
                page.locator('#homework-tab').click()
                page.locator('#hw-next').click()
                page.locator('#hw-answer').fill('6')
                page.locator('#hw-next').click()
                page.locator('#hw-answer').fill('5')
                page.locator('#hw-submit-all').click()
                expect(page.locator('#hw-message')).to_contain_text('本次已分析 2/2 题')
                page.route('**/api/homework/reviews', lambda route: route.fulfill(status=503,json={'detail':'测试服务暂不可用，答案已保留'}))
                page.locator('#hw-answer').fill('401')
                page.locator('#hw-save-answer').click()
                expect(page.locator('#hw-message')).to_contain_text('服务暂不可用')
                expect(page.locator('#hw-answer')).to_have_value('401')
                expect(page.locator('#hw-question-status')).to_have_text('待提交')
                page.unroute('**/api/homework/reviews')
                page.set_viewport_size({'width':390,'height':844})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(OUTPUT/'student-mobile.png'),full_page=True)
                page.locator('#hw-parent-mode').click()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(OUTPUT/'parent-mobile.png'),full_page=True)
                page.locator('#hw-text-tab').click()
                page.locator('#hw-batch').fill('\n'.join(f'{n}. 计算：{n} + 1 = ?' for n in range(1,31)))
                page.locator('#hw-split').click()
                expect(page.locator('.hw-edit-row')).to_have_count(33)
                page.locator('#hw-publish').click()
                expect(page.locator('.hw-item')).to_have_count(33)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.reload()
                expect(page.locator('#hw-total')).to_have_text('33')
                expect(page.locator('#hw-sync-status')).to_have_text(re.compile('已载入|已保存'))
                page.locator('.hw-item').nth(2).click()
                expect(page.locator('#hw-sync-status')).to_have_text('已保存，可换设备继续')
                # A new browser has no localStorage; the assignment and answer must come from SQLite.
                other_context=browser.new_context(viewport={'width':390,'height':844})
                phone=other_context.new_page()
                phone.on('pageerror',lambda error: errors.append(str(error)))
                phone.goto(base+'/?view=homework')
                expect(phone.locator('#hw-total')).to_have_text('33')
                expect(phone.locator('#hw-answer')).to_have_value('401')
                phone.locator('#hw-answer').fill('device B draft')
                expect(phone.locator('#hw-sync-status')).to_have_text('已保存，可换设备继续')
                page.locator('#hw-student-mode').click()
                page.locator('#hw-answer').fill('device A draft')
                expect(page.locator('#hw-sync-status')).to_contain_text('另一台设备有更新')
                expect(page.locator('#hw-answer')).to_have_value('device A draft')
                page.locator('#hw-reload').click()
                expect(page.locator('#hw-answer')).to_have_value('device B draft')
                # Homework sessions remain attached to their question across navigation.
                page.locator('#hw-tutor').click()
                with page.expect_response(lambda response: response.url.endswith('/api/sessions')) as started:
                    page.locator('#send').click()
                assert started.value.ok, started.value.json()
                expect(page.locator('#input')).to_have_value('')
                expect(page.locator('#send')).to_have_text('发送 ✦')
                first_session=page.evaluate("localStorage.getItem('mathguide.session')")
                assert first_session
                page.locator('#tutor-homework-return').click()
                page.locator('#hw-next').click()
                page.locator('#hw-tutor').click()
                page.locator('#send').click()
                expect(page.locator('#send')).to_have_text('发送 ✦')
                second_session=page.evaluate("localStorage.getItem('mathguide.session')")
                assert second_session and first_session!=second_session
                page.locator('#tutor-homework-return').click()
                page.locator('.hw-item').nth(2).click()
                page.locator('#hw-tutor').click()
                expect(page.locator('#tutor-workspace')).to_be_visible()
                expect(page.locator('#input')).to_have_value('')
                assert page.evaluate("localStorage.getItem('mathguide.session')")==first_session
                page.locator('#tutor-homework-return').click()
                # New dated assignments preserve older lists and per-page recognition failures.
                page.locator('#hw-new-assignment').click()
                expect(page.locator('#hw-parent')).to_be_visible()
                page.locator('#hw-title').fill('拍照作业')
                page.locator('#hw-date').fill('2026-10-31')
                for name,color in [('page-one.png','white'),('page-two.png','lightblue')]:
                    Image.new('RGB',(600,200),color).save(OUTPUT/name)
                page.locator('#hw-photo-tab').click()
                page.locator('#hw-photos').set_input_files([str(OUTPUT/'page-one.png'),str(OUTPUT/'page-two.png')])
                expect(page.locator('.hw-photo')).to_have_count(2)
                expect(page.locator('#hw-pick-photo')).to_be_enabled()
                photos=page.locator('[data-recognize]').evaluate_all('(els)=>els.map(el=>el.dataset.recognize)')
                blocked='**/api/homework/sources/'+photos[1]+'/recognize'
                page.route(blocked,lambda route: route.fulfill(status=503,json={'detail':'第二页识别暂时失败'}))
                page.locator('#hw-recognize-all').click()
                expect(page.locator('#hw-recognize-all')).to_be_enabled()
                expect(page.locator('[data-import]')).to_have_count(1)
                expect(page.locator('.hw-photo').nth(1)).to_contain_text('第二页识别暂时失败')
                page.unroute(blocked)
                page.locator('[data-recognize]').nth(1).click()
                expect(page.locator('[data-import]')).to_have_count(2)
                page.locator('[data-import]').first.click()
                page.locator('[data-import]').nth(1).click()
                expect(page.locator('.hw-edit-row')).to_have_count(4)
                page.locator('[data-import]').first.click()
                expect(page.locator('.hw-edit-row')).to_have_count(4)
                page.locator('.hw-edit-row [data-source]').first.click()
                expect(page.locator('#hw-source-dialog')).to_be_visible()
                expect(page.locator('#hw-source-image polygon')).to_have_count(2)
                page.locator('#hw-source-close').click()
                page.set_viewport_size({'width':1440,'height':1100})
                page.screenshot(path=str(OUTPUT/'photo-check-desktop.png'),full_page=True)
                page.locator('#hw-publish').click()
                expect(page.locator('#hw-total')).to_have_text('4')
                expect(page.locator('#hw-sync-status')).to_have_text('已保存，可换设备继续')
                page.reload()
                expect(page.locator('#hw-total')).to_have_text('4')
                expect(page.locator('#hw-sync-status')).to_have_text(re.compile('已载入|已保存'))
                expect(page.locator('#hw-source-links button')).to_have_count(1)
                page.locator('#hw-answer').fill('6')
                page.locator('#hw-save-answer').click()
                expect(page.locator('#hw-question-status')).to_have_text('AI 分析通过')
                expect(page.locator('#hw-question-images img')).to_have_count(1)
                assert page.locator('#hw-question-images img').evaluate('(image)=>image.complete&&image.naturalWidth>0')
                page.locator('#hw-tutor').click()
                expect(page.locator('#hw-visual-messages .teacher')).to_have_count(1)
                page.locator('#hw-visual-input').fill('我应该怎样找对应点？')
                page.locator('#hw-visual-send').click()
                expect(page.locator('#hw-visual-messages .teacher')).to_have_count(2)
                page.reload()
                expect(page.locator('#hw-visual-messages .teacher')).to_have_count(2)
                page.locator('#learning-tab').click()
                page.locator('#hw-summary-date').fill('2026-10-31')
                expect(page.locator('.hw-daily-metrics b')).to_have_text(['4','1','1','0','0','3'])
                page.locator('[data-collection="all"]').click()
                page.locator('#hw-record-date').fill('2026-10-31')
                expect(page.locator('.hw-record')).to_have_count(1)
                page.locator('.hw-record summary').click()
                page.locator('[data-record-reflection]').fill('记录验算方法')
                page.locator('[data-record-notes]').check()
                page.locator('[data-save-record]').click()
                expect(page.locator('.hw-record-save-status')).to_contain_text('已保存')
                page.screenshot(path=str(OUTPUT/'daily-summary-desktop.png'),full_page=True)
                page.set_viewport_size({'width':390,'height':844})
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                page.screenshot(path=str(OUTPUT/'daily-summary-mobile.png'),full_page=True)
                other_context.close()
                assert not errors, errors
                browser.close()
            print(json.dumps({'passed': True, 'model':'deterministic test substitute', 'ocr':'deterministic test substitute', 'checks':['empty and demo states','multiline parsing and reorder','draft and answer restore','AI submit and revision','reflection persistence','independent notes and mistakes filters','batch analysis','failure preserves answer','390px layout','30-question batch','independent device recovery','concurrent edit conflict','per-question tutor resume','multiple dated assignments','multi-photo upload and retry','OCR correction with original boxes','duplicate page import prevention','daily summary and date filter','archive reflection editing','per-question image display','picture tutor persistence'], 'page_errors':errors},ensure_ascii=False))
        finally:
            server.terminate()
            server.wait(timeout=15)


if __name__ == '__main__':
    main()
