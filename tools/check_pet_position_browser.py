"""Verify actual dragged pet placement survives interactions and workspace changes."""
import argparse
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / '.pet-qa/pet-position')
    output = parser.parse_args().output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    database = str(output / (uuid.uuid4().hex + '.db'))
    db.init_db(database)
    profile = pet.unlock_entertainment('xingya', database)['pet']['profile_id']
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    code = f"import config;config.DB_PATH={database!r};import web_app,uvicorn;web_app.llm.check_health=lambda:None;web_app.llm.pet_reply=lambda messages:'我陪你一起学习。';uvicorn.run(web_app.app,host='127.0.0.1',port={port},log_level='warning')"
    server = subprocess.Popen([sys.executable, '-c', code], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f'http://127.0.0.1:{port}'
    results = {'passed': False, 'checks': [], 'errors': [], 'uses_isolated_database': True}
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
            context = browser.new_context(viewport={'width':1440,'height':1000})
            context.add_init_script(f"sessionStorage.setItem('mathguide.entertainmentProfile',{profile!r})")
            page = context.new_page()
            page.on('pageerror', lambda error: results['errors'].append(str(error)))
            page.goto(base + '/?view=shop')
            expect(page.locator('[data-use="watermelon"]')).to_be_enabled()
            pet_node = page.locator('#pet-avatar')
            box = pet_node.bounding_box()
            page.mouse.move(box['x']+95, box['y']+110)
            page.mouse.down()
            page.mouse.move(420, 370, steps=15)
            page.mouse.up()
            expect(pet_node).to_have_class('pet-avatar floating')
            anchor = page.locator('.pet-floater').bounding_box()

            def stationary(label):
                page.wait_for_timeout(120)
                current = page.locator('.pet-floater').bounding_box()
                assert abs(current['x']-anchor['x']) < 1, (label, anchor, current)
                assert abs(current['y']-anchor['y']) < 1, (label, anchor, current)
                assert 'floating' in pet_node.get_attribute('class'), label
                results['checks'].append(label)

            def use(selector, endpoint, clip=None):
                with page.expect_response(lambda response: response.url.endswith(endpoint)):
                    page.locator(selector).click()
                if clip:
                    expect(pet_node).to_have_attribute('data-animation', clip)
                    page.wait_for_function("clip=>{const v=document.querySelector('#pet-video');return v.src.endsWith('/'+clip+'.webm')&&v.readyState>=2&&v.currentTime>.1&&!v.error}", arg=clip)

            use('[data-use="watermelon"]', '/api/pet/interact', 'food_watermelon')
            stationary('shop feeding stays at dragged position')
            use('[data-use="cube"]', '/api/pet/interact', 'toy_cube')
            stationary('shop toy stays at dragged position')
            page.locator('#pet-tab-actions').click()
            use('[data-perform="stretch"]', '/api/pet/perform', 'stretch')
            stationary('learned action stays at dragged position')
            page.locator('#pet-tab-hats').click()
            use('[data-equip="hat_beret"]', '/api/pet/equip')
            expect(page.locator('#pet-hat')).to_be_visible()
            stationary('putting on a hat stays at dragged position')
            use('[data-equip="hat_beret"]', '/api/pet/equip')
            expect(page.locator('#pet-hat')).to_be_hidden()
            stationary('taking off a hat stays at dragged position')
            page.locator('#tutor-tab').click()
            stationary('workspace change preserves position')
            pet_node.click(button='right')
            with page.expect_response(lambda response: response.url.endswith('/api/pet/interact')):
                page.locator('#pet-context-menu').get_by_role('button', name='清甜西瓜 ×999', exact=True).click()
            expect(pet_node).to_have_attribute('data-animation','food_watermelon')
            stationary('right-click feeding stays at dragged position')
            page.locator('#shop-tab').click()
            stationary('opening shop preserves position')
            with page.expect_response(lambda response: response.url.endswith('/api/pet/interact')):
                page.locator('#pet-inventory').get_by_role('button',name='清甜西瓜：点击喂食',exact=True).click()
            stationary('backpack feeding stays at dragged position')
            page.set_viewport_size({'width':1300,'height':900})
            stationary('resize preserves an in-bounds position')
            page.screenshot(path=str(output/'pet-in-place.png'))
            page.set_viewport_size({'width':390,'height':844})
            page.wait_for_timeout(150)
            current=page.locator('.pet-floater').bounding_box()
            assert 0 <= current['x'] and current['x']+current['width'] <= 390
            assert 0 <= current['y'] and current['y']+current['height'] <= 844
            results['checks'].append('smaller viewport clamps pet within visible area')
            page.set_viewport_size({'width':1440,'height':1000})
            page.locator('#pet-floating-home').click()
            expect(pet_node).not_to_have_class('pet-avatar floating')
            reset=page.locator('.pet-floater').bounding_box()
            assert abs(reset['x']-1238)<1 and abs(reset['y']-775)<1,reset
            results['checks'].append('explicit reset returns pet to corner')
            assert not results['errors'], results['errors']
            browser.close()
        results['passed']=True
        print(f"PASS: {len(results['checks'])} placement checks, interactions and video playback")
    except Exception as exc:
        results['errors'].append(str(exc))
        raise
    finally:
        server.terminate()
        server.wait(timeout=15)
        (output/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':
    main()
