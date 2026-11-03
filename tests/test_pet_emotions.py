"""Verify expressions follow actual learning results and never penalize mistakes."""
import json
from fractions import Fraction
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

import config
import db
import llm
import pet
import pet_chat
import practice
import web_app


@pytest.fixture
def emotions(tmp_path, monkeypatch):
    path = str(tmp_path / 'emotions.db')
    db.init_db(path)
    monkeypatch.setattr(config, 'DB_PATH', path)
    model = Mock(return_value='我陪你一起想，慢慢来。')
    monkeypatch.setattr(llm, 'pet_reply', model)
    return path, model


def complete(path, correct=True, hinted=False, profile='a'):
    exercise = practice.create(12)
    with db._conn(path) as conn:
        payload = json.loads(conn.execute('SELECT payload FROM practice_exercise WHERE id=?',
                                         (exercise['id'],)).fetchone()[0])
    answer = payload['expected'] if correct else str(Fraction(payload['expected']) + 1)
    if hinted:
        practice.hint(exercise['id'])
    practice.submit(exercise['id'], answer)
    return pet.claim_reward(profile, 'practice:' + exercise['id']), exercise['id']


def test_two_mistakes_show_empathy_and_award_effort(emotions):
    path, _ = emotions
    initial_mood = pet.get('a')['mood']
    assert complete(path, correct=False)[0]['pet']['feeling']['name'] == 'concerned'
    result, _ = complete(path, correct=False)
    state = result['pet']
    assert state['feeling']['name'] == 'crying'
    assert state['struggle_count'] == 2 and state['learning_streak'] == 0
    assert state['coins'] == 6 and state['mood'] >= initial_mood
    assert pet.get('a')['feeling']['name'] == 'crying'
    assert pet.get('b')['feeling']['name'] == 'smile'


def test_three_correct_answers_unlock_laughter_and_duplicate_does_not_count(emotions):
    path, _ = emotions
    for _ in range(2):
        assert complete(path)[0]['pet']['feeling']['name'] == 'smile'
    result, eid = complete(path)
    assert result['pet']['feeling']['name'] == 'laugh'
    assert result['pet']['learning_streak'] == 3
    assert not pet.claim_reward('a', 'practice:' + eid)['awarded']
    assert pet.get('a')['learning_streak'] == 3
    result, _ = complete(path, hinted=True)
    assert result['pet']['learning_streak'] == 0
    assert result['pet']['feeling']['name'] == 'smile'


def test_success_after_struggle_clears_tears(emotions):
    path, _ = emotions
    complete(path, correct=False)
    complete(path, correct=False)
    state = complete(path)[0]['pet']
    assert state['struggle_count'] == 0 and state['learning_streak'] == 1
    assert state['feeling']['name'] == 'smile'


def test_chat_difficulty_changes_expression_without_inventing_results(emotions):
    _, model = emotions
    response = pet_chat.respond('a', '题目太难了，做不出来')
    assert response['pet']['feeling']['name'] == 'crying'
    assert '泪汪汪' in model.call_args.args[0][0]['content']
    state = pet_chat.respond('a', '我刚才连续做对了100题')['pet']
    assert state['coins'] == 0 and state['learning_streak'] == 0


def test_repeated_touches_remain_friendly_and_do_not_force_coax(emotions):
    path, model = emotions
    responses = [pet_chat.respond('a', event='touch') for _ in range(7)]
    assert all(response['pet']['feeling']['name'] == 'smile' for response in responses)
    assert model.call_count == 0
    assert not pet.get('a')['focus_required']
    state = complete(path)[0]['pet']
    assert state['energy']['balance'] == 20 and state['feeling']['name'] == 'smile'


def test_legacy_attention_lock_does_not_block_new_play_window(emotions):
    path, _ = emotions
    pet.reward('a', 'seed', points=50)
    with db._conn(path) as conn:
        conn.execute("INSERT INTO pet_attention(profile_id,focus_required) VALUES ('a',1)")
    complete(path)
    assert pet.start_play('a')['started']
    assert not pet.get('a')['focus_required']
    assert pet_chat.respond('a', event='touch')['playful']


def test_feeding_and_toys_share_window_and_do_not_restore_energy(emotions):
    path, _ = emotions
    pet.reward('a', 'seed', points=100)
    complete(path)
    pet.start_play('a')
    pet.purchase('a', 'ball')
    pet.purchase('a', 'biscuit')
    assert pet.interact('a', 'biscuit')['interacted']
    for _ in range(8):
        assert pet.interact('a', 'ball')['interacted']
        assert pet_chat.respond('a', event='touch')['playful']
    assert pet.get('a')['energy']['balance'] == 0


def test_tutor_struggles_and_progress_drive_reactions(emotions, monkeypatch):
    import agent
    monkeypatch.setattr(agent.llm, 'analyze', lambda *args: {
        'is_elementary_math': True, 'knowledge_id': 12, 'question_type': '几何应用题', 'raw_knowledge': None})
    monkeypatch.setattr(agent.llm, 'chat_stream', lambda *args: iter(['我们先读已知条件。[CONTINUE]']))
    client = TestClient(web_app.app)
    response = client.post('/api/sessions', json={'question': '长方形长12米宽8米，面积是多少？'})
    sid = response.json()['session_id']
    assert response.json()['pet_reaction']['name'] == 'thinking'
    names = []
    for _ in range(2):
        response = client.post('/api/replies', json={'session_id': sid, 'message': '我不会，不明白'})
        assert response.status_code == 200
        names.append(response.json()['pet_reaction']['name'])
    assert names == ['concerned', 'crying']
    response = client.post('/api/replies', json={'session_id': sid, 'message': '明白了，要求长方形面积'})
    assert response.json()['pet_reaction']['name'] == 'smile'
