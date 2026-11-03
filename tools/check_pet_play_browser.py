"""Exercise the play lessons, hat and category layout in an isolated save."""
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

PLAY = ['flute', 'violin', 'sway_dance', 'cute_dance', 'grace_dance',
        'dove_magic', 'card_magic', 'flower_magic', 'juggle', 'shuttlecock',
        'gomoku', 'pet_cat', 'animals', 'garden', 'whale', 'gift', 'jump_catch']


def main():
    output = ROOT / '.pet-qa/play-browser'
    output.mkdir(parents=True, exist_ok=True)
    database = str(output / (uuid.uuid4().hex + '.db'))
    db.init_db(database)
    profile = pet.prepare_test_profile(database)['pet']['profile_id']
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    code = f"import config;config.DB_PATH={database!r};import web_app,uvicorn;web_app.llm.check_health=lambda:None;uvicorn.run(web_app.app,host='127.0.0.1',port={port},log_level='warning')"
    server = subprocess.Popen([sys.executable, '-c', code], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f'http://127.0.0.1:{port}'
    result = {'passed': False, 'actions': [], 'errors': [], 'isolated_database': True}
    try:
        for _ in range(80):
            try:
                urllib.request.urlopen(base, timeout=1).close()
                break
            except OSError:
                if server.poll() is not None:
                    raise RuntimeError('Preview exited')
                time.sleep(.25)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={'width': 1440, 'height': 1000})
            context.add_init_script(f"localStorage.setItem('mathguide.petProfile',{profile!r})")
            page = context.new_page()
            page.on('pageerror', lambda error: result['errors'].append(str(error)))
            page.goto(base + '/?view=shop')
            expect(page.locator('#shop-grid article')).to_have_count(30)
            food = page.locator('[data-category="food"]')
            toy = page.locator('[data-category="toy"]')
            expect(food.locator('article')).to_have_count(21)
            expect(toy.locator('article')).to_have_count(9)
            a, b = food.bounding_box(), toy.bounding_box()
            assert abs(a['y']-b['y']) < 1 and a['x']+a['width'] < b['x']
            page.screenshot(path=str(output / 'food-toy-columns.png'), full_page=True)
            pet_node = page.locator('#pet-avatar')
            box = pet_node.bounding_box()
            page.mouse.move(box['x']+95, box['y']+110)
            page.mouse.down()
            page.mouse.move(160, 400, steps=15)
            page.mouse.up()
            anchor = page.locator('.pet-floater').bounding_box()

            def stationary():
                box = page.locator('.pet-floater').bounding_box()
                assert abs(box['x']-anchor['x']) < 1 and abs(box['y']-anchor['y']) < 1

            page.locator('#pet-tab-hats').click()
            with page.expect_response(lambda r: r.url.endswith('/api/pet/purchase')):
                page.locator('[data-hat-buy="hat_beret"]').click()
            with page.expect_response(lambda r: r.url.endswith('/api/pet/equip')):
                page.locator('[data-equip="hat_beret"]').click()
            expect(page.locator('#pet-hat')).to_have_attribute('src', '/assets/hats/hat_beret-worn.svg')
            page.wait_for_function("document.querySelector('#pet-hat').naturalWidth > 0")
            stationary()
            pet_node.screenshot(path=str(output / 'hat.png'))
            page.locator('#pet-tab-actions').click()
            expect(page.locator('#pet-lessons-grid article')).to_have_count(26)
            balance = 9970
            for key in PLAY:
                with page.expect_response(lambda r: r.url.endswith('/api/pet/learn')) as response:
                    page.locator(f'[data-learn="{key}"]').click()
                balance -= pet.TRICKS[key]['price']
                assert response.value.json()['pet']['coins'] == balance
                with page.expect_response(lambda r: r.url.endswith('/api/pet/perform')) as response:
                    page.locator(f'[data-perform="{key}"]').click()
                assert response.value.json()['pet']['coins'] == balance
                expect(pet_node).to_have_attribute('data-animation', key)
                page.wait_for_function("key=>{const v=document.querySelector('#pet-video');return v.src.endsWith('/'+key+'.webm')&&v.readyState>=2&&v.currentTime>.15&&!v.error}", arg=key)
                stationary()
                assert key in json.loads((ROOT / 'web/assets/pet/hat-tracks.json').read_text(encoding='utf-8'))
                result['actions'].append(key)
                print(key + ': learned, decoded, free replay, hat and position verified', flush=True)
            page.screenshot(path=str(output / 'play-lessons.png'), full_page=True)
            page.locator('#pet-tab-items').click()
            for width in (760, 390):
                page.set_viewport_size({'width': width, 'height': 900})
                page.wait_for_timeout(150)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                a, b = food.bounding_box(), toy.bounding_box()
                if width == 390:
                    assert b['y'] > a['y']+a['height']
                else:
                    assert abs(a['y']-b['y']) < 1
                page.screenshot(path=str(output / f'shop-{width}.png'), full_page=True)
            assert not result['errors'], result['errors']
            result['passed'] = True
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
        (output / 'results.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
