"""Server-owned daily energy, verified task credit and timed play sessions."""
from datetime import datetime, timedelta, timezone
import math
import time

import config

LOCAL_ZONE = timezone(timedelta(hours=8))
CAPACITY = 40
TASK_LIMIT = 20
PLAY_COST = 20
PLAY_SECONDS = 120


def today(now=None):
    return datetime.fromtimestamp(time.time() if now is None else now, LOCAL_ZONE).date().isoformat()


def record_day(timestamp):
    return datetime.fromisoformat(timestamp).replace(tzinfo=timezone.utc).astimezone(LOCAL_ZONE).date().isoformat()


def ensure_schema(conn):
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS pet_energy (
        profile_id TEXT PRIMARY KEY, day TEXT NOT NULL,
        balance INTEGER NOT NULL DEFAULT 0, reserved_seconds INTEGER NOT NULL DEFAULT 0,
        play_until REAL NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS pet_energy_credit (
        profile_id TEXT NOT NULL, task_id TEXT NOT NULL, total INTEGER NOT NULL,
        PRIMARY KEY(profile_id,task_id)
    );
    CREATE TABLE IF NOT EXISTS pet_learning_evidence (
        task_id TEXT PRIMARY KEY, target INTEGER NOT NULL, day TEXT NOT NULL
    );
    ''')


def _row(conn, profile_id, now):
    day = today(now)
    conn.execute('INSERT OR IGNORE INTO pet_energy(profile_id,day) VALUES (?,?)', (profile_id, day))
    # Rollover preserves an already-paid session through midnight; its quota
    # belongs to the previous day. New sessions always use the current day.
    conn.execute('UPDATE pet_energy SET day=?,balance=0,reserved_seconds=0 WHERE profile_id=? AND day<>?',
                 (day, profile_id, day))
    return conn.execute('SELECT * FROM pet_energy WHERE profile_id=?', (profile_id,)).fetchone()


def snapshot(conn, profile_id):
    now = time.time()
    row = _row(conn, profile_id, now)
    unlimited = bool(conn.execute('SELECT 1 FROM pet_test_profile WHERE profile_id=?', (profile_id,)).fetchone())
    daily_limit = max(0, int(config.PET_DAILY_PLAY_MINUTES)) * 60
    remaining = max(0, math.ceil(row['play_until'] - now))
    quota = max(0, daily_limit - row['reserved_seconds'])
    active = unlimited or remaining > 0
    can_start = not active and row['balance'] >= PLAY_COST and quota >= PLAY_SECONDS
    if unlimited:
        message = '娱乐模式：自由互动，不消耗活力。'
    elif active:
        message = '玩耍时间里，可以自由摸摸、喂食和表演。'
    elif quota < PLAY_SECONDS:
        message = '今天的玩耍时间用完啦，我继续陪你学习，也可以先休息一下。'
    elif can_start:
        message = '活力准备好啦！可以开启一段玩耍时间。'
    else:
        message = f'我在这里陪你学习，完成小任务攒够 {PLAY_COST} 活力，就能一起玩耍。'
    return dict(day=row['day'], balance=row['balance'], capacity=CAPACITY,
                cost=PLAY_COST, session_seconds=PLAY_SECONDS, daily_limit_seconds=daily_limit,
                available_seconds=quota, remaining_seconds=remaining, active=active,
                unlimited=unlimited, can_start=can_start, message=message)


def grant(conn, profile_id, task_id, target, eligible_day):
    """Credit only new verified progress; caps do not leave rewards banked for later."""
    energy = snapshot(conn, profile_id)
    if energy['unlimited'] or eligible_day != energy['day']:
        return 0
    target = max(0, min(TASK_LIMIT, int(target)))
    previous = conn.execute('SELECT total FROM pet_energy_credit WHERE profile_id=? AND task_id=?',
                            (profile_id, task_id)).fetchone()
    delta = max(0, target - (previous['total'] if previous else 0))
    if not delta:
        return 0
    conn.execute('INSERT INTO pet_energy_credit(profile_id,task_id,total) VALUES (?,?,?) '
                 'ON CONFLICT(profile_id,task_id) DO UPDATE SET total=excluded.total', (profile_id, task_id, target))
    added = min(delta, CAPACITY - energy['balance'])
    conn.execute('UPDATE pet_energy SET balance=balance+? WHERE profile_id=?', (added, profile_id))
    return added


def start(conn, profile_id):
    energy = snapshot(conn, profile_id)
    if energy['active']:
        return True, False
    if not energy['can_start']:
        return False, False
    conn.execute('UPDATE pet_energy SET balance=balance-?,reserved_seconds=reserved_seconds+?,play_until=? '
                 'WHERE profile_id=?', (PLAY_COST, PLAY_SECONDS, time.time() + PLAY_SECONDS, profile_id))
    return True, True


def record_evidence(conn, task_id, teaching_state):
    # Both lists are created only by deterministic checks in the tutor.
    count = len(set(teaching_state.get('confirmed_steps', []))) + len(set(teaching_state.get('energy_substeps', [])))
    target = TASK_LIMIT if teaching_state.get('mastery') == 'solved_current' else min(TASK_LIMIT, count * 5)
    if not target:
        return None
    previous = conn.execute('SELECT target FROM pet_learning_evidence WHERE task_id=?', (task_id,)).fetchone()
    if previous and previous['target'] >= target:
        return None
    conn.execute('INSERT INTO pet_learning_evidence(task_id,target,day) VALUES (?,?,?) '
                 'ON CONFLICT(task_id) DO UPDATE SET target=excluded.target,day=excluded.day', (task_id, target, today()))
    return f'progress:{task_id}:{target}'
