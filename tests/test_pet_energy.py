"""Daily rollover, verified credit, concurrent windows and server-side gates."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json

import pytest
from fastapi.testclient import TestClient

import config
import db
import pet
import pet_chat
import pet_energy
import practice
import scaffolding
import teaching
import web_app


@pytest.fixture
def energy_db(tmp_path, monkeypatch):
    path = str(tmp_path / 'energy.db')
    db.init_db(path)
    monkeypatch.setattr(config, 'DB_PATH', path)
    pet.get('a')
    return path


def credit(path, task='task', amount=20):
    with db._conn(path) as conn:
        conn.execute('BEGIN IMMEDIATE')
        return pet_energy.grant(conn, 'a', task, amount, pet_energy.today())


def test_zero_start_and_economy_cannot_buy_energy(energy_db):
    assert pet.get('a')['energy']['balance'] == 0
    assert not pet.start_play('a')['started']
    pet.reward('a', 'old-stars', points=100)
    pet.purchase('a', 'berry')
    pet.learn('a', 'stretch')
    assert not pet.interact('a', 'berry')['interacted']
    assert not pet.perform('a', 'stretch')['performed']
    assert pet.get('a')['inventory']['berry'] == 1
    assert pet.get('a')['energy']['balance'] == 0


def test_same_day_persists_next_day_resets_only_energy(energy_db, monkeypatch):
    now = [datetime(2026, 11, 1, 10, tzinfo=pet_energy.LOCAL_ZONE).timestamp()]
    monkeypatch.setattr(pet_energy.time, 'time', lambda: now[0])
    pet.reward('a', 'stars', points=100)
    pet.learn('a', 'stretch')
    pet.purchase('a', 'hat_beret')
    pet.equip_hat('a', 'hat_beret')
    credit(energy_db)
    before = pet.get('a')
    assert before['energy']['balance'] == 20
    for _ in range(4):
        assert pet.get('a')['energy']['balance'] == 20
    now[0] += 86400
    after = pet.get('a')
    assert after['energy']['balance'] == 0 and after['energy']['day'] == '2026-11-02'
    for key in ('coins', 'xp', 'inventory', 'actions', 'hats', 'equipped_hat'):
        assert after[key] == before[key]
    assert credit(energy_db) == 0  # Old task cannot refill the new day.


def test_parallel_start_costs_once_and_does_not_extend_timer(energy_db, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(pet_energy.time, 'time', lambda: now[0])
    credit(energy_db, 'one'); credit(energy_db, 'two')
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: pet.start_play('a'), range(8)))
    assert all(r['started'] for r in results) and sum(r['charged'] for r in results) == 1
    now[0] += 60
    state = pet.start_play('a')['pet']['energy']
    assert state['balance'] == 20 and state['remaining_seconds'] == 60
    assert state['available_seconds'] == 480
    now[0] += 61
    assert not pet.get('a')['energy']['active']
    assert pet.start_play('a')['charged']


def test_capacity_and_per_task_cap_cannot_bank_retry_rewards(energy_db):
    assert credit(energy_db, 'one', 5) == 5
    assert credit(energy_db, 'one', 20) == 15
    assert credit(energy_db, 'one', 1000) == 0
    assert credit(energy_db, 'two') == 20
    assert credit(energy_db, 'three') == 0
    pet.start_play('a')
    assert credit(energy_db, 'three') == 0
    assert pet.get('a')['energy']['balance'] == 20


def test_daily_limit_enforced_by_backend_and_configurable(energy_db, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(pet_energy.time, 'time', lambda: now[0])
    monkeypatch.setattr(config, 'PET_DAILY_PLAY_MINUTES', 4)
    for task in ('one', 'two'):
        credit(energy_db, task)
        assert pet.start_play('a')['charged']
        now[0] += 121
    credit(energy_db, 'three')
    result = pet.start_play('a')
    assert not result['started'] and result['pet']['energy']['balance'] == 20
    assert result['pet']['energy']['available_seconds'] == 0
    now[0] += 86400
    assert pet.get('a')['energy']['available_seconds'] == 240


def test_paid_session_finishes_across_midnight_but_balance_resets(energy_db, monkeypatch):
    now = [datetime(2026, 11, 1, 23, 59, 30, tzinfo=pet_energy.LOCAL_ZONE).timestamp()]
    monkeypatch.setattr(pet_energy.time, 'time', lambda: now[0])
    credit(energy_db, 'one'); credit(energy_db, 'two')
    pet.start_play('a')
    now[0] += 40
    state = pet.get('a')['energy']
    assert state['balance'] == 0 and state['active'] and state['remaining_seconds'] == 80
    assert state['available_seconds'] == 600
    now[0] += 81
    assert not pet.start_play('a')['started']


def test_valid_steps_and_completion_share_twenty_point_cap(energy_db):
    state = teaching.initial_state()
    state['substep'] = dict(expression='2+3', expected='5', question='2+3=?', tries=0)
    assert scaffolding.reply_to_substep(state, '5')
    assert state['energy_substeps'] == ['2+3=5']
    event = pet.record_learning_progress('session', state)
    assert pet.claim_reward('a', event)['energy_awarded'] == 5
    assert pet.record_learning_progress('session', state) is None
    assert not pet.claim_reward('a', event)['awarded']
    with pytest.raises(ValueError):
        pet.claim_reward('a', 'progress:session:20')
    with db._conn(energy_db) as conn:
        conn.execute("INSERT INTO study_record(session_id,understood) VALUES ('session',1)")
    result = pet.claim_reward('a', 'tutor:session')
    assert result['energy_awarded'] == 15 and result['pet']['energy']['balance'] == 20
    assert result['points'] == 20


def test_explanation_or_wrong_substep_does_not_invent_verified_progress(energy_db):
    state = teaching.initial_state()
    state['substep'] = dict(expression='2+3', expected='5', question='2+3=?', tries=0)
    scaffolding.reply_to_substep(state, '999')
    teaching.mark_progress(state, 'compute', explained=True)
    assert pet.record_learning_progress('unverified', state) is None
    with pytest.raises(ValueError):
        pet.claim_reward('a', 'progress:invented:20')


def test_old_completed_record_gives_stars_but_not_todays_energy(energy_db):
    with db._conn(energy_db) as conn:
        conn.execute("INSERT INTO study_record(session_id,understood,create_time) VALUES ('old',1,'2020-01-01 10:00:00')")
    result = pet.claim_reward('a', 'tutor:old')
    assert result['points'] == 20 and result['energy_awarded'] == 0


def test_practice_effort_and_assisted_success_are_rewarded_once(energy_db):
    for correct, expected in ((False, 5), (True, 20)):
        exercise = practice.create(12)
        with db._conn(energy_db) as conn:
            payload = json.loads(conn.execute('SELECT payload FROM practice_exercise WHERE id=?', (exercise['id'],)).fetchone()[0])
        practice.hint(exercise['id'])
        practice.submit(exercise['id'], payload['expected'] if correct else '-9999')
        event = 'practice:' + exercise['id']
        assert pet.claim_reward('a', event)['energy_awarded'] == expected
        assert not pet.claim_reward('a', event)['awarded']


def test_expired_window_blocks_direct_api_and_preserves_food(energy_db):
    credit(energy_db)
    pet.reward('a', 'stars', points=100)
    pet.purchase('a', 'watermelon')
    pet.learn('a', 'stretch')
    pet.start_play('a')
    with db._conn(energy_db) as conn:
        conn.execute("UPDATE pet_energy SET play_until=0 WHERE profile_id='a'")
    client = TestClient(web_app.app)
    assert not client.post('/api/pet/interact', json={'profile_id': 'a', 'item_id': 'watermelon'}).json()['interacted']
    assert not client.post('/api/pet/perform', json={'profile_id': 'a', 'action_id': 'stretch'}).json()['performed']
    assert not client.post('/api/pet/play/start', json={'profile_id': 'a', 'balance': 999}).json()['started']
    assert pet.get('a')['inventory']['watermelon'] == 1
    assert pet_chat.respond('a', event='touch')['reply']


def test_entertainment_bypasses_energy_without_changing_student(energy_db):
    profile = pet.unlock_entertainment('xingya')['pet']['profile_id']
    assert pet.start_play(profile)['started'] and not pet.start_play(profile)['charged']
    assert pet.interact(profile, 'watermelon')['interacted']
    assert pet.get(profile)['energy']['unlimited']
    assert pet.get('a')['energy']['balance'] == 0


def test_actual_tutor_progress_produces_claimable_server_evidence(energy_db, monkeypatch):
    import agent
    monkeypatch.setattr(agent.llm, 'analyze', lambda *args: {
        'is_elementary_math': True, 'knowledge_id': 12, 'question_type': '几何应用题', 'raw_knowledge': None})
    monkeypatch.setattr(agent.llm, 'chat_stream', lambda *args: iter(['先说说题目告诉了你什么。[CONTINUE]']))
    client = TestClient(web_app.app)
    sid = client.post('/api/sessions', json={'question': '长方形长12米宽8米，面积是多少？'}).json()['session_id']
    response = client.post('/api/replies', json={'session_id': sid, 'message': '长12米，宽8米，要求长方形的面积'})
    assert response.status_code == 200
    event = response.json()['pet_progress_event']
    assert event and event.startswith('progress:' + sid)
    result = client.post('/api/pet/reward', json={'profile_id': 'a', 'event_id': event}).json()
    assert result['energy_awarded'] == 5 and result['points'] == 0
    assert not client.post('/api/pet/reward', json={'profile_id': 'a', 'event_id': event}).json()['awarded']
