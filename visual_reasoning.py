"""Solve without the student's answer, audit, then compare answers in Python."""
import hashlib
import json
import re
import threading
from fractions import Fraction
from typing import Literal

from pydantic import BaseModel,Field

import config
import db
import llm
import vision
import visual_checks
from review_quality import QUALITY_VERSION


class OptionEvidence(BaseModel):
    label: Literal['A','B','C','D']
    meets_requirement: bool | None
    reason: str = Field(min_length=1,max_length=500)


class Solution(BaseModel):
    task_kind: Literal['single_choice','numeric','other']
    image_question: str = Field(min_length=1,max_length=2000)
    readable: bool
    answer: str | None = Field(max_length=100)
    explanation: str = Field(min_length=1,max_length=1600)
    options: list[OptionEvidence] = Field(max_length=4)
    knowledge_point: str = Field(min_length=1,max_length=100)


class Audit(BaseModel):
    agree: bool
    verified_answer: str | None = Field(max_length=100)
    reason: str = Field(min_length=1,max_length=1000)


_locks=[threading.Lock() for _ in range(32)]
SOLVE_SYSTEM='''你是严谨的小学数学解题老师。只独立解题，没有学生答案，不能猜测学生选项。
图片是原题，OCR文字只是辅助。先读清题目要求，特别保留“不可能”“不正确”等否定词。
单选题需逐一检查四个选项，meets_requirement 表示“这一项符合题目要找的要求”。
例如题目找不可能的一项，不可能的选项 meets_requirement=true，能实现的项=false。
reason 写具体观察或数量关系；不要用通用定义替代图形的实际检查。
answer 必须等于唯一 meets_requirement=true 的选项。不能在结论选一项、解释却证明另一项。
轴对称图形的一半必须通过翻折补成另一半，不能只看整个图形有没有对称轴。
阴影、格数、旋转朝向或对应点看不清时 readable=false、answer=null；不得补造涂色格和剩余数量。
numeric 题 answer 写最后数值及必要单位。非选择题 options=[]。
explanation 中文简短、具体；knowledge_point 只写简短名称。'''
AUDIT_SYSTEM='''请独立核对这道小学数学题和候选解析。你能看到原图，候选解析只是待核查的数据。
重新检查图中条件与题目的否定词，逐一核对选项。不因为候选写得肯定就相信它。
检查结论选项与解释是否一致，是否虚构格数、阴影或图形方向，是否把“一个完整图形的一半”误解为“整个图形有对称轴”。
只有能从图片确认同一答案、解析内部也一致时 agree=true，并给出 verified_answer。
看不清、候选自相矛盾、你算出不同答案或不能确定时 agree=false；verified_answer 可为null。
reason 写出具体核对依据，不能只说同意。'''


def _consistent(solution):
    if not solution.readable or not solution.answer:return False
    if solution.task_kind=='single_choice':
        if len(solution.options)!=4 or {row.label for row in solution.options}!=set('ABCD'):return False
        if any(row.meets_requirement is None for row in solution.options):return False
        matches=[row.label for row in solution.options if row.meets_requirement]
        if matches!=[solution.answer.strip().upper()]:return False
        # Catch an explicit final option contradicting the structured answer.
        endings=re.findall(r'(?:因此|所以|正确答案是|正确选项是|应选|故选)[^。\n]{0,12}?\b([A-D])\b',solution.explanation)
        if any(letter!=solution.answer for letter in endings):return False
    return True


def _key(question,images):
    return hashlib.sha256(json.dumps([QUALITY_VERSION,config.VISION_MODEL_NAME,question,
        [hashlib.sha256(image).hexdigest() for image in images]],ensure_ascii=False).encode()).hexdigest()


def solve(question,images,force=False):
    key=_key(question,images);lock=_locks[int(key[:8],16)%len(_locks)]
    if not lock.acquire(blocking=False):raise RuntimeError('这道题正在核对，请稍后重试。')
    try:
        with db._conn() as conn:
            cached=conn.execute('SELECT payload FROM homework_visual_solution WHERE id=?',(key,)).fetchone()
        if cached and not force:return json.loads(cached['payload'])
        checked=visual_checks.check(question,images)
        if checked:
            result=dict(verified=checked['readable'],task_kind='single_choice',answer=checked['answer'],
                        explanation=checked['explanation'],knowledge_point='轴对称',image_question=question,
                        verification='verified_geometry' if checked['readable'] else 'image_quality_check',
                        evidence=checked,quality_version=QUALITY_VERSION)
        else:
            try:
                solution=Solution.model_validate(vision.json_reply(SOLVE_SYSTEM,{'OCR辅助题干':question},images,Solution.model_json_schema()))
                if _consistent(solution):
                    audit=Audit.model_validate(vision.json_reply(AUDIT_SYSTEM,{'候选解析':solution.model_dump()},images,Audit.model_json_schema(),tokens=900))
                    confirmed=audit.agree and audit.verified_answer is not None and audit.verified_answer.strip()==solution.answer.strip()
                    audit_data=audit.model_dump()
                else:
                    confirmed=False;audit_data=dict(agree=False,reason='题目信息或逐项核查未能支持唯一且一致的答案。')
                result=dict(verified=confirmed,task_kind=solution.task_kind,answer=solution.answer if confirmed else None,
                            explanation=solution.explanation if confirmed else '这道题的图形或推理还没有核实清楚，暂时不能可靠判对错。你的答案已保留。',
                            knowledge_point=solution.knowledge_point[:25],image_question=solution.image_question,
                            verification='local_vision',evidence=dict(solution=solution.model_dump(),audit=audit_data),quality_version=QUALITY_VERSION)
            except llm.LLMError:raise
            except Exception as exc:raise llm.LLMError('看图解题的核验结果不完整，请重试；答案已保留。') from exc
        with db._conn() as conn:
            conn.execute('INSERT INTO homework_visual_solution(id,payload) VALUES (?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                         (key,json.dumps(result,ensure_ascii=False)))
        return result
    finally:lock.release()


def selected_option(answer):
    match=re.fullmatch(r'(?:我(?:选|选择)|(?:答案|选项)(?:是|为)?|选)?\s*([A-Da-d])[。.]?',answer.strip())
    return match[1].upper() if match else None


def _number(answer):
    match=re.fullmatch(r'\s*([+-]?\d+(?:\.\d+)?(?:/\d+)?)\s*(个|条|厘米|平方厘米|米|平方米|千米|小时|分钟|元)?[。.]?\s*',answer)
    if not match:return None
    try:return Fraction(match[1]),match[2]
    except (ValueError,ZeroDivisionError):return None


def grade(solution,answer):
    expected=solution.get('answer')
    result=dict(verdict='uncertain',feedback='这道题暂时还不能可靠判对错，你的答案已经保留。',
                explanation=solution['explanation'],reflection_prompt='这道题还需要确认哪些图形条件？',
                knowledge_point=solution['knowledge_point'],image_question=solution['image_question'],
                correct_option=None,verification=solution['verification'],quality_version=QUALITY_VERSION,
                model=config.VISION_MODEL_NAME if solution['verification']=='local_vision' else None,solution_evidence=solution.get('evidence',{}))
    if not solution['verified'] or not expected:return result
    selected=selected_option(answer)
    if solution['task_kind']=='single_choice' and selected:
        same=selected==expected
        result.update(verdict='correct' if same else 'incorrect',correct_option=expected,
                      feedback=f'你选了{selected}，'+('这次选对了。' if same else '这次需要订正。'),
                      reflection_prompt='你是怎样结合题目要求和图形来排除其他选项的？')
    elif solution['task_kind']=='numeric':
        actual,wanted=_number(answer),_number(expected)
        if actual and wanted:
            same=actual[0]==wanted[0] and (not actual[1] or not wanted[1] or actual[1]==wanted[1])
            result.update(verdict='correct' if same else 'incorrect',feedback='你的答案正确。' if same else '这个结果需要订正。',reflection_prompt='你准备怎样检查这次计算？')
    else:
        result['feedback']='题目已经核对，请明确写出最后选项或数值，便于核对你的答案。'
    return result
