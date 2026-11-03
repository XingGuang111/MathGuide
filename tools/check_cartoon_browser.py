"""Verify workspace layout and the standalone pet shop using isolated data."""
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import db
import pet


def main():
    output = ROOT / 'output/cartoon-ui/workspaces'
    output.mkdir(parents=True, exist_ok=True)
    database = output / ('shop-' + str(time.time_ns()) + '.db')
    db.init_db(str(database))
    for index in range(3):
        pet.reward('cartoon-ui-check', f'initial-{index}', points=100, xp=0, db_path=str(database))
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    code = (
        f'import config; config.DB_PATH={str(database)!r}; import web_app,uvicorn; '
        'config.ENABLE_MODEL_OPENING=False; config.ENABLE_MODEL_DIAGNOSIS=False; '
        "web_app.llm.analyze=lambda *args:dict(is_elementary_math=True,knowledge_id=12,question_type='几何应用题',raw_knowledge=None); "
        "web_app.llm.chat_stream=lambda messages:iter(['继续看一看题目。[CONTINUE]']); "
        'web_app.llm.check_health=lambda:None; '
        "web_app.llm.pet_reply=lambda messages:'我陪你一步一步来，先读一遍题目吧。'; "
        f"uvicorn.run(web_app.app,host='127.0.0.1',port={port},log_level='warning')"
    )
    server = subprocess.Popen([sys.executable, '-c', code], cwd=ROOT,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f'http://127.0.0.1:{port}'
    errors, checks = [], []
    try:
        for _ in range(80):
            try:
                urllib.request.urlopen(base, timeout=1).close()
                break
            except OSError:
                if server.poll() is not None:
                    raise RuntimeError('Local preview server exited')
                time.sleep(.25)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={'width':1440, 'height':1100})
            context.add_init_script("localStorage.setItem('mathguide.petProfile','cartoon-ui-check')")
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(base)
            expect(page.locator('#health')).to_contain_text('已就绪')
            expect(page.locator('#pet-coins')).to_have_text('⭐ 300')
            expect(page.locator('#pet-avatar')).to_be_visible()
            expect(page.locator('#pet-store-view')).to_be_hidden()
            formula = page.locator('#formula').bounding_box()
            tutor = page.locator('.tutor-panel').bounding_box()
            assert formula['x'] + formula['width'] <= tutor['x']
            assert abs(formula['y'] - tutor['y']) <= 1, (formula, tutor)
            assert page.locator('#tutor-workspace #pet-card').count() == 0
            assert page.locator('.side > .card').count() == 2
            assert page.locator('.tutor-extras .photo-card').count() == 1
            assert page.locator('.tutor-followup #stats').count() == 1
            assert page.locator('.tutor-followup #qrcode-card').count() == 1
            assert page.locator('.tutor-followup #new').count() == 1
            followup = page.locator('.tutor-followup').bounding_box()
            assert followup['y'] >= tutor['y'] + tutor['height']
            expect(page.locator('#qrcode-card')).to_be_visible()
            assert page.locator('#qrcode-img').bounding_box()['width'] <= 104
            page.screenshot(path=str(output / 'tutor-desktop.png'), full_page=True, animations='disabled')
            checks.append('Aligned knowledge and chat; short left rail; review, actions and compact QR below chat')
            page.locator('#input').fill('长方形长12米、宽8米，面积是多少？')
            page.locator('#shop-tab').click()
            expect(page.locator('#pet-store-view')).to_be_visible()
            expect(page.locator('#tutor-workspace')).to_be_hidden()
            expect(page.locator('#shop-tab')).to_have_attribute('aria-pressed', 'true')
            assert page.locator('#pet-dialog').evaluate('(el)=>el.tagName') == 'SECTION'
            expect(page.locator('#shop-grid article')).not_to_have_count(0)
            page.screenshot(path=str(output / 'shop-desktop.png'), full_page=True, animations='disabled')
            page.locator('[data-buy="biscuit"]').click()
            expect(page.locator('#shop-balance')).to_have_text('我的星星 290 ⭐')
            page.locator('[data-use="biscuit"]').click()
            expect(page.locator('#pet-avatar')).to_have_attribute('data-animation', 'eat')
            expect(page.locator('#pet-store-view')).to_be_visible()
            page.locator('#pet-tab-actions').click()
            expect(page.locator('#pet-lessons-grid article')).to_have_count(9)
            page.locator('[data-learn="stretch"]').click()
            expect(page.locator('#shop-balance')).to_have_text('我的星星 270 ⭐')
            page.locator('[data-perform="stretch"]').click()
            expect(page.locator('#pet-avatar')).to_have_attribute('data-animation', 'stretch')
            page.locator('#pet-tab-hats').click()
            page.locator('[data-hat-buy="hat_beret"]').click()
            expect(page.locator('#shop-balance')).to_have_text('我的星星 240 ⭐')
            page.locator('[data-equip="hat_beret"]').click()
            expect(page.locator('#pet-hat')).to_have_attribute('alt', '莓莓贝雷帽')
            page.locator('#pet-tab-hats').focus()
            page.keyboard.press('ArrowRight')
            expect(page.locator('#pet-tab-items')).to_be_focused()
            expect(page.locator('#shop-items-panel')).to_be_visible()
            checks.append('Shop purchases, feeding, lessons, free performance, hats and keyboard category navigation')
            page.locator('#learning-tab').click()
            expect(page.locator('#learning-view')).to_be_visible()
            expect(page.locator('#pet-store-view')).to_be_hidden()
            page.locator('#tutor-tab').click()
            expect(page.locator('#input')).to_have_value('长方形长12米、宽8米，面积是多少？')
            page.locator('#pet-menu-toggle').click()
            page.locator('#pet-context-menu').get_by_role('button', name='🍪 买食物', exact=True).click()
            expect(page.locator('#shop-tab')).to_have_attribute('aria-pressed', 'true')
            page.reload()
            expect(page.locator('#pet-store-view')).to_be_visible()
            expect(page.locator('#shop-balance')).to_have_text('我的星星 240 ⭐')
            expect(page.locator('#pet-hat')).to_have_attribute('alt', '莓莓贝雷帽')
            page.locator('#pet-collapse').click()
            expect(page.locator('#pet-avatar')).to_be_hidden()
            page.locator('#pet-collapse').click()
            expect(page.locator('#pet-avatar')).to_be_visible()
            checks.append('Three workspaces, unsent input preservation, floating menu entry and reload persistence')
            for width in [320, 390, 768, 1024]:
                page.set_viewport_size({'width':width, 'height':900})
                for view, tab in [('tutor','tutor-tab'), ('learning','learning-tab'), ('shop','shop-tab')]:
                    page.locator('#' + tab).click()
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), (width, view)
                    if width == 390:
                        page.screenshot(path=str(output / (view + '-mobile.png')), full_page=True, animations='disabled')
            checks.append('No horizontal overflow at 320, 390, 768 and 1024 pixels in all workspaces')
            page.set_viewport_size({'width':390, 'height':844})
            page.locator('#tutor-tab').click()
            page.locator('#practice').click()
            expect(page.locator('#practice-dialog')).to_be_visible()
            expect(page.locator('#practice-dialog #pet-overlay')).to_have_count(1)
            expect(page.locator('#practice-topic')).not_to_be_empty()
            page.locator('#practice-close').click()
            page.locator('#shop-tab').click()
            page.locator('#pet-chat-toggle').click()
            page.locator('#pet-chat-input').fill('给我加油吧')
            page.locator('#pet-chat-send').click()
            expect(page.locator('#pet-chat-status')).to_have_text('由本地模型回复')
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            checks.append('Mobile practice dialog, companion overlay and pet chat (model reply stubbed)')
            page.set_viewport_size({'width':1440, 'height':1100})
            page.locator('#tutor-tab').click()
            page.locator('#new').click()
            expect(page.locator('#chat')).to_be_empty()
            expect(page.locator('#thinking-notes-content')).to_contain_text('发来一道题')
            def send(text):
                page.locator('#input').fill(text)
                page.locator('#send').click()
                expect(page.locator('#send')).to_be_enabled()
            send('长方形长12米宽8米，面积是多少？')
            expect(page.locator('#thinking-notes-content')).to_contain_text('12米')
            expect(page.locator('#thinking-notes-content')).not_to_contain_text('96')
            send('长12米')
            expect(page.locator('.notes-section li .is-confirmed')).to_have_count(1)
            send('宽8米，求面积')
            expect(page.locator('.notes-done')).to_contain_text('读懂题目')
            send('面积用长乘宽')
            expect(page.locator('#thinking-notes-content')).to_contain_text('长乘宽')
            send('12×8')
            expect(page.locator('.notes-expression')).not_to_be_empty()
            before = page.locator('#thinking-notes-content').text_content()
            page.reload()
            expect(page.locator('#chat')).to_contain_text('已恢复上次辅导')
            expect(page.locator('#thinking-notes-content')).to_have_text(before)
            page.screenshot(path=str(output / 'tutor-live-notes.png'), full_page=True, animations='disabled')
            for width in [320, 390, 768, 1024]:
                page.set_viewport_size({'width':width, 'height':900})
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.screenshot(path=str(output / 'tutor-live-notes-tablet.png'), full_page=True, animations='disabled')
            send('96平方米')
            expect(page.locator('#thinking-notes-content')).to_contain_text('本题已解出')
            send('长方形长12米宽8米，面积是多少？')
            expect(page.locator('#chat .msg.student')).to_have_count(1)
            expect(page.locator('#thinking-notes-content')).not_to_contain_text('本题已解出')
            page.route('**/api/sessions/abort', lambda route: route.fulfill(status=503, json={'detail':'请稍后再试'}))
            page.locator('#new').click()
            expect(page.locator('#alert-banner')).to_contain_text('请稍后再试')
            expect(page.locator('#chat .msg.student')).to_have_count(1)
            page.unroute('**/api/sessions/abort')
            page.locator('#new').click()
            expect(page.locator('#chat')).to_be_empty()
            expect(page.locator('#thinking-notes-content')).to_contain_text('发来一道题')
            expect(page.locator('#formula')).not_to_contain_text('长方形面积')
            assert page.evaluate("localStorage.getItem('mathguide.session')") is None
            # An expired session should clear the same way instead of retaining old text.
            send('长方形长12米宽8米，面积是多少？')
            page.route('**/api/sessions/abort', lambda route: route.fulfill(status=404, json={'detail':'会话已过期'}))
            page.locator('#new').click()
            expect(page.locator('#chat')).to_be_empty()
            page.unroute('**/api/sessions/abort')
            checks.append('Live notes update per reply, restore after refresh, clear on new and completed questions; failed abort preserves the conversation')
            assert not errors, errors
            browser.close()
        for check in checks:
            print('PASS:', check, flush=True)
    finally:
        server.terminate()
        server.wait(timeout=15)
        (output / 'results.json').write_text(json.dumps({'checks':checks, 'errors':errors},
            ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
