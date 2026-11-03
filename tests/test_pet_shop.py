"""Food-to-animation mapping, inventory persistence and pinned local assets."""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import db
import pet
import pet_energy
import web_app
from pet_shop import ITEMS


@pytest.fixture
def shop_db(tmp_path):
    path = str(tmp_path / 'shop.db')
    db.init_db(path)
    pet.reward('shop', 'initial', points=100, db_path=path)
    with db._conn(path) as conn:
        pet_energy.grant(conn, 'shop', 'test-window', 20, pet_energy.today())
    pet.start_play('shop', path)
    return path


@pytest.mark.parametrize('item_id', [key for key, item in ITEMS.items() if item['kind'] == 'food'])
def test_food_consumes_one_and_returns_its_exact_clip(shop_db, item_id):
    item = ITEMS[item_id]
    pet.purchase('shop', item_id, shop_db)
    pet.purchase('shop', item_id, shop_db)
    result = pet.interact('shop', item_id, shop_db)
    assert result['interacted'] and result['item']['animation'] == item['animation']
    assert result['item']['source_action'] == item['source_action']
    assert result['pet']['inventory'][item_id] == 1
    assert result['pet']['coins'] == 100 - item['price'] * 2
    assert result['pet']['xp'] == 100
    assert pet.get('shop', shop_db)['inventory'][item_id] == 1
    pet.interact('shop', item_id, shop_db)
    with pytest.raises(RuntimeError): pet.interact('shop', item_id, shop_db)


@pytest.mark.parametrize('item_id', [key for key, item in ITEMS.items() if item['kind'] == 'toy'])
def test_new_toys_are_permanent_and_keep_their_own_animation(shop_db, item_id):
    pet.purchase('shop', item_id, shop_db)
    for _ in range(2):
        result = pet.interact('shop', item_id, shop_db)
        assert result['interacted'] and result['pet']['inventory'][item_id] == 1
        assert result['item']['animation'] == ITEMS[item_id]['animation']
    with pytest.raises(RuntimeError): pet.purchase('shop', item_id, shop_db)


def test_food_and_toys_wait_for_play_window_without_consuming_stock(shop_db):
    pet.purchase('shop', 'cube', shop_db)
    pet.purchase('shop', 'watermelon', shop_db)
    with db._conn(shop_db) as conn:
        conn.execute("UPDATE pet_energy SET play_until=0 WHERE profile_id='shop'")
    for item in ('cube', 'watermelon'):
        result = pet.interact('shop', item, shop_db)
        assert not result['interacted'] and not result['pet']['focus_required']
        assert result['pet']['inventory'][item] == 1


def test_parallel_feeding_does_not_consume_unowned_food(shop_db):
    pet.purchase('shop', 'icecream', shop_db)
    def feed(_):
        try: return pet.interact('shop', 'icecream', shop_db)['interacted']
        except RuntimeError: return False
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(feed, range(8))) == 1


def test_http_new_food_cannot_override_price_or_animation(shop_db, monkeypatch):
    monkeypatch.setattr(web_app.config, 'DB_PATH', shop_db)
    client = TestClient(web_app.app)
    payload = {'profile_id': 'shop', 'item_id': 'hotpot'}
    assert client.post('/api/pet/interact', json=payload).status_code == 409
    purchase = client.post('/api/pet/purchase', json={**payload, 'price': 0})
    if purchase.status_code == 422:
        purchase = client.post('/api/pet/purchase', json=payload)
    assert purchase.status_code == 200 and purchase.json()['pet']['coins'] == 65
    feeding = client.post('/api/pet/interact', json={**payload, 'animation': 'eat'})
    if feeding.status_code == 422:
        feeding = client.post('/api/pet/interact', json=payload)
    assert feeding.status_code == 200 and feeding.json()['item']['animation'] == 'food_hotpot'


def test_every_item_has_pinned_local_video_thumbnail_and_hat_track():
    root = Path(__file__).resolve().parents[1] / 'web'
    manifest = json.loads((root / 'assets/pet/shop-manifest.json').read_text(encoding='utf-8'))
    tricks = json.loads((root / 'assets/pet/tricks.json').read_text(encoding='utf-8'))['clips']
    tracks = json.loads((root / 'assets/pet/hat-tracks.json').read_text(encoding='utf-8'))
    for item in ITEMS.values():
        animation = item['animation']
        clip = manifest['clips'].get(animation) or tricks[animation]
        video = (root / 'assets/pet' / clip['file']).read_bytes()
        assert hashlib.sha256(video).hexdigest() == clip['sha256']
        if 'git_blob' in clip:
            assert hashlib.sha1(b'blob ' + str(len(video)).encode() + b'\0' + video).hexdigest() == clip['git_blob']
        image = root / item['image'].lstrip('/')
        assert image.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
        assert tracks[animation]['points']
    assert len({item['animation'] for item in ITEMS.values() if item['kind'] == 'food'}) == 19
