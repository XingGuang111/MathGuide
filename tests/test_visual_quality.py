import io
import json

import numpy as np
from PIL import Image
import pytest

import config
import db
import homework_review
import visual_checks
import visual_reasoning
import vision
from review_quality import QUALITY_VERSION,safe_analysis


QUESTION='E是一个轴对称图形的一半，补全另一半后不可能是（）。'


def worksheet(kinds):
    canvas=np.full((140,640),255,dtype='uint8')
    glyph=np.zeros((22,14),dtype='uint8');glyph[:,:3]=1;glyph[:3,:]=1;glyph[-3:,:]=1;glyph[9:12,:-2]=1
    def paste(mask,x,y):
        h,w=mask.shape;canvas[y:y+h,x:x+w]=255-mask*255
    lines=[dict(text=QUESTION,box=[[3,3],[630,3],[630,25],[3,25]],confidence=1)]
    for i,kind in enumerate(kinds):
        x=i*155
        if kind=='same':paste(glyph,x+35,80);paste(glyph,x+60,80)
        elif kind=='vertical':paste(np.fliplr(glyph),x+35,80);paste(glyph,x+60,80)
        elif kind=='horizontal':paste(glyph,x+35,48);paste(glyph,x+35,80)
        elif kind=='diagonal':paste(glyph,x+30,80);paste(glyph.T,x+62,49)
        lines.append(dict(text=chr(65+i)+'.图形',box=[[x+10,88],[x+100,88],[x+100,105],[x+10,105]],confidence=1))
    output=io.BytesIO();Image.fromarray(canvas).save(output,format='PNG')
    return output.getvalue(),lines


@pytest.mark.parametrize('kinds,expected',[
    (['same','vertical','horizontal','diagonal'],'A'),
    (['horizontal','same','diagonal','vertical'],'B'),
    (['diagonal','horizontal','same','vertical'],'C'),
    (['vertical','diagonal','horizontal','same'],'D'),
])
def test_reflection_geometry_checks_option_pixels_not_fixed_answer(kinds,expected):
    image,lines=worksheet(kinds)
    result=visual_checks.reflection_options(QUESTION,image,lines)
    assert result is not None
    assert result['answer']==expected
    possible={row['label']:row['possible'] for row in result['options']}
    assert possible[expected] is False
    assert sum(possible.values())==3


@pytest.fixture
def database(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'DB_PATH',str(tmp_path/'quality.db'));db.init_db()


def solution(answer='A'):
    return dict(task_kind='single_choice',image_question=QUESTION,readable=True,answer=answer,
                explanation=f'因此应选{answer}。',knowledge_point='轴对称',
                options=[dict(label=letter,meets_requirement=letter==answer,reason='实际翻折核对。') for letter in 'ABCD'])


def test_blind_solution_and_audit_do_not_receive_student_answer(database,monkeypatch):
    monkeypatch.setattr(visual_checks,'check',lambda *args:None)
    calls=[]
    def reply(system,payload,images,schema,**kwargs):
        calls.append(payload)
        if 'verified_answer' in schema['properties']:return dict(agree=True,verified_answer='A',reason='图形朝向检查一致。')
        return solution()
    monkeypatch.setattr(vision,'json_reply',reply)
    first=homework_review.analyze_visual(QUESTION,'D',[b'one-image'])
    second=homework_review.analyze_visual(QUESTION,'A',[b'one-image'])
    assert first['verdict']=='incorrect' and second['verdict']=='correct'
    assert first['correct_option']==second['correct_option']=='A'
    assert len(calls)==2  # The same verified solution is reused for another student choice.
    assert all('学生作答' not in json.dumps(payload,ensure_ascii=False) for payload in calls)


def test_contradictory_option_flags_are_not_published(database,monkeypatch):
    monkeypatch.setattr(visual_checks,'check',lambda *args:None)
    invalid=solution('C');invalid['options']=[dict(label=letter,meets_requirement=letter=='D',reason='检查图形。') for letter in 'ABCD']
    monkeypatch.setattr(vision,'json_reply',lambda *args,**kwargs:invalid)
    result=homework_review.analyze_visual(QUESTION,'D',[b'image'])
    assert result['verdict']=='uncertain' and result['correct_option'] is None


def test_disagreeing_independent_audit_abstains(database,monkeypatch):
    monkeypatch.setattr(visual_checks,'check',lambda *args:None)
    def reply(system,payload,images,schema,**kwargs):
        return dict(agree=False,verified_answer='D',reason='候选结论与解释不一致。') if 'verified_answer' in schema['properties'] else solution('C')
    monkeypatch.setattr(vision,'json_reply',reply)
    result=homework_review.analyze_visual(QUESTION,'D',[b'image'])
    assert result['verdict']=='uncertain'
    assert '选错' not in result['feedback']


def test_unchecked_old_visual_judgments_are_not_reused_as_evidence():
    old=dict(verdict='incorrect',correct_option='C',explanation='D不可能。',verification='local_vision')
    safe=safe_analysis(old)
    assert safe['verdict']=='uncertain' and safe['needs_reanalysis']
    assert old['verdict']=='incorrect'
    assert safe_analysis({**old,'quality_version':QUALITY_VERSION})['verdict']=='incorrect'


def test_verified_reflection_tutor_does_not_reverse_possible_and_impossible():
    from homework_visual import _reflection_guidance
    image,lines=worksheet(['same','vertical','horizontal','diagonal'])
    evidence=visual_checks.reflection_options(QUESTION,image,lines)
    result=_reflection_guidance(dict(evidence=evidence,answer='A',explanation=evidence['explanation']),'我选D，对吗？')
    assert 'D可以补出来' in result
    assert '斜线' in result
    assert 'D不可能' not in result
