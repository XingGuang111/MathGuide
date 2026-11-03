# -*- coding: utf-8 -*-
"""学习陪伴宠物：积分、成长、商店和互动的轻量持久化服务。"""
import json
import secrets
import time

import db
import pet_emotions
import pet_energy
from pet_catalog import HATS, TRICKS
from pet_shop import ITEMS as ANIMATED_ITEMS

PLAY_WINDOW_SECONDS = 45
PLAY_LIMIT = 4
TEST_PROFILE_ID = 'pet-test-preview'


SHOP = {
    "biscuit": {"name": "星星饼干", "kind": "food", "price": 10, "emoji": "🍪", "mood": 8,
                "image": "/assets/items/biscuit.svg", "animation": "eat", "description": "酥脆小点心 · 每次喂食消耗 1 份"},
    "berry": {"name": "能量果实", "kind": "food", "price": 25, "emoji": "🍓", "mood": 16,
              "image": "/assets/items/berry.svg", "animation": "eat", "description": "甜甜的果实 · 每次喂食消耗 1 份"},
    "ball": {"name": "彩虹小球", "kind": "toy", "price": 40, "emoji": "🔴", "mood": 20,
             "image": "/assets/items/ball.svg", "animation": "play", "description": "一起练习抛接球 · 购买后可反复玩"},
    "yarn": {"name": "星云毛线球", "kind": "toy", "price": 60, "emoji": "🧶", "mood": 28,
             "image": "/assets/items/yarn.svg", "animation": "touch", "description": "软软的毛线球 · 购买后可反复玩"},
}
SHOP.update(ANIMATED_ITEMS)

STAGES = [
    (0, "幼年伙伴", "从一次小小的学习开始，一起长大"),
    (100, "成长伙伴", "伙伴长大了，获得第一枚成长星章"),
    (300, "学习伙伴", "解锁星光陪伴场景与双星徽章"),
    (600, "星光伙伴", "解锁星光冠与最终成长徽章"),
]


def _ensure_schema(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS pet_profile (
        profile_id TEXT PRIMARY KEY,
        coins INTEGER NOT NULL DEFAULT 0,
        xp INTEGER NOT NULL DEFAULT 0,
        mood INTEGER NOT NULL DEFAULT 70,
        inventory TEXT NOT NULL DEFAULT '{}',
        last_action TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS pet_reward (
        profile_id TEXT NOT NULL,
        event_id TEXT NOT NULL,
        points INTEGER NOT NULL,
        xp INTEGER NOT NULL,
        reason TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(profile_id, event_id)
    );
    CREATE TABLE IF NOT EXISTS pet_attention (
        profile_id TEXT PRIMARY KEY,
        touches TEXT NOT NULL DEFAULT '[]',
        focus_required INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS pet_message (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        profile_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        source TEXT NOT NULL DEFAULT 'local_model',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS pet_message_profile ON pet_message(profile_id, id);
    CREATE TABLE IF NOT EXISTS pet_feeling (
        profile_id TEXT PRIMARY KEY,
        emotion TEXT NOT NULL DEFAULT 'smile',
        reason TEXT,
        streak INTEGER NOT NULL DEFAULT 0,
        struggles INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS pet_collection (
        profile_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        item_id TEXT NOT NULL,
        acquired_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(profile_id, kind, item_id)
    );
    CREATE TABLE IF NOT EXISTS pet_outfit (
        profile_id TEXT PRIMARY KEY,
        hat_id TEXT
    );
    CREATE TABLE IF NOT EXISTS pet_test_profile (
        profile_id TEXT PRIMARY KEY
    );
    CREATE TABLE IF NOT EXISTS pet_entertainment_session (
        profile_id TEXT PRIMARY KEY
    );
    """)
    pet_energy.ensure_schema(conn)


def _is_test_profile(conn, profile_id):
    return bool(conn.execute('SELECT 1 FROM pet_test_profile WHERE profile_id=?', (profile_id,)).fetchone())


def unlock_entertainment(password, db_path=None):
    """The password issues an unguessable, separate entertainment save."""
    if not secrets.compare_digest(password.encode('utf-8'), b'xingya'):
        raise ValueError('密码不正确，请重新输入')
    profile_id = 'pet-fun-' + secrets.token_urlsafe(24)
    with db._conn(db_path) as conn:
        _ensure_schema(conn)
        conn.execute('BEGIN IMMEDIATE')
        _profile(conn, profile_id)
        conn.execute('INSERT INTO pet_test_profile(profile_id) VALUES (?)', (profile_id,))
        conn.execute('INSERT INTO pet_entertainment_session(profile_id) VALUES (?)', (profile_id,))
        inventory = {key: 999 if item['kind'] == 'food' else 1 for key, item in SHOP.items()}
        conn.execute('UPDATE pet_profile SET coins=10000,inventory=? WHERE profile_id=?',
                     (json.dumps(inventory), profile_id))
        conn.executemany('INSERT INTO pet_collection(profile_id,kind,item_id) VALUES (?,?,?)',
                         [(profile_id, 'action', key) for key in TRICKS]
                         + [(profile_id, 'hat', key) for key in HATS])
        return {'pet': _snapshot(conn, profile_id)}


def prepare_test_profile(db_path=None):
    """Enable only the dedicated preview profile; called locally, never by HTTP."""
    with db._conn(db_path) as conn:
        _ensure_schema(conn)
        conn.execute('BEGIN IMMEDIATE')
        _profile(conn, TEST_PROFILE_ID)
        conn.execute('INSERT OR IGNORE INTO pet_test_profile(profile_id) VALUES (?)', (TEST_PROFILE_ID,))
    return refill_test_profile(TEST_PROFILE_ID, db_path)


def refill_test_profile(profile_id, db_path=None):
    with db._conn(db_path) as conn:
        _ensure_schema(conn)
        conn.execute('BEGIN IMMEDIATE')
        if not _is_test_profile(conn, profile_id):
            raise ValueError('当前不是已开启的测试档案')
        conn.execute('UPDATE pet_profile SET coins=10000 WHERE profile_id=?', (profile_id,))
        conn.execute("UPDATE pet_attention SET touches='[]', focus_required=0 WHERE profile_id=?", (profile_id,))
        return {'pet': _snapshot(conn, profile_id)}


def _profile(conn, profile_id):
    row = conn.execute("SELECT * FROM pet_profile WHERE profile_id=?", (profile_id,)).fetchone()
    if row is None:
        conn.execute("INSERT INTO pet_profile(profile_id) VALUES (?)", (profile_id,))
        row = conn.execute("SELECT * FROM pet_profile WHERE profile_id=?", (profile_id,)).fetchone()
    return row


def _stage(xp):
    current = STAGES[0]
    for item in STAGES:
        if xp >= item[0]:
            current = item
    index = STAGES.index(current)
    next_xp = STAGES[index + 1][0] if index + 1 < len(STAGES) else None
    return index + 1, current[1], current[2], next_xp


def _public(row, focus_required=False):
    inventory = json.loads(row["inventory"] or "{}")
    level, stage, stage_tip, next_xp = _stage(row["xp"])
    return {
        "profile_id": row["profile_id"], "coins": row["coins"], "xp": row["xp"],
        "mood": row["mood"], "inventory": inventory, "level": level,
        "stage": stage, "stage_tip": stage_tip, "next_xp": next_xp,
        "stages": [{"level": i + 1, "name": s[1], "xp": s[0]} for i, s in enumerate(STAGES)],
        "shop": [{"id": key, **value} for key, value in SHOP.items()],
        "last_action": row["last_action"],
        "focus_required": bool(focus_required),
    }


def _snapshot(conn, profile_id):
    row = _profile(conn, profile_id)
    result = _public(row)
    result['energy'] = pet_energy.snapshot(conn, profile_id)
    result['test_mode'] = _is_test_profile(conn, profile_id)
    result['entertainment_mode'] = bool(conn.execute(
        'SELECT 1 FROM pet_entertainment_session WHERE profile_id=?', (profile_id,)).fetchone())
    if result['entertainment_mode']:
        # Existing entertainment saves also receive newly added lessons and hats.
        conn.executemany('INSERT OR IGNORE INTO pet_collection(profile_id,kind,item_id) VALUES (?,?,?)',
                         [(profile_id, 'action', key) for key in TRICKS]
                         + [(profile_id, 'hat', key) for key in HATS])
    mood = conn.execute('SELECT * FROM pet_feeling WHERE profile_id=?', (profile_id,)).fetchone()
    result['feeling'] = pet_emotions.feeling(mood['emotion'], mood['reason']) if mood else pet_emotions.feeling()
    result['learning_streak'] = mood['streak'] if mood else 0
    result['struggle_count'] = mood['struggles'] if mood else 0
    owned = {(r['kind'], r['item_id']) for r in conn.execute(
        'SELECT kind,item_id FROM pet_collection WHERE profile_id=?', (profile_id,))}
    outfit = conn.execute('SELECT hat_id FROM pet_outfit WHERE profile_id=?', (profile_id,)).fetchone()
    hat_id = outfit['hat_id'] if outfit else None
    result['actions'] = [{'id': key, **item, 'learned': ('action', key) in owned}
                         for key, item in TRICKS.items()]
    result['hats'] = [{'id': key, **item, 'owned': ('hat', key) in owned,
                       'equipped': key == hat_id} for key, item in HATS.items()]
    result['equipped_hat'] = {'id': hat_id, **HATS[hat_id]} if hat_id in HATS else None
    return result


def _set_feeling(conn, profile_id, emotion, reason=None):
    value = pet_emotions.feeling(emotion, reason)
    conn.execute('INSERT OR IGNORE INTO pet_feeling(profile_id) VALUES (?)', (profile_id,))
    conn.execute('UPDATE pet_feeling SET emotion=?, reason=? WHERE profile_id=?',
                 (value['name'], value['message'], profile_id))
    return value


def _record_play(conn, profile_id):
    """Compatibility helper: play eligibility now depends only on the paid window."""
    return {'count': 0, 'focus': not pet_energy.snapshot(conn, profile_id)['active'],
            'just_locked': False, 'mood': 'smile'}


def start_play(profile_id, db_path=None):
    with db._conn(db_path) as conn:
        _ensure_schema(conn)
        conn.execute('BEGIN IMMEDIATE')
        _profile(conn, profile_id)
        started, charged = pet_energy.start(conn, profile_id)
        return {'started': started, 'charged': charged, 'pet': _snapshot(conn, profile_id)}


def record_learning_progress(task_id, teaching_state, db_path=None):
    with db._conn(db_path) as conn:
        _ensure_schema(conn)
        conn.execute('BEGIN IMMEDIATE')
        return pet_energy.record_evidence(conn, task_id, teaching_state)


def get(profile_id, db_path=None):
    profile_id = str(profile_id).strip()[:80]
    if not profile_id:
        raise ValueError("缺少宠物档案")
    with db._conn(db_path) as conn:
        _ensure_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        return _snapshot(conn, profile_id)


def reward(profile_id, event_id, reason="完成学习任务", points=20, xp=None, db_path=None, outcome=None,
           energy_target=0, energy_day=None):
    profile_id, event_id = str(profile_id).strip()[:80], str(event_id).strip()[:120]
    if not profile_id or not event_id:
        raise ValueError("宠物奖励缺少事件标识")
    points = max(0, min(int(points), 100))
    xp = points if xp is None else max(0, min(int(xp), 100))
    with db._conn(db_path) as conn:
        _ensure_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        row = _profile(conn, profile_id)
        already = conn.execute("SELECT 1 FROM pet_reward WHERE profile_id=? AND event_id=?", (profile_id, event_id)).fetchone()
        if already:
            return {"awarded": False, "pet": _snapshot(conn, profile_id)}
        energy_added = pet_energy.grant(conn, profile_id, event_id, energy_target, energy_day)
        conn.execute("INSERT INTO pet_reward(profile_id,event_id,points,xp,reason) VALUES (?,?,?,?,?)",
                     (profile_id, event_id, points, xp, reason))
        conn.execute("UPDATE pet_profile SET coins=coins+?, xp=xp+?, mood=MIN(100,mood+8), last_action=?, updated_at=CURRENT_TIMESTAMP WHERE profile_id=?",
                     (points, xp, reason, profile_id))
        conn.execute('UPDATE pet_attention SET touches=\'[]\', focus_required=0 WHERE profile_id=?', (profile_id,))
        conn.execute('INSERT OR IGNORE INTO pet_feeling(profile_id) VALUES (?)', (profile_id,))
        if outcome == 'incorrect':
            conn.execute('UPDATE pet_feeling SET streak=0, struggles=struggles+1 WHERE profile_id=?', (profile_id,))
            struggles = conn.execute('SELECT struggles FROM pet_feeling WHERE profile_id=?', (profile_id,)).fetchone()[0]
            _set_feeling(conn, profile_id, 'crying' if struggles >= 2 else 'concerned')
        elif outcome == 'independent':
            conn.execute('UPDATE pet_feeling SET streak=streak+1, struggles=0 WHERE profile_id=?', (profile_id,))
            streak = conn.execute('SELECT streak FROM pet_feeling WHERE profile_id=?', (profile_id,)).fetchone()[0]
            _set_feeling(conn, profile_id, 'laugh' if streak >= 3 else 'smile',
                         f'连续独立完成 {streak} 道题啦，哈哈，我都忍不住笑出声了！' if streak >= 3
                         else '你认真做出来啦，我为你的努力开心！')
        else:
            conn.execute('UPDATE pet_feeling SET streak=0, struggles=0 WHERE profile_id=?', (profile_id,))
            _set_feeling(conn, profile_id, 'smile', '愿意一步一步尝试就很棒，我们又前进了一点。')
        return {"awarded": True, "points": points, "xp": xp, "reason": reason, 'energy_awarded': energy_added,
                "pet": _snapshot(conn, profile_id)}


def claim_reward(profile_id, event_id, db_path=None):
    """The browser supplies an event id; completed records determine the reward."""
    kind, separator, source_id = event_id.partition(":")
    if not separator or not source_id:
        raise ValueError("奖励事件无效")
    with db._conn(db_path) as conn:
        _ensure_schema(conn)
        conn.execute('BEGIN IMMEDIATE')
        if kind == 'progress':
            task_id, _, requested = source_id.rpartition(':')
            evidence = conn.execute('SELECT * FROM pet_learning_evidence WHERE task_id=?', (task_id,)).fetchone()
            if not evidence or not requested.isdigit() or int(requested) > evidence['target']:
                raise ValueError('先完成一个已核实的学习步骤')
            _profile(conn, profile_id)
            added = pet_energy.grant(conn, profile_id, 'tutor:' + task_id, int(requested), evidence['day'])
            return {'awarded': bool(added), 'points': 0, 'energy_awarded': added,
                    'reason': '完成学习小步骤', 'pet': _snapshot(conn, profile_id)}
        if kind == "practice":
            row = conn.execute("SELECT correct, hinted, answered_at FROM practice_exercise WHERE id=?", (source_id,)).fetchone()
            if row is None or row["correct"] is None:
                raise ValueError("完成练习后才能领取奖励")
            points = (5 if row["hinted"] else 10) if row["correct"] else 3
            reason = "完成专项练习"
            outcome = ('supported' if row['hinted'] else 'independent') if row['correct'] else 'incorrect'
            energy_target = 20 if row['correct'] else 5
            energy_day = pet_energy.record_day(row['answered_at'])
        elif kind == "tutor":
            row = conn.execute("SELECT understood,create_time FROM study_record WHERE session_id=? LIMIT 1", (source_id,)).fetchone()
            if row is None:
                raise ValueError("完成辅导后才能领取奖励")
            points, reason = 20, "完成一道辅导题"
            outcome = 'independent' if row['understood'] else 'supported'
            evidence = conn.execute('SELECT target FROM pet_learning_evidence WHERE task_id=?', (source_id,)).fetchone()
            energy_target = 20 if row['understood'] else (evidence['target'] if evidence else 0)
            energy_day = pet_energy.record_day(row['create_time'])
        else:
            raise ValueError("不支持的奖励事件")
    return reward(profile_id, event_id, reason, points, db_path=db_path, outcome=outcome,
                  energy_target=energy_target, energy_day=energy_day)


def purchase(profile_id, item_id, db_path=None):
    profile_id, item_id = str(profile_id).strip()[:80], str(item_id).strip()
    if item_id in HATS:
        return _acquire(profile_id, item_id, HATS, 'hat', db_path)
    item = SHOP.get(item_id)
    if not item:
        raise ValueError("商品不存在")
    with db._conn(db_path) as conn:
        _ensure_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        row = _profile(conn, profile_id)
        inventory = json.loads(row["inventory"] or "{}")
        if item["kind"] == "toy" and inventory.get(item_id, 0):
            raise RuntimeError("已经拥有这个玩具，可以直接去背包玩耍")
        if row["coins"] < item["price"]:
            raise RuntimeError(f"还差 {item['price'] - row['coins']} 星星")
        inventory[item_id] = inventory.get(item_id, 0) + 1
        conn.execute("UPDATE pet_profile SET coins=coins-?, inventory=?, last_action=?, updated_at=CURRENT_TIMESTAMP WHERE profile_id=?",
                     (item["price"], json.dumps(inventory, ensure_ascii=False), f"买了{item['name']}", profile_id))
        return {"purchased": True, "item": item, "pet": _snapshot(conn, profile_id)}


def _acquire(profile_id, item_id, catalog, kind, db_path):
    """Permanent lessons and hats: concurrent retries charge at most once."""
    profile_id, item_id = str(profile_id).strip()[:80], str(item_id).strip()
    if not profile_id or item_id not in catalog:
        raise ValueError('动作或帽子不存在')
    item = catalog[item_id]
    flag = 'learned' if kind == 'action' else 'purchased'
    with db._conn(db_path) as conn:
        _ensure_schema(conn)
        conn.execute('BEGIN IMMEDIATE')
        row = _profile(conn, profile_id)
        owned = conn.execute('SELECT 1 FROM pet_collection WHERE profile_id=? AND kind=? AND item_id=?',
                             (profile_id, kind, item_id)).fetchone()
        if owned:
            return {flag: False, 'item': item, 'pet': _snapshot(conn, profile_id)}
        if row['coins'] < item['price']:
            raise RuntimeError(f"还差 {item['price'] - row['coins']} 星星，完成学习任务就能获得哦")
        conn.execute('INSERT INTO pet_collection(profile_id,kind,item_id) VALUES (?,?,?)',
                     (profile_id, kind, item_id))
        verb = '学会了' if kind == 'action' else '买了'
        conn.execute('UPDATE pet_profile SET coins=coins-?, last_action=?, updated_at=CURRENT_TIMESTAMP WHERE profile_id=?',
                     (item['price'], verb + item['name'], profile_id))
        return {flag: True, 'item': item, 'pet': _snapshot(conn, profile_id)}


def learn(profile_id, action_id, db_path=None):
    return _acquire(profile_id, action_id, TRICKS, 'action', db_path)


def perform(profile_id, action_id, db_path=None):
    action_id = str(action_id).strip()
    if action_id not in TRICKS:
        raise ValueError('动作不存在')
    with db._conn(db_path) as conn:
        _ensure_schema(conn)
        conn.execute('BEGIN IMMEDIATE')
        _profile(conn, profile_id)
        if not conn.execute("SELECT 1 FROM pet_collection WHERE profile_id=? AND kind='action' AND item_id=?",
                            (profile_id, action_id)).fetchone():
            raise RuntimeError('星芽还没学会这个动作，先用星星解锁吧')
        if _record_play(conn, profile_id)['focus']:
            return {'performed': False, 'reply': pet_energy.snapshot(conn, profile_id)['message'],
                    'pet': _snapshot(conn, profile_id)}
        item = TRICKS[action_id]
        conn.execute('UPDATE pet_profile SET mood=MIN(100,mood+3), last_action=?, updated_at=CURRENT_TIMESTAMP WHERE profile_id=?',
                     ('表演了' + item['name'], profile_id))
        return {'performed': True, 'item': item, 'pet': _snapshot(conn, profile_id)}


def equip_hat(profile_id, hat_id=None, db_path=None):
    if hat_id is not None and hat_id not in HATS:
        raise ValueError('帽子不存在')
    with db._conn(db_path) as conn:
        _ensure_schema(conn)
        conn.execute('BEGIN IMMEDIATE')
        _profile(conn, profile_id)
        if hat_id and not conn.execute("SELECT 1 FROM pet_collection WHERE profile_id=? AND kind='hat' AND item_id=?",
                                       (profile_id, hat_id)).fetchone():
            raise RuntimeError('还没有这顶帽子，先去装扮商店购买吧')
        conn.execute('INSERT INTO pet_outfit(profile_id,hat_id) VALUES (?,?) ON CONFLICT(profile_id) DO UPDATE SET hat_id=excluded.hat_id',
                     (profile_id, hat_id))
        return {'equipped': True, 'pet': _snapshot(conn, profile_id)}


def interact(profile_id, item_id, db_path=None):
    profile_id, item_id = str(profile_id).strip()[:80], str(item_id).strip()
    item = SHOP.get(item_id)
    if not item:
        raise ValueError("互动道具不存在")
    with db._conn(db_path) as conn:
        _ensure_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        row = _profile(conn, profile_id)
        inventory = json.loads(row["inventory"] or "{}")
        if inventory.get(item_id, 0) < 1:
            raise RuntimeError("还没有这个道具，先去商店购买吧")
        if not pet_energy.snapshot(conn, profile_id)['active']:
            return {'interacted': False, 'focus_required': False,
                    'reply': pet_energy.snapshot(conn, profile_id)['message'],
                    'pet': _snapshot(conn, profile_id)}
        entertainment = conn.execute('SELECT 1 FROM pet_entertainment_session WHERE profile_id=?', (profile_id,)).fetchone()
        if item["kind"] == "food" and not entertainment:
            inventory[item_id] -= 1
            if inventory[item_id] <= 0:
                inventory.pop(item_id, None)
        conn.execute("UPDATE pet_profile SET inventory=?, mood=MIN(100,mood+?), last_action=?, updated_at=CURRENT_TIMESTAMP WHERE profile_id=?",
                     (json.dumps(inventory, ensure_ascii=False), item["mood"], f"和{item['name']}互动", profile_id))
        return {"interacted": True, "item": item, "pet": _snapshot(conn, profile_id)}
