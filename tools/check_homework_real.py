"""Real RapidOCR and configured Ollama integration, using an isolated database."""
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from PIL import Image, ImageDraw, ImageFont
    from fastapi.testclient import TestClient
    import config
    import llm
    output = ROOT / '.pet-qa' / 'homework'
    output.mkdir(parents=True, exist_ok=True)
    config.DB_PATH = str(output / ('real-flow-' + uuid.uuid4().hex[:8] + '.db'))
    import web_app
    health = llm.check_health()
    if health:
        raise RuntimeError(health)
    sheet = output / 'ocr-real-sheet.png'
    image = Image.new('RGB', (1400, 850), 'white')
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 38)
    for y, text in [(70,'今日数学作业'), (180,'1. 计算：36 ÷ 6 = ?'),
                    (300,'2. 长方形长 8 厘米，宽 5 厘米，'), (370,'面积是多少平方厘米？'),
                    (500,'3. 24 颗糖平均分给 6 个小朋友，'), (570,'每个小朋友分到几颗？')]:
        draw.text((70, y), text, font=font, fill='black')
    image.save(sheet)
    with TestClient(web_app.app) as client:
        with sheet.open('rb') as photo:
            response = client.post('/api/homework/sources', files={'image':('sheet.png',photo,'image/png')})
        assert response.status_code == 200, response.text
        source = response.json()
        recognized = client.post('/api/homework/sources/'+source['id']+'/recognize').json()
        assert recognized['result'], recognized
        questions = recognized['result']['questions']
        assert len(questions) == 3, questions
        payload = dict(revision=0, title='真实联调测试', date='2026-11-01', source_ids=[source['id']],
                       items=[dict(id=f'real-{i}', text=q['text'], answer='6' if i==0 else '', source_ids=[source['id']]) for i,q in enumerate(questions)])
        assert client.put('/api/homework/assignments/real-test', json=payload).status_code == 200
        cases = []
        for item_id, question, answer, verdict in [
            ('real-0', questions[0]['text'], '6', 'correct'),
            ('extra-incorrect', '计算：36÷6=?', '5', 'incorrect'),
            ('extra-figure', '求图中阴影部分的面积。', '12平方厘米', 'uncertain'),
        ]:
            response = client.post('/api/homework/reviews',json=dict(item_id=item_id,title=payload['title'],assignment_date=payload['date'],question=question,answer=answer))
            assert response.status_code == 200, response.text
            record = response.json()
            assert record['analysis']['verdict'] == verdict, record
            cases.append(record)
            print('PASS real model:', verdict, flush=True)
        saved = client.patch('/api/homework/reviews/'+cases[0]['id'],json=dict(reflection='我用6乘6等于36来验算。',in_notes=True,in_mistakes=False))
        assert saved.status_code == 200
        summary = client.get('/api/homework/summary?date=2026-11-01').json()
        assert (summary['total'],summary['passed'],summary['notes'],summary['reflections']) == (3,1,1,1), summary
        result = dict(passed=True,model=config.MODEL_NAME,isolated_database=config.DB_PATH,
                      ocr=recognized['result'],cases=cases,summary=summary)
        (output/'real-flow-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print('PASS real OCR -> durable list -> AI analysis -> reflection -> daily summary', flush=True)


if __name__ == '__main__':
    main()
