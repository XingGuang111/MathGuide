import io
import json
from unittest.mock import Mock

from fastapi.testclient import TestClient
from PIL import Image,ImageDraw
import pytest

import config
import db
import homework
import homework_review
import ocr
import vision
import visual_reasoning
from review_quality import QUALITY_VERSION
import web_app


VISUAL=dict(verdict='correct', feedback='我们一起检查对应点。',explanation='B点到对称轴的距离与对应点不相等。',
            reflection_prompt='你会怎样检查对应点？',knowledge_point='轴对称',correct_option='B',
            diagram_clear=True,image_question='图中不正确的点是（）。A.A B.B C.C D.D')


SOLVED=dict(task_kind='single_choice',image_question='图中不正确的点是（）。',readable=True,answer='B',explanation='B点到对称轴的距离与对应点不相等。',knowledge_point='轴对称',options=[dict(label=letter,meets_requirement=letter=='B',reason='检查对应点距离。') for letter in 'ABCD'])
AUDIT=dict(agree=True,verified_answer='B',reason='逐项检查后结论一致。')

def model_response(**kwargs):
    data=AUDIT if 'verified_answer' in kwargs['format'].get('properties',{}) else SOLVED
    return {'message':{'content':json.dumps(data)}}


@pytest.fixture
def picture():
    image=Image.new('RGB',(400,400),'white')
    draw=ImageDraw.Draw(image)
    draw.rectangle((30,90,100,140),fill='black')
    output=io.BytesIO();image.save(output,format='PNG')
    return output.getvalue()


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'DB_PATH',str(tmp_path/'pictures.db'))
    db.init_db()
    return TestClient(web_app.app)


def prepare(client,picture,monkeypatch):
    source=client.post('/api/homework/sources',files={'image':('page.png',picture,'image/png')}).json()
    box=lambda y:[[5,y],[390,y],[390,y+12],[5,y+12]]
    lines=[dict(text=text,box=box(y),confidence=.99) for text,y in [('数学作业',10),('一.选择题',30),('1.图中不正确的点是（）',50),('A.A B.B C.C D.D',160),('二.填空题',200),('2.图形有几条对称轴？',230)]]
    monkeypatch.setattr(ocr,'recognize_layout',lambda path:lines)
    recognized=client.post('/api/homework/sources/'+source['id']+'/recognize').json()
    first=recognized['result']['questions'][0]
    payload=dict(revision=0,title='图形作业',date='2026-11-01',source_ids=[source['id']],
                 items=[dict(id='with-image',text=first['text'],answer='B',source_ids=[source['id']],source_regions=first['source_regions'])])
    assert client.put('/api/homework/assignments/visual',json=payload).status_code==200
    review=dict(item_id='with-image',title='图形作业',assignment_date='2026-11-01',question=first['text'],answer='B')
    return source,recognized,payload,review


def test_crop_preserves_picture_options_and_omits_next_section(client,picture,monkeypatch):
    source,recognized,payload,_=prepare(client,picture,monkeypatch)
    questions=recognized['result']['questions']
    assert len(questions)==2
    assert '选择题' not in questions[0]['text']
    assert '填空题' not in questions[0]['text']
    assert '不正确' in questions[0]['text']
    assert questions[0]['source_regions'][0]['box'][3]<500
    response=client.get(questions[0]['image_url'])
    image=Image.open(io.BytesIO(response.content))
    # The drawing is below the first OCR line but must stay inside the crop.
    assert image.getpixel((40,60))==(0,0,0)
    assert image.height>110
    for box in ['0,300,1000,200','0,0,1001,400','x,y,z,w']:
        assert client.get(source['url']+'?box='+box).status_code==422
    db.init_db()
    restored=client.get('/api/homework/assignments/visual').json()
    assert restored['items'][0]['source_regions']==payload['items'][0]['source_regions']


def test_actual_image_reaches_model_and_stays_with_record(client,picture,monkeypatch):
    _,_,_,review=prepare(client,picture,monkeypatch)
    monkeypatch.setattr(vision,'status',lambda:dict(ok=True,model=config.VISION_MODEL_NAME))
    chat=Mock(side_effect=model_response)
    monkeypatch.setattr(vision._client,'chat',chat)
    response=client.post('/api/homework/reviews',json=review)
    assert response.status_code==200,response.text
    data=response.json()
    assert data['analysis']['verification']=='local_vision'
    sent=chat.call_args.kwargs['messages'][-1]['images']
    assert len(sent)==1 and Image.open(io.BytesIO(sent[0])).width>400
    assert len(data['attachments'])==1
    assert client.get(data['attachments'][0]['url']).status_code==200
    assert client.post('/api/homework/reviews',json=review).json()['id']==data['id']
    assert chat.call_count==2
    client.patch('/api/homework/reviews/'+data['id'],json={'in_mistakes':True})
    assert client.get('/api/homework/reviews?collection=mistakes').json()[0]['attachments']==data['attachments']


def test_changed_picture_invalidates_previous_analysis(client,picture,monkeypatch):
    _,_,payload,review=prepare(client,picture,monkeypatch)
    monkeypatch.setattr(homework_review,'analyze_visual',lambda *args:VISUAL)
    first=client.post('/api/homework/reviews',json=review).json()
    payload['revision']=1
    payload['items'][0]['source_regions'][0]['box'][3]-=10
    changed=client.put('/api/homework/assignments/visual',json=payload).json()
    assert changed['items'][0]['status']=='todo'
    second=client.post('/api/homework/reviews',json=review).json()
    assert first['id']!=second['id']
    assert first['attachments']!=second['attachments']


def test_no_visual_model_does_not_fall_back_to_text_grading(client,picture,monkeypatch):
    _,_,_,review=prepare(client,picture,monkeypatch)
    monkeypatch.setattr(vision,'status',lambda:dict(ok=False,model=config.VISION_MODEL_NAME))
    text=Mock();monkeypatch.setattr(homework_review,'analyze',text)
    assert client.post('/api/homework/reviews',json=review).status_code==503
    assert client.get('/api/homework/reviews').json()==[]
    text.assert_not_called()


def test_choice_about_incorrect_point_grades_the_selected_option(monkeypatch):
    solution=dict(verified=True,task_kind='single_choice',answer='B',explanation='B点的位置不符合要求。',knowledge_point='轴对称',image_question='不正确的点是（）',verification='local_vision',quality_version=QUALITY_VERSION)
    monkeypatch.setattr(visual_reasoning,'solve',lambda *args,**kwargs:solution)
    assert homework_review.analyze_visual('不正确的点是（）','B',[b'image'])['verdict']=='correct'
    assert homework_review.analyze_visual('不正确的点是（）','A',[b'image'])['verdict']=='incorrect'
    solution['verified']=False
    assert homework_review.analyze_visual('不正确的点是（）','B',[b'image'])['verdict']=='uncertain'


def test_visual_arithmetic_checks_transcription_from_image(monkeypatch):
    monkeypatch.setattr(visual_reasoning,'solve',lambda *args,**kwargs:dict(verified=True,task_kind='numeric',answer='14',explanation='13+1=14。',knowledge_point='加法',image_question='13+1=?',verification='local_vision',quality_version=QUALITY_VERSION))
    result=homework_review.analyze_visual('12+1=?','14',[b'image'])
    assert result['verdict']=='correct'
    assert '13+1' in result['explanation']


def test_visual_tutor_persists_and_retries_without_duplicate_turn(client,picture,monkeypatch):
    _,_,_,_=prepare(client,picture,monkeypatch)
    monkeypatch.setattr(visual_reasoning,'solve',lambda *args,**kwargs:dict(verified=True,task_kind='single_choice',answer='B',explanation='对应点距离相等。',knowledge_point='轴对称',image_question='不正确的点是（）',verification='local_vision',quality_version=QUALITY_VERSION))
    model=Mock(return_value={'reply':'先找到对称轴，你准备观察哪一对点？'})
    monkeypatch.setattr(vision,'json_reply',model)
    body=dict(message='我看不懂这幅图',request_id='turn-1')
    url='/api/homework/items/with-image/visual-tutor'
    assert client.post(url,json=body).status_code==200
    assert client.post(url,json=body).status_code==200
    assert model.call_count==1
    db.init_db()
    assert len(client.get(url).json()['messages'])==2
    assert client.post(url,json={**body,'message':'different'}).status_code==409
    assert db.query_history()==[]


def test_visual_reading_keeps_region_and_denial_word(client,picture,monkeypatch):
    _,_,payload,_=prepare(client,picture,monkeypatch)
    monkeypatch.setattr(vision,'json_reply',lambda *args,**kwargs:dict(text='不正确的点是（）。',visual_summary='选项见配图。',needs_review=False))
    result=client.post('/api/homework/vision/read',json=payload['items'][0]['source_regions'][0])
    assert result.status_code==200
    assert '不正确' in result.json()['text']
    assert 'source_regions' in client.get('/api/homework/assignments/visual').json()['items'][0]


def test_no_ocr_text_still_preserves_whole_picture(client,picture,monkeypatch):
    source=client.post('/api/homework/sources',files={'image':('diagram.png',picture,'image/png')}).json()
    monkeypatch.setattr(ocr,'recognize_layout',lambda path:[])
    result=client.post('/api/homework/sources/'+source['id']+'/recognize').json()['result']
    assert len(result['questions'])==1
    assert result['questions'][0]['source_regions'][0]['box']==[0,0,1000,1000]
    assert result['questions'][0]['low_confidence']


def test_transcription_does_not_add_inferred_geometry_to_printed_text(client,picture,monkeypatch):
    _,_,payload,_=prepare(client,picture,monkeypatch)
    monkeypatch.setattr(vision,'json_reply',lambda *args,**kwargs:dict(text='1.图中不正确的点是（）\nA.A B.B C.C D.D\n图中有一个红色等边三角形，其中三个顶点都是圆圈。',visual_summary='triangle',needs_review=False))
    result=client.post('/api/homework/vision/read',json=payload['items'][0]['source_regions'][0]).json()
    assert '三角形' not in result['text']
    assert 'A.A' in result['text']
    assert result['needs_review']
