"""Exercise learning-earned play, reloads, expiry, mobile and multiple tabs."""
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import uuid

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import db
import pet


def main():
    output = ROOT / '.pet-qa/energy-browser'
    output.mkdir(parents=True, exist_ok=True)
    database = str(output / (uuid.uuid4().hex + '.db'))
    db.init_db(database)
    profile = 'energy-browser'
    # Shop funds/ownership are independent of energy. Learning below is real.
    pet.reward(profile, 'fixture-stars', points=100, db_path=database)
    pet.purchase(profile, 'biscuit', database)
    pet.purchase(profile, 'ball', database)
    pet.learn(profile, 'stretch', database)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
    code = f"import config;config.DB_PATH={database!r};import web_app,uvicorn;web_app.llm.check_health=lambda:None;web_app.llm.pet_reply=lambda messages:'我陪你一步一步想。先看看题目告诉了我们什么。';uvicorn.run(web_app.app,host='127.0.0.1',port={port},log_level='warning')"
    server = subprocess.Popen([sys.executable, '-c', code], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f'http://127.0.0.1:{port}'
    result = {'passed': False, 'checks': [], 'errors': [], 'isolated_database': True}
    try:
        for _ in range(80):
            try:
                urllib.request.urlopen(base, timeout=1).close(); break
            except OSError:
                if server.poll() is not None: raise RuntimeError('Preview exited')
                time.sleep(.25)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={'width': 1440, 'height': 1000})
            context.add_init_script(f"localStorage.setItem('mathguide.petProfile',{profile!r})")
            page = context.new_page()
            page.on('pageerror', lambda error: result['errors'].append(str(error)))
            page.goto(base + '/?view=shop')
            expect(page.locator('#pet-energy-value')).to_have_text('今日活力 0 / 40')
            expect(page.locator('#pet-energy-start')).to_be_disabled()
            for _ in range(6):
                with page.expect_response(lambda r: r.url.endswith('/api/pet/touch')):
                    page.locator('#pet-touch').click()
            expect(page.locator('#pet-avatar')).to_have_attribute('data-animation', 'idle')
            page.locator('[data-use="biscuit"]').click()
            assert pet.get(profile, database)['inventory']['biscuit'] == 1
            result['checks'].append('zero energy: quiet touch, food preserved, no old click lock')
            page.screenshot(path=str(output / 'quiet-desktop.png'))

            # Student completes an actual practice question through the UI.
            page.locator('#pet-energy-study').click()
            page.wait_for_function("localStorage.getItem('mathguide.practice') !== null")
            expect(page.locator('#practice-answer')).to_be_editable()
            eid = page.evaluate("localStorage.getItem('mathguide.practice')")
            with db._conn(database) as conn:
                answer = json.loads(conn.execute('SELECT payload FROM practice_exercise WHERE id=?', (eid,)).fetchone()[0])['expected']
            page.locator('#practice-answer').fill(str(answer))
            with page.expect_response(lambda r: r.url.endswith('/api/pet/reward')):
                page.locator('#practice-submit').click()
            page.locator('#practice-close').click()
            page.evaluate("window.MathGuideWorkspace.show('shop')")
            expect(page.locator('#pet-energy-value')).to_have_text('今日活力 20 / 40')
            page.reload()
            expect(page.locator('#pet-energy-value')).to_have_text('今日活力 20 / 40')
            result['checks'].append('verified practice earns 20, reload keeps unspent energy')

            page.locator('#pet-energy-start').click()
            expect(page.locator('#pet-energy-status')).to_contain_text('玩耍剩余')
            expect(page.locator('#pet-energy-value')).to_have_text('今日活力 0 / 40')
            second = context.new_page(); second.goto(base + '/?view=shop')
            expect(second.locator('#pet-energy-status')).to_contain_text('玩耍剩余')
            expect(second.locator('#pet-energy-start')).to_be_disabled()
            page.reload()
            expect(page.locator('#pet-energy-status')).to_contain_text('玩耍剩余')
            assert pet.get(profile, database)['energy']['available_seconds'] == 480
            result['checks'].append('paid countdown survives reload and is shared by multiple tabs')

            avatar = page.locator('#pet-avatar')
            box = avatar.bounding_box()
            page.mouse.move(box['x']+95, box['y']+100); page.mouse.down()
            page.mouse.move(210, 400, steps=12); page.mouse.up()
            page.wait_for_timeout(300)
            anchor = page.locator('.pet-floater').bounding_box()
            for _ in range(6):
                with page.expect_response(lambda r: r.url.endswith('/api/pet/touch')):
                    page.locator('#pet-touch').click()
            page.locator('[data-use="biscuit"]').click()
            expect(avatar).to_have_attribute('data-animation', 'eat')
            page.locator('[data-use="ball"]').click()
            expect(avatar).to_have_attribute('data-animation', 'play')
            page.locator('#pet-tab-actions').click()
            page.locator('[data-perform="stretch"]').click()
            expect(avatar).to_have_attribute('data-animation', 'stretch')
            page.wait_for_function("document.querySelector('#pet-video').readyState>=2")
            current = page.locator('.pet-floater').bounding_box()
            assert abs(anchor['x']-current['x'])<1 and abs(anchor['y']-current['y'])<1
            result['checks'].append('many touches, feeding, toys and learned actions keep position within the window')
            page.screenshot(path=str(output / 'playing-desktop.png'))

            # Expire the test save naturally in two seconds; real duration stays 120.
            with db._conn(database) as conn:
                conn.execute('UPDATE pet_energy SET play_until=? WHERE profile_id=?', (time.time()+2, profile))
            page.locator('#pet-retry').click()
            expect(page.locator('#pet-energy-status')).to_contain_text('安静陪学', timeout=6000)
            expect(avatar).to_have_attribute('data-animation', 'idle')
            page.locator('[data-perform="stretch"]').click()
            expect(avatar).to_have_attribute('data-animation', 'idle')
            page.locator('#pet-chat-toggle').click()
            page.locator('#pet-chat-input').fill('这题好难，可以给我加油吗？')
            page.locator('#pet-chat-send').click()
            expect(page.locator('#pet-chat-log')).to_contain_text('我陪你一步一步想')
            result['checks'].append('expiry stops entertainment; learning chat remains available')
            page.set_viewport_size({'width': 390, 'height': 844})
            page.locator('#pet-energy-value').scroll_into_view_if_needed()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(output / 'quiet-mobile.png'))
            assert not result['errors'], result['errors']
            result['passed'] = True
            browser.close()
    finally:
        server.terminate(); server.wait(timeout=10)
        (output / 'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
