"""Preview funds and unlimited interaction must stay in the dedicated test save."""
import pytest
from fastapi.testclient import TestClient

import config
import db
import pet
import web_app


def test_preview_save_is_separate_and_refill_preserves_purchases(tmp_path):
    path = str(tmp_path / 'preview.db')
    db.init_db(path)
    original = pet.reward('learner', 'first', points=20, db_path=path)['pet']
    state = pet.prepare_test_profile(path)['pet']
    assert state['test_mode'] and state['coins'] == 10000
    assert state['xp'] == 0
    pet.purchase(pet.TEST_PROFILE_ID, 'watermelon', path)
    pet.purchase(pet.TEST_PROFILE_ID, 'cube', path)
    for _ in range(8):
        result = pet.interact(pet.TEST_PROFILE_ID, 'cube', path)
        assert result['interacted'] and not result['pet']['focus_required']
    state = pet.refill_test_profile(pet.TEST_PROFILE_ID, path)['pet']
    assert state['coins'] == 10000
    assert state['inventory'] == {'watermelon': 1, 'cube': 1}
    assert pet.get('learner', path) == original
    assert not pet.get('pet-test-unregistered', path)['test_mode']
    with pytest.raises(ValueError):
        pet.refill_test_profile('learner', path)
    with db._conn(path) as conn:
        assert not pet._record_play(conn, pet.TEST_PROFILE_ID)['focus']
        for _ in range(pet.PLAY_LIMIT):
            ordinary = pet._record_play(conn, 'learner')
        assert ordinary['focus']


def test_http_refill_cannot_enable_test_mode_for_a_student(tmp_path, monkeypatch):
    path = str(tmp_path / 'api.db')
    db.init_db(path)
    monkeypatch.setattr(config, 'DB_PATH', path)
    client = TestClient(web_app.app)
    assert client.post('/api/pet/entertainment/unlock', json={'password': 'wrong'}).status_code == 422
    assert pet.get('learner', path)['coins'] == 0
    assert not pet.get('pet-fun-guessed', path)['entertainment_mode']
    result = client.post('/api/pet/entertainment/unlock', json={'password': 'xingya'})
    assert result.status_code == 200
    state = result.json()['pet']
    assert state['coins'] == 10000 and state['entertainment_mode']
    assert set(state['inventory']) == set(pet.SHOP)
    assert all(item['learned'] for item in state['actions'])
    assert all(item['owned'] for item in state['hats'])
    profile = state['profile_id']
    food_count = state['inventory']['watermelon']
    for _ in range(7):
        assert pet.interact(profile, 'cube', path)['interacted']
        assert pet.interact(profile, 'watermelon', path)['pet']['inventory']['watermelon'] == food_count
        assert pet.perform(profile, next(iter(pet.TRICKS)), path)['performed']
    assert pet.equip_hat(profile, next(iter(pet.HATS)), path)['pet']['equipped_hat']
    assert pet.get('learner', path)['inventory'] == {}


def test_existing_entertainment_save_receives_new_catalog_entries(tmp_path):
    path = str(tmp_path / 'catalog-upgrade.db')
    db.init_db(path)
    profile = pet.unlock_entertainment('xingya', path)['pet']['profile_id']
    with db._conn(path) as conn:
        conn.execute("DELETE FROM pet_collection WHERE profile_id=? AND item_id IN ('flute','violin','hat_beret')", (profile,))
    for _ in range(2):
        state = pet.get(profile, path)
        assert all(item['learned'] for item in state['actions'])
        assert all(item['owned'] for item in state['hats'])
        assert state['coins'] == 10000
    learner = pet.get('ordinary-student', path)
    assert not any(item['learned'] for item in learner['actions'])
    assert not any(item['owned'] for item in learner['hats'])
