import io
import time
from unittest.mock import Mock

from PIL import Image
import pytest
from fastapi.testclient import TestClient

import db
import homework
import homework_review
import ocr
import web_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app.config, 'DB_PATH', str(tmp_path / 'homework.db'))
    db.init_db()
    return TestClient(web_app.app)


def payload(**changes):
    return dict(revision=0, title='今日数学', date='2026-11-01',
                items=[dict(id='task-one', text='36÷6=?', answer='6')], **changes)


def png(color='white'):
    data = io.BytesIO()
    Image.new('RGB', (200, 100), color).save(data, format='PNG')
    return data.getvalue()


def test_durable_list_and_stale_writes(client):
    url='/api/homework/assignments/day-one'
    first=client.put(url, json=payload()).json()
    assert first['revision']==1
    assert first['items'][0]['answer']=='6'
    # A lost response can be retried without incrementing the revision.
    assert client.put(url, json=payload()).json()['revision']==1
    second={**payload(), 'revision':1}
    second['items'][0]['answer']='5'
    assert client.put(url,json=second).json()['revision']==2
    conflict=client.put(url,json=payload())
    assert conflict.status_code==409
    db.init_db()
    assert client.get(url).json()['items'][0]['answer']=='5'
    assert client.get('/api/homework/assignments?date=2026-11-01').json()[0]['total']==1
    assert client.get('/api/homework/assignments?date=2026-10-31').json()==[]


def test_snapshot_uses_server_analysis_not_client_completion(client,monkeypatch):
    result=dict(verdict='incorrect', feedback='检查除法', explanation='36÷6=6', reflection_prompt='怎样检查？', knowledge_point='除法')
    monkeypatch.setattr(homework_review,'analyze',lambda *args:result)
    url='/api/homework/assignments/one'
    data=payload()
    data['items'][0]['status']='done'
    assert client.put(url,json=data).json()['items'][0]['status']=='todo'
    review=client.post('/api/homework/reviews',json=dict(item_id='task-one', title='今日数学',assignment_date='2026-11-01',question='36÷6=?',answer='6')).json()
    snapshot=client.get(url).json()
    assert snapshot['items'][0]['status']=='revision'
    assert snapshot['items'][0]['review_id']==review['id']
    client.patch('/api/homework/reviews/'+review['id'],json=dict(reflection='需要验算',in_notes=True))
    summary=client.get('/api/homework/summary?date=2026-11-01').json()
    assert (summary['total'],summary['revision'],summary['reflections'],summary['notes'])==(1,1,1,1)
    assert summary['topics']==['除法']
    assert client.get('/api/homework/reviews?date=2026-10-31').json()==[]
    # Editing the answer invalidates completion without destroying the old evidence.
    data=payload();data['revision']=1;data['items'][0]['answer']='7'
    assert client.put(url,json=data).json()['items'][0]['status']=='todo'
    assert len(client.get('/api/homework/reviews').json())==1


def test_draft_and_item_ownership(client):
    data=payload();data['items']=[];data['draft']=dict(title='草稿',date='2026-11-01',batch='第一题',items=[dict(id='draft-item',text='')])
    assert client.put('/api/homework/assignments/draft-one',json=data).status_code==200
    restored=client.get('/api/homework/assignments/draft-one').json()
    assert restored['draft']['items'][0]['text']==''
    assert client.get('/api/homework/assignments').json()[0]['draft']
    data['draft']['items'][0]['text']='计算题'
    assert client.put('/api/homework/assignments/another',json=data).status_code==422


@pytest.mark.parametrize('change',[{'date':'invalid'},{'items':[{'id':'one','text':''}]},
                                  {'items':[{'id':'x','text':'a'},{'id':'x','text':'b'}]},
                                  {'source_ids':['not-present']}])
def test_invalid_lists(client,change):
    response=client.put('/api/homework/assignments/list',json={**payload(),**change})
    assert response.status_code in (422,404)
    assert client.get('/api/homework/assignments').json()==[]


def test_image_upload_deduplication_and_ocr_retry(client,monkeypatch):
    one=client.post('/api/homework/sources',files={'image':('one.png',png(),'image/png')}).json()
    two=client.post('/api/homework/sources',files={'image':('two.png',png(),'image/png')}).json()
    assert one['id']==two['id']
    assert client.get(one['url']).content==homework.image_bytes(one['id'])
    box=[[0,0],[150,0],[150,20],[0,20]]
    lines=[dict(text='练习：每题写出算式',box=box,confidence=.99),
           dict(text='1. 36÷6=?',box=box,confidence=.99),
           dict(text='2. 长方形长8厘米宽5厘米',box=box,confidence=.7),
           dict(text='面积是多少？',box=box,confidence=.95)]
    model=Mock(side_effect=[ocr.OCRError('本页模糊'),lines])
    monkeypatch.setattr(ocr,'recognize_layout',model)
    url='/api/homework/sources/'+one['id']+'/recognize'
    failed=client.post(url).json()
    assert failed['result'] is None and failed['error']=='本页模糊'
    success=client.post(url).json()
    questions=success['result']['questions']
    assert len(questions)==2
    assert all('每题写出算式' in row['text'] for row in questions)
    assert '面积是多少' in questions[1]['text'] and questions[1]['low_confidence']
    assert client.post(url).json()['result']==success['result']
    assert model.call_count==2  # Cached recognition does not run again.
    data=payload();data['source_ids']=[one['id']];data['items'][0]['source_ids']=[one['id']]
    assert client.put('/api/homework/assignments/photo-list',json=data).status_code==200
    db.init_db()
    assert client.get('/api/homework/assignments/photo-list').json()['sources'][0]['result']==success['result']


def test_invalid_image_and_missing_source(client):
    assert client.post('/api/homework/sources',files={'image':('bad.png',b'not image','image/png')}).status_code==422
    assert client.get('/api/homework/sources/missing/image').status_code==404
    assert client.post('/api/homework/sources/missing/recognize').status_code==404


def test_split_without_numbers_does_not_guess_independent_questions():
    box=[[0,0],[10,0],[10,10],[0,10]]
    lines=[dict(text='一个长方形',box=box,confidence=.9),dict(text='面积是多少？',box=box,confidence=.9)]
    assert len(homework.split_page(lines))==1


def test_layout_keeps_reading_order_and_boxes(monkeypatch):
    box=[[1,2],[3,2],[3,4],[1,4]]
    monkeypatch.setattr(ocr,'_get_engine',lambda:lambda path:([[box,'第二行',.98],[box,'第一行',.5]],0))
    result=ocr.recognize_layout('unused.png')
    assert [line['text'] for line in result]==['第二行','第一行']
    assert result[0]['box'][0]==[1.0,2.0]


def test_compact_ocr_numbering_is_flagged_for_correction():
    box=[[0,0],[10,0],[10,10],[0,10]]
    lines=[dict(text=text,box=box,confidence=.99) for text in ['1.计算题','2.面积题','3.24颗糖平均分给6人']]
    result=homework.split_page(lines)
    assert len(result)==3 and result[-1]['low_confidence']


def test_homework_session_survives_ttl_and_restart(client,monkeypatch):
    web_app._sessions.clear()
    data=payload();data['items'][0]['text']='长方形长8厘米，宽5厘米，面积是多少？'
    client.put('/api/homework/assignments/tutor-list',json=data)
    monkeypatch.setattr(web_app.agent_mod.llm,'analyze',lambda *args:dict(is_elementary_math=True,knowledge_id=12,question_type='几何应用题',raw_knowledge=None))
    response=client.post('/api/sessions',json=dict(question=data['items'][0]['text'],homework_item_id='task-one'))
    assert response.status_code==200
    sid=response.json()['session_id']
    assert client.get('/api/homework/assignments/tutor-list').json()['items'][0]['tutor_session_id']==sid
    web_app._activity[sid]=time.time()-2*web_app.SESSION_TTL
    web_app._persist()
    assert client.get('/api/sessions/'+sid).status_code==200
    web_app._sessions.clear()
    web_app._restore()
    restored=client.get('/api/sessions/'+sid).json()
    assert restored['homework_item_id']=='task-one'
    assert restored['question']==data['items'][0]['text']
    invalid=client.post('/api/sessions',json=dict(question='被编辑的题干',homework_item_id='task-one'))
    assert invalid.status_code==422
    web_app._sessions.clear()
