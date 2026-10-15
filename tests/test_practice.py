import json
import random
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction

import pytest
from fastapi.testclient import TestClient

import db
import practice
import web_app


@pytest.fixture
def path(tmp_path, monkeypatch):
    value = str(tmp_path / 'practice.db')
    db.init_db(value)
    monkeypatch.setattr(web_app.config, 'DB_PATH', value)
    return value


def test_all_templates_have_finite_exact_answers():
    for kid in range(1, 51):
        for seed in range(30):
            p = practice.variant(kid, random.Random(seed))
            assert p['question'] and p['explanation']
            assert Fraction(p['expected']) >= 0


def test_template_answers_against_independent_reference():
    # 固定参数a=2、b=3、c=4，参考值人工按知识点公式计算。
    values = ['103','200','20','95','2','14','7','22/15','8/15','5/6',
              '10','6','8','4','6','6','20','157/25','314/25','52',
              '24','24','8','165','6','4','4','320','32','2',
              '16','4','20','1/10','90','120','240','10','2000','20000',
              '2000','2000','120','24','20','2','5','6','3','63']
    class Parameters:
        def __init__(self): self.values = iter([2, 3, 4])
        def randint(self, low, high): return next(self.values)
    for kid, answer in enumerate(values, 1):
        assert Fraction(practice.variant(kid, Parameters())['expected']) == Fraction(answer)


def test_history_is_preserved_when_practice_reduces_priority(path):
    db.save_record(dict(session_id='s', record_date='2026-10-13', question_type='几何应用题',
                        question_text='t', knowledge_point='长方形面积', formula='f',
                        dialogue_log='[]', understood=0), path)
    before = db.weak_stats(path)[0]
    p = practice.create(12, path)
    after = practice.submit(p['id'], expected(p['id'], path), path)['stats']
    assert after['weak_score'] < before['weak_score']
    assert after['total'] == before['total'] and after['not_understood'] == before['not_understood']


def expected(eid, path):
    with db._conn(path) as conn:
        return json.loads(conn.execute('SELECT payload FROM practice_exercise WHERE id=?', (eid,)).fetchone()[0])['expected']


def test_select_weak_point_and_hide_answers(path):
    db.save_record(dict(session_id='s', record_date='2026-10-13', question_type='几何应用题',
                        question_text='t', knowledge_point='长方形面积', formula='f',
                        dialogue_log='[]', understood=0), path)
    p = practice.create(db_path=path)
    assert p['knowledge_id'] == 12
    assert 'expected' not in p and 'explanation' not in p
    assert practice.get(p['id'], path)['answered'] is False


def test_success_changes_priority_and_three_successes_consolidate(path):
    for i in range(3):
        p = practice.create(12, path)
        result = practice.submit(p['id'], expected(p['id'], path), path)
        assert result['independent']
        assert result['stats']['streak'] == i+1
    assert result['stats']['practice_status'] == '初步巩固'
    assert result['stats']['weak_score'] == 0
    p = practice.create(12, path)
    result = practice.submit(p['id'], '0', path)
    assert not result['correct']
    assert result['stats']['streak'] == 0 and result['stats']['weak_score'] == 2


def test_hint_does_not_count_as_independent(path):
    p = practice.create(12, path)
    practice.hint(p['id'], path)
    result = practice.submit(p['id'], expected(p['id'], path), path)
    assert result['correct'] and not result['independent']
    assert result['stats']['streak'] == 0
    with pytest.raises(RuntimeError): practice.hint(p['id'], path)


def test_submitted_result_survives_reload_without_recounting(path):
    p = practice.create(12, path)
    assert 'expected' not in practice.get(p['id'], path)
    practice.hint(p['id'], path)
    submitted = practice.submit(p['id'], expected(p['id'], path), path)
    for _ in range(2):
        restored = practice.get(p['id'], path)
        assert restored['answered'] and restored['correct']
        assert restored['expected'] == submitted['expected']
        assert restored['explanation'] == submitted['explanation']
        assert restored['feedback'] == submitted['feedback']
    assert db.weak_stats(path)[0]['practice_total'] == 1


def test_duplicate_submission_is_atomic(path):
    p = practice.create(12, path)
    answer = expected(p['id'], path)
    def send():
        try: return practice.submit(p['id'], answer, path)
        except RuntimeError: return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: send(), range(2)))
    assert sum(r is not None for r in results) == 1
    assert db.weak_stats(path)[0]['practice_total'] == 1


@pytest.mark.parametrize('text', ['__import__("os")', '1/0', 'NaN', '3+2', ''])
def test_invalid_answer_does_not_write(path, text):
    p = practice.create(12, path)
    with pytest.raises(ValueError): practice.submit(p['id'], text, path)
    assert not practice.get(p['id'], path)['answered']


def test_fraction_and_units():
    assert practice.parse_answer('0.5', '') == Fraction(1,2)
    assert practice.parse_answer('2/4', '') == Fraction(1,2)
    assert practice.parse_answer('４０平方厘米', '平方厘米') == 40
    with pytest.raises(ValueError): practice.parse_answer('40厘米', '平方厘米')


def test_endpoints_work_without_model(path):
    client = TestClient(web_app.app)
    p = client.post('/api/practice', json={'knowledge_id': 12}).json()
    assert client.get('/api/practice/'+p['id']).status_code == 200
    answer = expected(p['id'], path)
    response = client.post('/api/practice/'+p['id']+'/answer', json={'answer': answer})
    assert response.status_code == 200 and response.json()['correct']
    assert client.post('/api/practice/'+p['id']+'/answer', json={'answer': answer}).status_code == 409
    assert client.post('/api/practice/missing/hint').status_code == 404
    assert client.post('/api/practice', json={'knowledge_id': 51}).status_code == 422


def test_database_reinitialization_preserves_practice(path):
    p = practice.create(12, path)
    db.init_db(path)
    assert practice.get(p['id'], path)['id'] == p['id']
