"""Permanent action lessons and hats share the verified star economy."""
import hashlib
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

import db
import pet
import pet_energy
import web_app
from pet_catalog import HATS, TRICKS


@pytest.fixture
def collection_db(tmp_path):
    path = str(tmp_path / 'collection.db')
    db.init_db(path)
    pet.reward('a', 'initial', points=100, db_path=path)
    with db._conn(path) as conn:
        pet_energy.grant(conn, 'a', 'test-window', 20, pet_energy.today())
    pet.start_play('a', path)
    return path


def test_lessons_persist_and_perform_does_not_cost_again(collection_db):
    result = pet.learn('a', 'stretch', collection_db)
    assert result['learned']
    assert (result['pet']['coins'], result['pet']['xp']) == (80, 100)
    assert pet.perform('a', 'stretch', collection_db)['performed']
    assert not pet.learn('a', 'stretch', collection_db)['learned']
    assert pet.get('a', collection_db)['coins'] == 80
    assert next(x for x in pet.get('a', collection_db)['actions'] if x['id'] == 'stretch')['learned']
    assert not any(x['learned'] for x in pet.get('b', collection_db)['actions'])
    with pytest.raises(RuntimeError):
        pet.perform('a', 'bubbles', collection_db)


def test_hat_purchase_equip_switch_remove_and_profile_isolation(collection_db):
    assert pet.purchase('a', 'hat_beret', collection_db)['purchased']
    assert not pet.purchase('a', 'hat_beret', collection_db)['purchased']
    assert pet.get('a', collection_db)['equipped_hat'] is None
    pet.equip_hat('a', 'hat_beret', collection_db)
    assert pet.get('a', collection_db)['equipped_hat']['id'] == 'hat_beret'
    with pytest.raises(RuntimeError):
        pet.equip_hat('b', 'hat_beret', collection_db)
    with pytest.raises(RuntimeError):
        pet.equip_hat('a', 'hat_wizard', collection_db)
    pet.purchase('a', 'hat_sun', collection_db)
    result = pet.equip_hat('a', 'hat_sun', collection_db)['pet']
    assert sum(h['equipped'] for h in result['hats']) == 1
    assert (result['coins'], result['xp'], result['inventory']) == (30, 100, {})
    result = pet.equip_hat('a', None, collection_db)['pet']
    assert result['equipped_hat'] is None
    assert sum(h['owned'] for h in result['hats']) == 2


@pytest.mark.parametrize('operation,item', [(pet.learn, 'bubbles'), (pet.purchase, 'hat_wizard')])
def test_concurrent_unlock_is_charged_once(collection_db, operation, item):
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: operation('a', item, collection_db), range(8)))
    flag = 'learned' if operation is pet.learn else 'purchased'
    assert sum(result[flag] for result in results) == 1
    assert pet.get('a', collection_db)['coins'] == 40


def test_different_purchases_cannot_overspend_shared_balance(collection_db):
    def attempt(item):
        try:
            if item in TRICKS:
                pet.learn('a', item, collection_db)
            else:
                pet.purchase('a', item, collection_db)
            return True
        except RuntimeError:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(attempt, ['bubbles', 'hat_wizard'])) == 1
    assert pet.get('a', collection_db)['coins'] == 40


def test_actions_continue_through_many_touches_and_wait_after_expiry(collection_db):
    pet.learn('a', 'stretch', collection_db)
    for _ in range(8):
        assert pet.perform('a', 'stretch', collection_db)['performed']
    with db._conn(collection_db) as conn:
        conn.execute("UPDATE pet_energy SET play_until=0 WHERE profile_id='a'")
    assert not pet.perform('a', 'stretch', collection_db)['performed']
    pet.purchase('a', 'hat_beret', collection_db)
    assert pet.equip_hat('a', 'hat_beret', collection_db)['equipped']
    assert pet.get('a', collection_db)['coins'] == 50


def test_http_rejects_unowned_invalid_and_insufficient_funds(collection_db, monkeypatch):
    monkeypatch.setattr(web_app.config, 'DB_PATH', collection_db)
    client = TestClient(web_app.app)
    def post(route, **fields):
        return client.post('/api/pet/' + route, json={'profile_id': 'a', **fields})
    assert post('perform', action_id='stretch').status_code == 409
    assert post('learn', action_id='../idle').status_code == 422
    assert post('equip', hat_id='hat_beret').status_code == 409
    assert post('learn', action_id='bubbles').json()['pet']['coins'] == 40
    assert post('purchase', item_id='hat_wizard').status_code == 409
    assert post('purchase', item_id='hat_beret').json()['pet']['coins'] == 10
    assert post('equip', hat_id='hat_beret').json()['pet']['equipped_hat']['id'] == 'hat_beret'
    assert post('equip', hat_id=None).json()['pet']['equipped_hat'] is None


def test_extra_clips_match_plugin_hashes_and_hats_are_local(collection_db, monkeypatch):
    monkeypatch.setattr(web_app.config, 'DB_PATH', collection_db)
    client = TestClient(web_app.app)
    manifest = client.get('/assets/pet/tricks.json').json()
    assert set(manifest['clips']) == set(TRICKS)
    for key, clip in manifest['clips'].items():
        response = client.get('/assets/pet/' + clip['file'])
        assert response.status_code == 200
        assert response.content[:4] == bytes.fromhex('1a45dfa3')
        assert hashlib.sha256(response.content).hexdigest() == clip['sha256']
    for hat in HATS.values():
        for field in ('image', 'overlay'):
            response = client.get(hat[field])
            assert response.status_code == 200
            assert b'<svg' in response.content


@pytest.mark.parametrize('action', [key for key in TRICKS if key not in {
    'stretch', 'giggle', 'bubbles', 'scout', 'busy', 'sort', 'token', 'yawn', 'sigh'}])
def test_play_lessons_charge_once_and_perform_exact_clip(collection_db, action):
    with pytest.raises(RuntimeError):
        pet.perform('a', action, collection_db)
    state = pet.learn('a', action, collection_db)['pet']
    assert state['coins'] == 100 - TRICKS[action]['price']
    assert not pet.learn('a', action, collection_db)['learned']
    result = pet.perform('a', action, collection_db)
    assert result['performed']
    learned = next(item for item in result['pet']['actions'] if item['id'] == action)
    assert learned['learned'] and learned['animation'] == action
    assert result['pet']['coins'] == state['coins']


def test_unapproved_tiger_hat_is_not_for_sale(collection_db):
    assert 'hat_tiger' not in HATS
    with pytest.raises(ValueError):
        pet.purchase('a', 'hat_tiger', collection_db)
