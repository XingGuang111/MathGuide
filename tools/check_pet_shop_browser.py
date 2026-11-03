"""Check every new food and toy through the real shop using isolated records."""
import argparse
import json
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import db
import pet
import pet_energy
from pet_shop import ITEMS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / '.pet-qa/shop-browser')
    output = parser.parse_args().output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    path = str(output / (uuid.uuid4().hex + '.db'))
    db.init_db(path)
    profile = 'shop-browser-check'
    for i in range(25): pet.reward(profile, str(i), points=100, xp=0, db_path=path)
    pet.reward(profile, 'play-window', points=0, xp=0, db_path=path, energy_target=20, energy_day=pet_energy.today())
    pet.start_play(profile, path)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
    code = f"import config;config.DB_PATH={path!r};import web_app,uvicorn;web_app.llm.check_health=lambda:None;uvicorn.run(web_app.app,host='127.0.0.1',port={port},log_level='warning')"
    server = subprocess.Popen([sys.executable, '-c', code], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f'http://127.0.0.1:{port}'
    result = {'passed': False, 'items': [], 'errors': [], 'uses_isolated_database': True}
    page = None
    try:
        for _ in range(80):
            try:
                urllib.request.urlopen(base, timeout=1).close(); break
            except OSError:
                if server.poll() is not None: raise RuntimeError('Preview exited')
                time.sleep(.25)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={'width': 1440, 'height': 1050})
            context.add_init_script(f"localStorage.setItem('mathguide.petProfile','{profile}')")
            page = context.new_page()
            page.on('pageerror', lambda error: result['errors'].append(str(error)))
            page.goto(base + '/?view=shop')
            expect(page.locator('#shop-balance')).to_have_text('我的星星 2500 ⭐')
            expect(page.locator('#shop-grid article')).to_have_count(30)
            page.locator('[data-item-filter="food"]').click()
            expect(page.locator('#shop-grid article')).to_have_count(13)
            page.screenshot(path=str(output / 'shop-daily-desktop.png'), full_page=True)
            page.locator('[data-item-filter="festival"]').click()
            expect(page.locator('#shop-grid article')).to_have_count(8)
            page.screenshot(path=str(output / 'shop-festival-desktop.png'), full_page=True)
            page.locator('[data-item-filter="owned"]').click()
            expect(page.locator('.shop-empty')).to_have_count(2)
            expect(page.locator('.shop-empty').first).to_be_visible()
            page.locator('[data-item-filter="all"]').click()
            balance = 2500
            for index, (key, item) in enumerate(ITEMS.items()):
                if item['kind'] == 'toy':
                    # QA-only reset, never touches a student's progress or balance.
                    pet.reward(profile, 'toy-check-' + key, points=0, xp=0, db_path=path)
                    page.reload()
                    expect(page.locator('#shop-balance')).to_have_text(f'我的星星 {balance} ⭐')
                    expect(page.locator('#pet-card')).to_have_attribute('data-focus', 'false')
                image = page.locator(f'[data-item="{key}"] > img')
                image.scroll_into_view_if_needed()
                expect(image).to_have_js_property('complete', True)
                assert image.evaluate('image=>image.naturalWidth') == 256
                page.locator(f'[data-buy="{key}"]').click()
                balance -= item['price']
                expect(page.locator('#shop-balance')).to_have_text(f'我的星星 {balance} ⭐')
                expect(page.locator(f'[data-use="{key}"]')).to_be_enabled()
                with page.expect_response(lambda response: response.url.endswith('/api/pet/interact')) as response:
                    page.locator(f'[data-use="{key}"]').click()
                data = response.value.json()
                assert data['item']['animation'] == item['animation']
                expect(page.locator('#pet-avatar')).to_have_attribute('data-animation', item['animation'])
                page.wait_for_function('''clip=>{
                    const v=document.querySelector('#pet-video');
                    return v.src.endsWith('/'+clip+'.webm')&&v.readyState>=2&&v.currentTime>.15&&!v.error;
                }''', arg=item['animation'])
                expect(page.locator('#pet-prop')).to_be_hidden()
                if item['kind'] == 'food':
                    assert key not in data['pet']['inventory']
                    expect(page.locator(f'[data-use="{key}"]')).to_be_disabled()
                else:
                    assert data['pet']['inventory'][key] == 1
                    expect(page.locator(f'[data-buy="{key}"]')).to_be_disabled()
                if key in ['icecream', 'watermelon', 'hotpot', 'cube']:
                    page.evaluate("()=>{const v=document.querySelector('#pet-video');v.currentTime=4.5}")
                    page.wait_for_timeout(200)
                    page.screenshot(path=str(output / (key + '-feeding.png')))
                result['items'].append({'id': key, 'animation': item['animation'], 'passed': True})
                print('PASS:', key, 'purchase, mapped clip, inventory and video decode', flush=True)
            page.reload()
            expect(page.locator('#shop-balance')).to_have_text(f'我的星星 {balance} ⭐')
            page.locator('[data-item-filter="owned"]').click()
            expect(page.locator('#shop-grid article')).to_have_count(7)
            expect(page.locator('[data-buy="cube"]')).to_be_disabled()
            # Prepare owned food and check right-click feeding from another view.
            page.locator('[data-item-filter="food"]').click()
            page.locator('[data-buy="watermelon"]').click(); balance -= ITEMS['watermelon']['price']
            expect(page.locator('#shop-balance')).to_have_text(f'我的星星 {balance} ⭐')
            page.locator('#tutor-tab').click()
            page.locator('#pet-avatar').click(button='right')
            expect(page.locator('#pet-context-menu')).to_be_visible()
            page.locator('#pet-context-menu').get_by_role('button', name='清甜西瓜 ×1', exact=True).click()
            expect(page.locator('#pet-avatar')).to_have_attribute('data-animation', 'food_watermelon')
            mobile = browser.new_context(viewport={'width':390,'height':844}, is_mobile=True, has_touch=True)
            mobile.add_init_script(f"localStorage.setItem('mathguide.petProfile','{profile}')")
            phone = mobile.new_page(); phone.on('pageerror', lambda error: result['errors'].append(str(error)))
            phone.goto(base + '/?view=shop')
            expect(phone.locator('#shop-grid article')).to_have_count(30)
            phone.locator('[data-item-filter="food"]').click()
            expect(phone.locator('[data-item="icecream"]')).to_be_visible()
            phone.screenshot(path=str(output / 'shop-food-mobile.png'), full_page=True)
            phone.locator('[data-item-filter="festival"]').click()
            expect(phone.locator('#shop-grid article')).to_have_count(8)
            phone.screenshot(path=str(output / 'shop-festival-mobile.png'), full_page=True)
            phone.locator('[data-item-filter="toy"]').click()
            expect(phone.locator('#shop-grid article')).to_have_count(9)
            assert phone.evaluate('document.documentElement.scrollWidth<=innerWidth'), 'Mobile horizontal overflow'
            assert not result['errors'], result['errors']
            mobile.close(); context.close(); browser.close()
            result['passed'] = True
    except Exception as exc:
        result['errors'].append(str(exc))
        if page:
            try: page.screenshot(path=str(output / 'failure.png'), full_page=True)
            except Exception: pass
        raise
    finally:
        server.terminate(); server.wait(timeout=15)
        (output / 'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__ == '__main__':
    main()
