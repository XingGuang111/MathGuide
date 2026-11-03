"""Exercise a supplied photographed worksheet against real local OCR and vision."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image',type=Path)
    parser.add_argument('--question',type=int,default=3)
    parser.add_argument('--answer',default='B')
    parser.add_argument('--count',type=int,default=5)
    args=parser.parse_args()
    from fastapi.testclient import TestClient
    import config
    import vision
    output=ROOT/'.pet-qa'/'homework-vision'
    output.mkdir(parents=True,exist_ok=True)
    config.DB_PATH=str(output/('picture-'+uuid.uuid4().hex[:8]+'.db'))
    import web_app
    assert vision.status()['ok'],'Local vision model is not ready'
    with TestClient(web_app.app) as client:
        response=client.post('/api/homework/sources',files={'image':('worksheet.png',args.image.read_bytes(),'image/png')})
        assert response.status_code==200,response.text
        source=response.json()
        response=client.post('/api/homework/sources/'+source['id']+'/recognize')
        recognized=response.json()
        questions=recognized['result']['questions']
        assert len(questions)==args.count,questions
        items=[dict(id='image-'+str(index),text=row['text'],source_ids=[source['id']],source_regions=row['source_regions'],answer=args.answer if index==args.question-1 else '') for index,row in enumerate(questions)]
        payload=dict(revision=0,title='带图作业实测（隔离档案）',date='2026-11-01',items=items,source_ids=[source['id']],active=items[args.question-1]['id'])
        response=client.put('/api/homework/assignments/picture-regression',json=payload)
        assert response.status_code==200,response.text
        item=items[args.question-1]
        response=client.post('/api/homework/reviews',json=dict(item_id=item['id'],title=payload['title'],assignment_date=payload['date'],question=item['text'],answer=args.answer))
        assert response.status_code==200,response.text
        review=response.json()
        assert review['analysis']['verification']=='local_vision'
        assert review['attachments']
        print('PASS real picture analysis:',review['analysis']['verdict'],flush=True)
        response=client.post('/api/homework/items/'+item['id']+'/visual-tutor',json=dict(message='请先读题，确认这道题要求找正确的点还是不正确的点，不要直接给选项。',request_id=uuid.uuid4().hex))
        assert response.status_code==200,response.text
        reply=response.json()
        print('PASS real picture guidance:',reply['reply'],flush=True)
        reading=client.post('/api/homework/vision/read',json=item['source_regions'][0])
        assert reading.status_code==200,reading.text
        result=dict(passed=True,question_count=len(questions),review=review,reply=reply,reading=reading.json(),database=config.DB_PATH)
        (output/'real-picture-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    command=f'import config;config.DB_PATH={config.DB_PATH!r};import uvicorn;uvicorn.run("web_app:app",host="127.0.0.1",port={port})'
    with (output/'browser-server.log').open('w',encoding='utf-8') as log:
        server=subprocess.Popen([sys.executable,'-X','utf8','-c',command],cwd=ROOT,stdout=log,stderr=log,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        try:
            for _ in range(100):
                try:urllib.request.urlopen(base,timeout=1).close();break
                except OSError:time.sleep(.2)
            from playwright.sync_api import sync_playwright,expect
            with sync_playwright() as p:
                browser=p.chromium.launch()
                page=browser.new_page(viewport={'width':1440,'height':1050})
                errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(base+'/?view=homework&assignment=picture-regression')
                expect(page.locator('.hw-item')).to_have_count(args.count)
                expect(page.locator('#hw-visual-messages .teacher')).to_have_count(1)
                expect(page.locator('#hw-question-images img')).to_be_visible()
                page.locator('#hw-question-images img').evaluate('(image)=>image.decode()')
                page.screenshot(path=str(output/'picture-student-desktop.png'),full_page=True)
                page.locator('[data-zoom-region]').click()
                expect(page.locator('#hw-source-dialog')).to_be_visible()
                page.locator('#hw-source-dialog').screenshot(path=str(output/'picture-zoom.png'))
                page.locator('#hw-source-close').click()
                page.locator('#hw-parent-mode').click()
                expect(page.locator('.hw-editor-figure img')).to_have_count(args.count)
                page.locator('.hw-edit-row [data-source]').nth(args.question-1).click()
                expect(page.locator('#hw-crop-controls')).to_be_visible()
                page.locator('#hw-source-close').click()
                page.screenshot(path=str(output/'picture-parent-desktop.png'),full_page=True)
                page.set_viewport_size({'width':390,'height':844})
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                page.locator('#hw-student-mode').click()
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                page.screenshot(path=str(output/'picture-student-mobile.png'),full_page=True)
                assert not errors,errors
                browser.close()
            print('PASS original question crops, zoom, parent correction, and mobile layout',flush=True)
        finally:
            server.terminate();server.wait(timeout=15)


if __name__=='__main__':
    main()
