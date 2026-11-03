"""Run real-browser pet checks against an isolated database and local server.

Requires the optional Playwright package and an installed Chromium browser.
No student records or balances are modified.
"""
import argparse
from datetime import datetime
import json
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request
import uuid
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright, expect
import db
import pet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / '.pet-qa')
    parser.add_argument('--record-video', action='store_true')
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    result = {'started': datetime.now().astimezone().isoformat(), 'passed': False,
              'model_responses_mocked': True, 'checkpoints': [], 'errors': []}
    page = None

    def checkpoint(label):
        result['checkpoints'].append(label)
        print('PASS:', label, flush=True)

    path = str(output / ('browser-' + uuid.uuid4().hex + '.db'))
    db.init_db(path)
    pet.reward('pet-browser-check', 'initial', points=100, xp=0, db_path=path)
    for i in range(6):
        pet.reward('pet-browser-grown', str(i), points=100, db_path=path)
        pet.reward('pet-browser-collection', str(i), points=100, xp=0, db_path=path)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    code = f"import config; config.DB_PATH={path!r}; import web_app,uvicorn; web_app.llm.check_health=lambda:None; web_app.llm.pet_reply=lambda messages:'我陪你一步一步来，先读一遍题目吧。'; uvicorn.run(web_app.app,host='127.0.0.1',port={port},log_level='warning')"
    server = subprocess.Popen([sys.executable, '-c', code], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f'http://127.0.0.1:{port}'
    try:
        for _ in range(60):
            try:
                with urllib.request.urlopen(base, timeout=1):
                    break
            except OSError:
                if server.poll() is not None:
                    raise RuntimeError('Preview server exited')
                time.sleep(.5)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            recording = {'record_video_dir': str(output / 'videos')} if args.record_video else {}
            context = browser.new_context(viewport={'width': 1366, 'height': 1000}, **recording)
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('pageerror', lambda error: print('PAGE ERROR:', str(error), flush=True))
            page.add_init_script("localStorage.setItem('mathguide.petProfile','pet-browser-check')")
            page.goto(base)
            expect(page.locator('#pet-coins')).to_have_text('⭐ 100')
            page.wait_for_function("document.querySelector('#pet-video').readyState>=2 && document.querySelector('#pet-video').currentTime>0")
            page.screenshot(path=str(output / 'pet-desktop.png'))
            with page.expect_response(lambda response: response.url.endswith('/api/pet/touch')):
                page.locator('#pet-touch').click()
            expect(page.locator('#pet-avatar')).to_have_attribute('data-animation', __import__('re').compile('touch|wave'))
            box = page.locator('#pet-avatar').bounding_box()
            page.mouse.move(box['x'] + 90, box['y'] + 90)
            page.mouse.down()
            page.mouse.move(520, 310, steps=10)
            page.mouse.up()
            expect(page.locator('#pet-avatar')).to_have_class(__import__('re').compile('floating'))
            page.locator('#pet-home').click()
            expect(page.locator('#pet-home')).to_be_hidden()
            page.locator('#pet-shop').click()
            page.locator('[data-buy="biscuit"]').click()
            expect(page.locator('#shop-balance')).to_have_text('我的星星 90 ⭐')
            page.locator('[data-use="biscuit"]').click()
            expect(page.locator('#pet-dialog')).not_to_be_visible()
            expect(page.locator('#pet-avatar')).to_have_attribute('data-animation', 'eat')
            page.wait_for_function("document.querySelector('#pet-video').currentTime>0")
            page.screenshot(path=str(output / 'pet-feeding.png'))
            page.locator('#pet-play').click()
            page.locator('[data-buy="ball"]').click()
            expect(page.locator('#shop-balance')).to_have_text('我的星星 50 ⭐')
            page.locator('[data-use="ball"]').click()
            expect(page.locator('#pet-avatar')).to_have_attribute('data-animation', 'play')
            page.locator('#pet-shop').click()
            expect(page.locator('[data-buy="ball"]')).to_be_disabled()
            expect(page.locator('[data-use="ball"]')).to_be_enabled()
            page.screenshot(path=str(output / 'pet-shop.png'))
            page.locator('#pet-dialog-close').click()
            page.reload()
            expect(page.locator('#pet-coins')).to_have_text('⭐ 50')
            checkpoint('桌面动画、拖动归位、购买喂食、玩具复用和余额刷新恢复')
            # Chat is distinct from tutoring and safely displays user text.
            page.locator('#pet-chat-toggle').click()
            page.locator('#pet-chat-input').fill('这题好难 <b>给我加油</b>')
            page.locator('#pet-chat-send').click()
            expect(page.locator('#pet-chat-log .pet-chat-line')).to_have_count(2)
            expect(page.locator('#pet-chat-status')).to_have_text('由本地模型回复')
            expect(page.locator('#pet-card')).to_have_attribute('data-emotion', 'crying')
            expect(page.locator('#pet-avatar > .pet-emotion-effects')).to_be_visible()
            expect(page.locator('#pet-chat-log b')).to_have_count(0)
            page.locator('#pet-card').screenshot(path=str(output / 'pet-chat-desktop.png'))
            checkpoint('陪伴对话、困难情绪和用户文本安全显示（模型回复使用替身）')
            # A new verified learning event resets the initial touch used for animation QA.
            pet.reward('pet-browser-check', 'before-focus-check', points=0, xp=0, db_path=path)
            # The fourth touch pauses play; reloading must preserve the reminder.
            for index in range(4):
                with page.expect_response(lambda response: response.url.endswith('/api/pet/touch')):
                    page.locator('#pet-touch').click()
            expect(page.locator('#pet-study')).to_be_visible()
            expect(page.locator('#pet-message')).to_contain_text('先做一道题')
            page.locator('#pet-play').click()
            expect(page.locator('#pet-dialog')).not_to_be_visible()
            expect(page.locator('#pet-avatar')).to_have_attribute('data-animation', 'idle')
            expect(page.locator('#pet-card')).to_have_attribute('data-emotion', 'coax')
            for _ in range(3):
                with page.expect_response(lambda response: response.url.endswith('/api/pet/touch')):
                    page.locator('#pet-touch').click()
            expect(page.locator('#pet-card')).to_have_attribute('data-emotion', 'coax')
            expect(page.locator('#pet-avatar')).to_have_attribute('data-expression', 'coax')
            assert 'expression-coax.svg' in page.locator('#pet-avatar').evaluate("node=>getComputedStyle(node,'::after').backgroundImage")
            page.locator('#pet-card').screenshot(path=str(output / 'pet-gentle-reminder.png'))
            page.reload()
            expect(page.locator('#pet-study')).to_be_visible()
            expect(page.locator('#pet-card')).to_have_attribute('data-emotion', 'coax')
            page.locator('#pet-card').screenshot(path=str(output / 'pet-focus.png'))
            checkpoint('连续互动保持温柔催学、鼓腮效果已移除、刷新后提醒保留')
            # Submit an actual practice from the existing learning UI and verify automatic reward.
            page.locator('#pet-study').click()
            expect(page.locator('#practice-question')).not_to_be_empty()
            exercise_id = page.evaluate("localStorage.getItem('mathguide.practice')")
            with sqlite3.connect(path) as connection:
                answer = json.loads(connection.execute('SELECT payload FROM practice_exercise WHERE id=?', (exercise_id,)).fetchone()[0])['expected']
            page.locator('#practice-answer').fill(answer)
            page.locator('#practice-submit').click()
            expect(page.locator('#pet-coins')).to_have_text('⭐ 60')
            expect(page.locator('#pet-study')).to_be_hidden()
            expect(page.locator('#practice-pet-reaction')).to_have_attribute('data-emotion', 'smile')
            checkpoint('实际练习答对后自动奖励并恢复互动')
            # Verified wrong answers show concern/tears, then three successes produce laughter.
            for index, correct in enumerate([False, False, True, True, True]):
                page.locator('#practice-next').click()
                expect(page.locator('#practice-form')).to_be_visible()
                exercise_id = page.evaluate("localStorage.getItem('mathguide.practice')")
                with sqlite3.connect(path) as connection:
                    answer = json.loads(connection.execute('SELECT payload FROM practice_exercise WHERE id=?', (exercise_id,)).fetchone()[0])['expected']
                answer = answer if correct else str(Fraction(answer) + 1)
                with page.expect_response(lambda response: response.url.endswith('/api/pet/reward')):
                    page.locator('#practice-answer').fill(answer)
                    page.locator('#practice-submit').click()
                emotion = ['concerned', 'crying', 'smile', 'smile', 'laugh'][index]
                expect(page.locator('#practice-pet-reaction')).to_have_attribute('data-emotion', emotion)
                if emotion in ['crying', 'laugh']:
                    page.locator('#practice-dialog').screenshot(path=str(output / ('pet-practice-' + emotion + '.png')))
            expect(page.locator('#pet-coins')).to_have_text('⭐ 96')
            checkpoint('两次答错后的共情、连续三次答对后的大笑及奖励核对')
            page.locator('#practice-close').click()
            page.locator('#pet-play').click()
            page.locator('[data-use="ball"]').click()
            expect(page.locator('#pet-avatar')).to_have_attribute('data-animation', 'play')
            page.locator('#pet-chat-toggle').click()
            expect(page.locator('#pet-chat-log .pet-chat-line')).to_have_count(3)
            page.locator('#pet-collapse').click()
            expect(page.locator('#pet-scene')).to_be_hidden()
            page.locator('#pet-collapse').click()
            expect(page.locator('#pet-scene')).to_be_visible()
            checkpoint('聊天历史保留、完成练习后玩耍及收起展开')
            # All clips must decode and advance, not just return HTTP 200.
            for clip in ['idle', 'touch', 'wave', 'drag', 'eat', 'play', 'think', 'celebrate', 'sleep', *pet.TRICKS]:
                page.evaluate("name=>{const v=document.querySelector('#pet-video');v.src='/assets/pet/'+name+'.webm';v.load();v.play().catch(()=>{})}", clip)
                page.wait_for_function("document.querySelector('#pet-video').readyState>=2 && document.querySelector('#pet-video').currentTime>0", timeout=15000)
            checkpoint('全部18段动作可解码并播放')
            # A separate profile keeps collection checks independent of learning rewards.
            collection = browser.new_context(viewport={'width': 1366, 'height': 1000})
            collection.add_init_script("localStorage.setItem('mathguide.petProfile','pet-browser-collection')")
            companion = collection.new_page()
            companion.on('pageerror', lambda error: errors.append(str(error)))
            companion.goto(base)
            expect(companion.locator('#pet-coins')).to_have_text('⭐ 600')
            companion.locator('#pet-lessons').click()
            expect(companion.locator('#pet-lessons-grid article')).to_have_count(9)
            companion.locator('[data-learn="stretch"]').click()
            expect(companion.locator('#shop-balance')).to_have_text('我的星星 580 ⭐')
            expect(companion.locator('[data-perform="stretch"]')).to_be_enabled()
            companion.screenshot(path=str(output / 'pet-lessons.png'))
            companion.locator('[data-perform="stretch"]').click()
            expect(companion.locator('#pet-avatar')).to_have_attribute('data-animation', 'stretch')
            companion.wait_for_function("document.querySelector('#pet-video').currentTime>.3")
            expect(companion.locator('#pet-coins')).to_have_text('⭐ 580')
            companion.locator('#pet-wardrobe').click()
            companion.locator('[data-hat-buy="hat_beret"]').click()
            expect(companion.locator('#shop-balance')).to_have_text('我的星星 550 ⭐')
            companion.locator('[data-equip="hat_beret"]').click()
            expect(companion.locator('#pet-hat')).to_be_visible()
            companion.wait_for_function("document.querySelector('#pet-video').currentTime>0")
            companion.screenshot(path=str(output / 'pet-beret.png'))
            companion.reload()
            expect(companion.locator('#pet-coins')).to_have_text('⭐ 550')
            expect(companion.locator('#pet-hat')).to_have_attribute('alt', '莓莓贝雷帽')
            expect(companion.locator('#pet-action-count')).to_have_text('1/9')
            for hat in ['hat_sun', 'hat_wizard']:
                companion.locator('#pet-wardrobe').click()
                companion.locator(f'[data-hat-buy="{hat}"]').click()
                companion.locator(f'[data-equip="{hat}"]').click()
                expect(companion.locator('#pet-hat')).to_have_attribute('src', pet.HATS[hat]['overlay'])
                companion.screenshot(path=str(output / (hat + '.png')))
            companion.locator('#pet-wardrobe').click()
            companion.locator('[data-equip="hat_wizard"]').click()
            expect(companion.locator('#pet-hat')).to_be_hidden()
            companion.locator('#pet-wardrobe').click()
            companion.locator('[data-equip="hat_beret"]').click()
            # The bubble must follow the pet, including when native dialogs are open.
            companion.locator('#practice').click()
            expect(companion.locator('#practice-dialog')).to_be_visible()
            expect(companion.locator('#practice-dialog #pet-overlay')).to_have_count(1)
            expect(companion.locator('#pet-overlay')).to_have_js_property('popover', 'manual')
            box = companion.locator('#pet-avatar').bounding_box()
            companion.mouse.move(box['x']+90, box['y']+90)
            companion.mouse.down()
            companion.mouse.move(1060, 640, steps=10)
            companion.mouse.up()
            expect(companion.locator('#pet-avatar')).to_have_class(__import__('re').compile('floating'))
            moved = companion.locator('#pet-avatar').bounding_box()
            bubble = companion.locator('#pet-message').bounding_box()
            assert bubble['x'] < moved['x'] + 190 and bubble['x'] + bubble['width'] > moved['x']
            assert bubble['y'] < moved['y'] and bubble['y'] + bubble['height'] >= moved['y'] - 30
            hit = companion.evaluate('''()=>{const r=document.querySelector('#pet-avatar').getBoundingClientRect();
                return document.elementFromPoint(r.x+95,r.y+95)?.closest('#pet-avatar')!==null}''')
            assert hit, 'Pet must receive pointer events above the practice dialog'
            companion.locator('#pet-floating-chat-toggle').click()
            companion.locator('#pet-floating-chat input').fill('给我加油')
            companion.locator('#pet-floating-chat button[type="submit"]').click()
            expect(companion.locator('#pet-message')).to_contain_text('先读一遍题目')
            companion.locator('#pet-floating-chat button[type="button"]').click()
            expect(companion.locator('#practice-pet-hat')).to_be_visible()
            companion.wait_for_function("document.querySelector('#pet-video').readyState>=2 && document.querySelector('#practice-pet-video').readyState>=2")
            companion.wait_for_timeout(300)
            companion.screenshot(path=str(output / 'pet-dialog-overlay.png'))
            companion.locator('#practice-close').click()
            expect(companion.locator('body > #pet-overlay')).to_have_count(1)
            companion.locator('#pet-floating-home').click()
            expect(companion.locator('#pet-avatar')).not_to_have_class(__import__('re').compile('floating'))
            companion.locator('#pet-avatar').click(button='right')
            expect(companion.locator('#pet-context-menu')).to_be_visible()
            companion.screenshot(path=str(output / 'pet-right-click-menu.png'))
            companion.locator('#pet-context-menu').get_by_role('button', name='摘下 莓莓贝雷帽', exact=True).click()
            expect(companion.locator('#pet-hat')).to_be_hidden()
            companion.locator('#pet-avatar').click(button='right')
            companion.locator('#pet-context-menu').get_by_role('button', name='戴上 莓莓贝雷帽', exact=True).click()
            expect(companion.locator('#pet-hat')).to_be_visible()
            companion.locator('#pet-avatar').click(button='right')
            companion.locator('#pet-context-menu').get_by_role('button', name='🍪 买食物', exact=True).click()
            companion.locator('[data-buy="biscuit"]').click()
            expect(companion.locator('#shop-balance')).to_have_text('我的星星 440 ⭐')
            companion.locator('#pet-dialog-close').click()
            companion.locator('#pet-avatar').click(button='right')
            companion.locator('#pet-context-menu').get_by_role('button', name='星星饼干 ×1', exact=True).click()
            expect(companion.locator('#pet-avatar')).to_have_attribute('data-animation', 'eat')
            companion.locator('#pet-avatar').click(button='right')
            companion.locator('#pet-context-menu').get_by_role('button', name='🙆 大大伸懒腰', exact=True).click()
            expect(companion.locator('#pet-avatar')).to_have_attribute('data-animation', 'stretch')
            companion.wait_for_function("document.querySelector('#pet-video').currentTime>1")
            companion.screenshot(path=str(output / 'pet-hat-action.png'))
            companion.locator('#pet-menu-toggle').click()
            companion.keyboard.press('Escape')
            expect(companion.locator('#pet-context-menu')).to_be_hidden()
            checkpoint('右键菜单喂食、动作、换帽子和键盘关闭')
            checkpoint('动作花星星学习、免费表演、三顶帽子购买换戴摘下、刷新恢复及随宠物移动的顶层气泡对话')
            collection.close()
            mobile = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, **recording)
            mobile.add_init_script("localStorage.setItem('mathguide.petProfile','pet-browser-grown')")
            phone = mobile.new_page()
            phone.on('pageerror', lambda error: errors.append(str(error)))
            phone.goto(base)
            expect(phone.locator('#pet-stage')).to_have_text('Lv.4 · 星光伙伴')
            phone.locator('#pet-card').scroll_into_view_if_needed()
            expect(phone.locator('#pet-crown')).to_be_visible()
            phone.wait_for_function("document.querySelector('#pet-video').currentTime>0")
            assert phone.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile horizontal overflow'
            phone.screenshot(path=str(output / 'pet-mobile.png'))
            phone.locator('#pet-shop').click()
            phone.screenshot(path=str(output / 'pet-mobile-shop.png'))
            phone.locator('#pet-tab-actions').click()
            expect(phone.locator('#pet-lessons-grid article')).to_have_count(9)
            phone.screenshot(path=str(output / 'pet-mobile-lessons.png'))
            phone.locator('#pet-tab-hats').click()
            phone.locator('[data-hat-buy="hat_sun"]').click()
            phone.locator('[data-equip="hat_sun"]').click()
            expect(phone.locator('#pet-hat')).to_be_visible()
            expect(phone.locator('#pet-crown')).to_be_hidden()
            phone.screenshot(path=str(output / 'pet-mobile-hat.png'))
            phone.locator('#pet-shop').click()
            phone.locator('#pet-dialog-close').click()
            phone.locator('#pet-chat-toggle').click()
            phone.locator('[data-pet-say="给我加加油吧！"]').click()
            expect(phone.locator('#pet-chat-status')).to_have_text('由本地模型回复')
            assert phone.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Chat horizontal overflow'
            phone.locator('#pet-card').screenshot(path=str(output / 'pet-chat-mobile.png'))
            phone.locator('#pet-menu-toggle').click()
            expect(phone.locator('#pet-context-menu')).to_be_visible()
            phone.screenshot(path=str(output / 'pet-mobile-context-menu.png'))
            phone.locator('#pet-context-menu').get_by_role('button', name='关闭', exact=True).click()
            assert not errors, errors
            checkpoint('390像素移动布局、星冠成长、商店和聊天均无横向溢出或页面脚本异常')
            result['passed'] = True
            print('PASS: 18 clips, action lessons, permanent hats, top-layer pet and speech bubble, learning rewards, emotions, desktop/mobile layout.')
            mobile.close()
            context.close()
            browser.close()
    except Exception as exc:
        result['errors'].append(str(exc))
        if page is not None:
            try:
                page.screenshot(path=str(output / 'failure.png'), full_page=True)
            except Exception:
                pass
        raise
    finally:
        server.terminate()
        server.wait(timeout=15)
        result['finished'] = datetime.now().astimezone().isoformat()
        (output / 'browser-results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
