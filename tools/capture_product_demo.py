"""Exercise the running product API with example inputs and save real results.

Use with run_product_demo.py (isolated data). No model/OCR mocks are used.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'output' / 'product-demo-2026-11-02'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('section', choices=['ocr', 'homework', 'tutor-review', 'visual', 'cli', 'snapshot'])
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = {'time': datetime.now(timezone(timedelta(hours=8))).isoformat(),
              'example_inputs': True, 'mocked': False, 'calls': []}

    def call(method, path, payload=None, binary=None, content_type=None):
        start = time.perf_counter()
        body = binary if binary is not None else (json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None)
        headers = {'Content-Type': content_type or 'application/json'}
        request = urllib.request.Request(args.base_url + path, data=body, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=240) as response:
            result = json.load(response)
        report['calls'].append({'method': method, 'path': path, 'input': payload,
                                'seconds': round(time.perf_counter()-start, 3), 'result': result})
        (OUTPUT / f'{args.section}-evidence.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(method, path, f"{report['calls'][-1]['seconds']:.2f}s", flush=True)
        return result

    call('GET', '/api/health')
    call('GET', '/api/homework/vision/status')
    if args.section == 'ocr':
        # This is a worksheet input for the OCR demonstration, not a UI mockup.
        from PIL import Image, ImageDraw, ImageFont
        image = Image.new('RGB', (1400, 850), 'white')
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 38)
        for y, line in [(70, '今日数学作业'), (180, '1. 计算：36 ÷ 6 = ?'),
                        (300, '2. 长方形长 8 厘米，宽 5 厘米，'),
                        (370, '面积是多少平方厘米？'),
                        (500, '3. 24 颗糖平均分给 6 个小朋友，'),
                        (570, '每个小朋友分到几颗？')]:
            draw.text((70, y), line, font=font, fill='black')
        photo = OUTPUT / 'demo-worksheet.png'
        image.save(photo)
        boundary = 'MathGuideProductDemoBoundary'
        binary = (f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="worksheet.png"\r\nContent-Type: image/png\r\n\r\n'.encode()
                  + photo.read_bytes() + f'\r\n--{boundary}--\r\n'.encode())
        source = call('POST', '/api/homework/sources', binary=binary, content_type=f'multipart/form-data; boundary={boundary}')
        recognized = call('POST', f"/api/homework/sources/{source['id']}/recognize")
        questions = recognized.get('result', {}).get('questions', [])
        print(json.dumps(questions, ensure_ascii=False, indent=2), flush=True)
        assert len(questions) == 3, 'OCR demonstration did not split into 3 questions'
    elif args.section == 'homework':
        # Text-only questions keep OCR demonstration separate from visual grading.
        assignment = {'revision': 0, 'title': '产品演示：每日数学作业', 'date': '2026-11-02',
                      'items': [{'id': 'pm-homework-1', 'text': '计算：36÷6=?', 'answer': '6'},
                                {'id': 'pm-homework-2', 'text': '计算：8+5=?', 'answer': '12'},
                                {'id': 'pm-homework-3', 'text': '24颗糖平均分给6个小朋友，每人分到几颗？', 'answer': ''}],
                      'active': 'pm-homework-2'}
        try:
            old = call('GET', '/api/homework/assignments/pm-product-demo')
            assignment['revision'] = old['revision']
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
        call('PUT', '/api/homework/assignments/pm-product-demo', assignment)
        for item in assignment['items'][:2]:
            record = call('POST', '/api/homework/reviews',
                          {'item_id': item['id'], 'title': assignment['title'],
                           'assignment_date': assignment['date'], 'question': item['text'], 'answer': item['answer']})
            expected = 'correct' if item['id'].endswith('1') else 'incorrect'
            assert record['analysis']['verdict'] == expected, record
            call('PATCH', '/api/homework/reviews/' + record['id'],
                 {'reflection': '我用6乘6等于36来验算。' if expected == 'correct' else '我把8+5算成12，下次先凑十再验算。',
                  'in_notes': True, 'in_mistakes': expected != 'correct'})
        call('GET', '/api/homework/summary?date=2026-11-02')
    elif args.section == 'visual':
        import shutil
        photo = OUTPUT / 'demo-symmetry-question.png'
        shutil.copy2(ROOT / '.pet-qa' / 'homework-vision' / 'question-2.png', photo)
        boundary = 'MathGuideVisualDemoBoundary'
        binary = (f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="symmetry.png"\r\nContent-Type: image/png\r\n\r\n'.encode()
                  + photo.read_bytes() + f'\r\n--{boundary}--\r\n'.encode())
        source = call('POST', '/api/homework/sources', binary=binary, content_type=f'multipart/form-data; boundary={boundary}')
        region = {'source_id': source['id'], 'box': [0, 0, 1000, 1000]}
        reading = call('POST', '/api/homework/vision/read', region)
        print('Visual transcription:', reading, flush=True)
        question = 'E是一个轴对称图形的一半，补全另一半后不可能是（ ）。选项见配图。'
        assignment = {'revision': 0, 'title': '产品演示：轴对称带图题', 'date': '2026-11-02',
                      'source_ids': [source['id']], 'active': 'pm-visual-item',
                      'items': [{'id': 'pm-visual-item', 'text': question, 'answer': 'A',
                                 'source_ids': [source['id']], 'source_regions': [region]}]}
        try:
            old = call('GET', '/api/homework/assignments/pm-visual-demo')
            assignment['revision'] = old['revision']
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
        call('PUT', '/api/homework/assignments/pm-visual-demo', assignment)
        review = call('POST', '/api/homework/reviews',
                      {'item_id': 'pm-visual-item', 'title': assignment['title'],
                       'assignment_date': assignment['date'], 'question': question, 'answer': 'A'})
        print('Visual analysis:', review['analysis'], flush=True)
        tutor = call('POST', '/api/homework/items/pm-visual-item/visual-tutor',
                     {'message': '我该怎么观察轴对称图形？请先提示一步。', 'request_id': 'pm-visual-guidance-1'})
        print('Visual teacher:', tutor['reply'], flush=True)
        assert review['attachments'], 'Visual review did not preserve its image'
    elif args.section == 'cli':
        import contextlib
        import io
        import sys
        sys.path.insert(0, str(ROOT))
        import config
        config.DB_PATH = str(OUTPUT / 'runtime' / 'product-demo.db')
        import main as terminal
        transcript = io.StringIO()
        previous = sys.stdin
        try:
            sys.stdin = io.StringIO('/help\n/stats\n/history\n\n/quit\n')
            with contextlib.redirect_stdout(transcript):
                terminal.main()
        finally:
            sys.stdin = previous
        (OUTPUT / 'terminal-demo.txt').write_text(transcript.getvalue(), encoding='utf-8')
        print(transcript.getvalue(), flush=True)
    elif args.section == 'tutor-review':
        session = call('POST', '/api/sessions', {'question': '一件商品原价200元，打八折后多少钱？'})
        result = call('POST', '/api/replies', {'session_id': session['session_id'], 'message': '请完整讲解'})
        assert result.get('finished'), result
        history = call('GET', '/api/history')
        record = next(row for row in history if row['session_id'] == session['session_id'])
        assert not record['understood'], 'Viewing an explanation must not count as independent solving'
    else:
        for path in ['/api/history', '/api/stats', '/api/homework/assignments',
                     '/api/homework/reviews', '/api/homework/summary?date=2026-11-02']:
            call('GET', path)
    print('Saved:', OUTPUT / f'{args.section}-evidence.json', flush=True)


if __name__ == '__main__':
    main()
