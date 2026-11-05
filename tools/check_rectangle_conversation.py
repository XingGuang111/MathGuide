"""Replay the reported rectangle conversation against the configured real model."""
import json
import logging
from pathlib import Path
import sys
import uuid
from contextlib import nullcontext

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config
from fastapi.testclient import TestClient
import web_app


def main():
    output = ROOT / 'output' / 'rectangle-conversation'
    output.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=output / 'model.log', level=logging.INFO, encoding='utf-8')
    report = []
    with nullcontext(output / uuid.uuid4().hex) as directory:
        directory.mkdir()
        config.DB_PATH = str(Path(directory) / 'test.db')
        with TestClient(web_app.app) as client:
            for label, answers in [
                ('reference', ['我改用长乘宽，列式8×3，但我算成了25平方厘米。',
                               '我检查后改成8×3＝24平方厘米。']),
                ('separate_steps', ['8x3', '24', '平方厘米']),
            ]:
                question = '题目：一张长方形卡纸长8厘米，宽3厘米，面积是多少平方厘米？\n我想用8＋3＝11平方厘米，这样对吗？'
                data = client.post('/api/sessions', json={'question': question}).json()
                sid = data['session_id']
                turns = [{'student': question, **data}]
                print(label, json.dumps(data, ensure_ascii=False), flush=True)
                for answer in answers:
                    data = client.post('/api/replies', json={'session_id': sid, 'message': answer}).json()
                    turns.append({'student': answer, **data})
                    print(label, json.dumps(data, ensure_ascii=False), flush=True)
                report.append({'scenario': label, 'turns': turns})
                (output / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
                assert not any(turn.get('retryable') for turn in turns), label
                assert turns[-1]['finished'], label
                assert turns[0]['summary']['target'] == '长方形的面积'
                assert [row['value'] for row in turns[0]['summary']['conditions']] == ['8厘米', '3厘米']
                assert turns[1]['summary']['expression'] == '8*3'
                assert '长×宽' in turns[1]['summary']['method']
                assert 'method' not in turns[0]['summary']['completed']
                assert not turns[1]['finished']
                assert '24' not in turns[0]['reply'] and '24' not in turns[1]['reply']
    print('All real-model rectangle scenarios passed.', flush=True)


if __name__ == '__main__':
    main()
