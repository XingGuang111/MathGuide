"""Verify the persistent economy and the actual animation files served to browsers."""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

import db
import pet
import pet_energy
import practice
import web_app


@pytest.fixture
def pet_db(tmp_path):
    path = str(tmp_path / "pet.db")
    db.init_db(path)
    return path


def test_food_is_consumed_toy_is_reusable_and_xp_never_spent(pet_db):
    pet.reward('a', 'seed', points=100, db_path=pet_db)
    with db._conn(pet_db) as conn:
        pet_energy.grant(conn, 'a', 'test-window', 20, pet_energy.today())
    pet.start_play('a', pet_db)
    pet.purchase('a', 'biscuit', pet_db)
    pet.purchase('a', 'ball', pet_db)
    pet.interact('a', 'biscuit', pet_db)
    pet.interact('a', 'ball', pet_db)
    state = pet.interact('a', 'ball', pet_db)['pet']
    assert state['inventory'] == {'ball': 1}
    assert (state['coins'], state['xp'], state['level']) == (50, 100, 2)
    with pytest.raises(RuntimeError):
        pet.purchase('a', 'ball', pet_db)
    with pytest.raises(RuntimeError):
        pet.interact('a', 'biscuit', pet_db)
    assert pet.get('b', pet_db)['coins'] == 0


def test_parallel_claims_and_purchases_cannot_duplicate_or_overspend(pet_db):
    def award(_):
        return pet.reward('a', 'same-event', points=20, db_path=pet_db)['awarded']
    with ThreadPoolExecutor(max_workers=4) as executor:
        assert sum(executor.map(award, range(8))) == 1
    def buy(_):
        try:
            pet.purchase('a', 'biscuit', pet_db)
            return True
        except RuntimeError:
            return False
    with ThreadPoolExecutor(max_workers=4) as executor:
        assert sum(executor.map(buy, range(8))) == 2
    assert pet.get('a', pet_db)['coins'] == 0
    assert pet.get('a', pet_db)['inventory']['biscuit'] == 2


def test_reward_requires_completed_record_and_retries_are_idempotent(pet_db):
    exercise = practice.create(12, pet_db)
    event_id = 'practice:' + exercise['id']
    with pytest.raises(ValueError):
        pet.claim_reward('a', event_id, pet_db)
    with db._conn(pet_db) as conn:
        payload = json.loads(conn.execute('SELECT payload FROM practice_exercise WHERE id=?', (exercise['id'],)).fetchone()[0])
    practice.submit(exercise['id'], payload['expected'], pet_db)
    assert pet.claim_reward('a', event_id, pet_db)['points'] == 10
    assert not pet.claim_reward('a', event_id, pet_db)['awarded']
    with pytest.raises(ValueError):
        pet.claim_reward('a', 'tutor:invented-session', pet_db)


def test_growth_boundaries_and_restart_persistence(pet_db):
    for i in range(6):
        state = pet.reward('growing', str(i), points=100, db_path=pet_db)['pet']
    assert (state['xp'], state['level'], state['next_xp']) == (600, 4, None)
    assert pet.get('growing', pet_db)['level'] == 4
    pet.purchase('growing', 'berry', pet_db)
    assert pet.get('growing', pet_db)['xp'] == 600


def test_http_static_media_and_inventory(pet_db, monkeypatch):
    monkeypatch.setattr(web_app.config, 'DB_PATH', pet_db)
    client = TestClient(web_app.app)
    assert client.get('/pet.js').status_code == 200
    assert client.get('/pet.css').status_code == 200
    assert client.get('/assets/items/biscuit.svg').status_code == 200
    manifest = client.get('/assets/pet/manifest.json').json()
    assert len(manifest['clips']) == 9
    for clip in manifest['clips'].values():
        response = client.get('/assets/pet/' + clip['file'])
        assert response.status_code == 200
        assert response.headers['content-type'].startswith('video/webm')
        assert hashlib.sha256(response.content).hexdigest() == clip['sha256']
    response = client.get('/assets/pet/idle.webm', headers={'Range': 'bytes=0-15'})
    assert response.status_code == 206 and len(response.content) == 16
    assert client.post('/api/pet/reward', json={'profile_id': 'a', 'event_id': 'practice:fake', 'points': 100}).status_code == 422
    assert client.post('/api/pet/purchase', json={'profile_id': 'a', 'item_id': 'biscuit'}).status_code == 409
    pet.reward('a', 'seed', points=100, db_path=pet_db)
    with db._conn(pet_db) as conn:
        pet_energy.grant(conn, 'a', 'test-window', 20, pet_energy.today())
    pet.start_play('a', pet_db)
    assert client.post('/api/pet/purchase', json={'profile_id': 'a', 'item_id': 'ball'}).status_code == 200
    assert client.post('/api/pet/interact', json={'profile_id': 'a', 'item_id': 'ball'}).json()['pet']['inventory']['ball'] == 1
