"""教学诊断与策略：模型给建议，代码核验事实并决定动作，不向学生暴露状态。"""
import math
import re
from dataclasses import dataclass
from fractions import Fraction

import calculation


ERROR_TYPES = frozenset(('READ_ERROR', 'CONCEPT_ERROR', 'RELATION_ERROR', 'OPERATION_ERROR',
                         'EQUATION_ERROR', 'CALCULATION_ERROR', 'UNIT_ERROR', 'CARELESS_ERROR',
                         'MASTERED', 'UNKNOWN'))
ACTION_RULES = {
    'ASK_DIFFICULTY': '只问尚未明确的卡点，已经说过的内容不重问。',
    'EXPLAIN_CONCEPT': '只解释学生点名的一个题内概念，不接着讲本题计算。',
    'SIMPLIFY_NUMBERS': '保持本题数量关系，换成小数字举例，不代算本题。',
    'USE_LIFE_EXAMPLE': '用同一数量关系的生活例子解释，等待学生回答。',
    'BREAK_DOWN': '把当前困难拆小，一次只问一个子问题，记住已经答对的部分。',
    'GIVE_HINT': '给一个具体提示，不反复说再想想，不重复已掌握的内容。',
    'GUIDE_EQUATION': '引导学生列式，已经有正确算式时不要要求重写。',
    'GUIDE_CALCULATION': '保留已确认算式，只检查当前计算，不重新解释题意。',
    'CHECK_UNIT': '数值已经正确，只检查或补充单位，不再让学生重算。',
    'CHECK_REASONABLENESS': '只问结果与题目条件的大小是否合理，不公布正确答案。',
    'SUMMARIZE': '仅在本题确实完成后简短总结概念和数量关系。',
    'GIVE_VARIATION': '建议做一道同知识点的专项练习，由练习模块独立判分。',
    'FULL_EXPLANATION': '展示核验过的完整解法，标记为看过讲解，不当作独立掌握。',
}
_ERROR_LABELS = {
    'READ_ERROR': '需要核对题意', 'CONCEPT_ERROR': '需要理解概念',
    'RELATION_ERROR': '需要找到数量关系', 'OPERATION_ERROR': '需要分清运算关系',
    'EQUATION_ERROR': '需要检查列式', 'CALCULATION_ERROR': '算式已确认，需要检查计算',
    'UNIT_ERROR': '需要检查单位', 'CARELESS_ERROR': '需要核对抄写的条件',
    'MASTERED': '本题已解出，类似题掌握情况待练习验证', 'UNKNOWN': '继续核对当前一步',
}


def initial_state():
    return dict(grade=None, error_type='UNKNOWN', next_action='ASK_DIFFICULTY',
                teaching_level=1, attempt_count=0, consecutive_errors=0,
                difficulty_key='', current_goal='ASK_DIFFICULTY', student_state='尚未明确卡点',
                mastery='unknown', give_final_answer=False, source='rules',
                confirmed_steps=[], known_facts={}, concept_term='', emotional_support=False,
                substep=None)


@dataclass(frozen=True)
class Diagnosis:
    error_type: str = 'UNKNOWN'
    next_action: str = 'GIVE_HINT'
    confidence: float = 1.0
    reason: str = ''
    source: str = 'rules'
    concept_term: str = ''


def validate_diagnosis(data):
    """诊断概率只用于筛选建议，不能用于判分、跳阶段或自动揭示答案。"""
    if not isinstance(data, dict):
        raise ValueError('诊断必须是JSON对象')
    if (not isinstance(data.get('error_type'), str) or not isinstance(data.get('next_action'), str)
            or data['error_type'] not in ERROR_TYPES or data['next_action'] not in ACTION_RULES):
        raise ValueError('诊断包含无效的错误类型或教学动作')
    confidence = data.get('confidence')
    if type(confidence) not in (float, int) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise ValueError('confidence必须在0和1之间')
    reason = data.get('reason', '')
    if not isinstance(reason, str) or len(reason) > 240:
        raise ValueError('reason必须是简短的诊断依据')
    return Diagnosis(data['error_type'], data['next_action'], confidence, reason, 'model')


def requests_explanation(text):
    return (not re.search(r'不要|不用|不想|别', text)
            and bool(re.search(r'直接.*(?:答案|告诉我|讲解)|完整(?:的)?(?:过程|讲解|解法)|详细(?:的)?(?:过程|讲解|解法)', text)))


def emotional(text):
    return bool(re.search(r'太笨|我(?:很|好)?笨|数学好难|好难啊|又错了|我就是不会', text))


@dataclass(frozen=True)
class Work:
    response: str
    complete: bool
    expression: str
    result_correct: bool
    error_type: str
    next_action: str
    progressed: bool = False
    explicit_expression: bool = False


def looks_like_work(student):
    text = calculation.normalize(student).rstrip('。!！')
    return bool(re.fullmatch(r'[\d.()%+*/÷−-]+(?:=\d+(?:\.\d+)?(?:元|平方(?:千米|厘米|毫米|米)|千米|厘米|毫米|米)?)?', text)
                and re.search(r'[+*/÷−-]', text))


def assess_work(verified, student, previous_expression='', result_correct=False):
    if verified is None:
        return None
    response, complete, expression, correct = verified.guide(student, previous_expression, result_correct)
    text = calculation.normalize(student).rstrip('。.!！')
    text = re.sub(r'^(?:面积=长\*宽|周长=\(长\+宽\)\*2)[，,；;]?', '', text)
    text = re.sub(r'^(?:面积|周长|现价|价格|答案)(?:是|为|=)', '', text)
    candidate = text.split('=', 1)[0]
    explicit = verified.valid_expression(candidate)
    if complete:
        error, action = 'MASTERED', 'SUMMARIZE'
    elif '=' in text and not explicit:
        error, action = 'EQUATION_ERROR', 'GUIDE_EQUATION'
    elif correct:
        error, action = 'UNIT_ERROR', 'CHECK_UNIT'
    elif expression:
        if verified.valid_expression(text):
            error, action = 'UNKNOWN', 'GUIDE_CALCULATION'
        else:
            error, action = 'CALCULATION_ERROR', 'GUIDE_CALCULATION'
            numeric = re.search(rf'(?:^|=)({calculation.NUMBER})(?:元)?$', text)
            if isinstance(verified, calculation.Discount) and numeric and Fraction(numeric[1]) > verified.price:
                action = 'CHECK_REASONABLENESS'
    else:
        error, action = 'EQUATION_ERROR', 'GUIDE_EQUATION'
    numeric = re.search(rf'=({calculation.NUMBER})(?:元)?$', text)
    if (error == 'EQUATION_ERROR' and isinstance(verified, calculation.Discount)
            and numeric and Fraction(numeric[1]) > verified.price):
        action = 'CHECK_REASONABLENESS'
    progressed = complete or (correct and not result_correct) or bool(expression and expression != previous_expression)
    return Work(response, complete, expression, correct, error, action, progressed, explicit)


def diagnose_local(stage, text, needs_help=False, reading=None, work=None, method_valid=False,
                   concept_term=''):
    if requests_explanation(text):
        return Diagnosis(next_action='FULL_EXPLANATION')
    if concept_term:
        return Diagnosis('CONCEPT_ERROR', 'EXPLAIN_CONCEPT', concept_term=concept_term)
    if work is not None:
        return Diagnosis(work.error_type, work.next_action)
    if stage == 'understand':
        if reading and reading.correction:
            return Diagnosis('READ_ERROR', 'GIVE_HINT')
        if needs_help:
            return Diagnosis('CONCEPT_ERROR', 'EXPLAIN_CONCEPT')
        return Diagnosis('UNKNOWN', 'GIVE_HINT')
    if stage == 'method':
        if method_valid:
            return Diagnosis(next_action='GUIDE_EQUATION')
        if needs_help or re.search(r'加|减|乘|除|公式|方法|懂了', text):
            return Diagnosis('OPERATION_ERROR' if re.search(r'加|减|乘|除', text) else 'RELATION_ERROR', 'GIVE_HINT')
    return Diagnosis()


def constrain(diagnosis, stage):
    """模型诊断不允许跨阶段判掌握或触发完整讲解。"""
    if diagnosis.source != 'model':
        return diagnosis
    actions = {'ASK_DIFFICULTY', 'EXPLAIN_CONCEPT', 'SIMPLIFY_NUMBERS', 'USE_LIFE_EXAMPLE',
               'BREAK_DOWN', 'GIVE_HINT'}
    if stage != 'understand':
        actions |= {'GUIDE_EQUATION', 'CHECK_REASONABLENESS'}
    if stage == 'compute':
        actions |= {'GUIDE_CALCULATION', 'CHECK_UNIT'}
    error = diagnosis.error_type
    if error == 'MASTERED':
        error = 'UNKNOWN'
    if stage == 'understand' and error in ('EQUATION_ERROR', 'CALCULATION_ERROR', 'UNIT_ERROR'):
        error = 'READ_ERROR'
    action = diagnosis.next_action if diagnosis.next_action in actions else 'GIVE_HINT'
    return Diagnosis(error, action, diagnosis.confidence, diagnosis.reason, 'model')


def advance_state(previous, diagnosis, stage, *, student='', progressed=False, facts=None):
    state = {**initial_state(), **previous}
    state['confirmed_steps'] = list(state['confirmed_steps'])
    state['known_facts'] = dict(state['known_facts'])
    state['attempt_count'] += 1
    key = ':'.join((stage, diagnosis.error_type, diagnosis.concept_term))
    has_error = diagnosis.error_type not in ('UNKNOWN', 'MASTERED')
    count = (state['consecutive_errors'] + 1 if key == state['difficulty_key'] else 1) if has_error else 0
    if progressed and diagnosis.error_type in ('UNKNOWN', 'UNIT_ERROR', 'MASTERED'):
        count = 0
    action = diagnosis.next_action
    level = 1
    if action == 'EXPLAIN_CONCEPT':
        level = min(6, max(2, count + 1))
        action = {2: 'EXPLAIN_CONCEPT', 3: 'SIMPLIFY_NUMBERS', 4: 'USE_LIFE_EXAMPLE',
                  5: 'BREAK_DOWN', 6: 'GIVE_HINT'}[level]
    elif has_error and count >= 2:
        level = min(6, count + 1)
        action = {3: 'SIMPLIFY_NUMBERS', 4: 'USE_LIFE_EXAMPLE', 5: 'BREAK_DOWN', 6: 'GIVE_HINT'}[level]
    # 模型不能凭概率触发讲解；连续六次在同一卡点失败才启动兜底。
    if count >= 6 or requests_explanation(student):
        level, action = 7, 'FULL_EXPLANATION'
    if facts:
        state['known_facts'].update(facts)
    if emotional(student) and has_error and level < 3:
        level, action = 3, 'BREAK_DOWN'
    if re.search(r'举例|例子|换个例', student) and level < 3:
        level, action = 3, 'SIMPLIFY_NUMBERS'
    state.update(error_type=diagnosis.error_type, next_action=action, teaching_level=level,
                 consecutive_errors=count, difficulty_key=key, current_goal=action,
                 student_state=_ERROR_LABELS[diagnosis.error_type], source=diagnosis.source,
                 give_final_answer=action == 'FULL_EXPLANATION', concept_term=diagnosis.concept_term,
                 emotional_support=emotional(student))
    return state


def mark_progress(state, stage, completed=False, explained=False):
    state['consecutive_errors'] = 0
    state['difficulty_key'] = ''
    state['teaching_level'] = 1
    if stage not in state['confirmed_steps'] and not explained:
        state['confirmed_steps'].append(stage)
    state['substep'] = None
    if explained:
        state.update(mastery='explanation_seen', next_action='GIVE_VARIATION', current_goal='GIVE_VARIATION',
                     give_final_answer=True, teaching_level=7)
    elif completed:
        state.update(mastery='solved_current', error_type='MASTERED', next_action='SUMMARIZE', current_goal='SUMMARIZE',
                     student_state=_ERROR_LABELS['MASTERED'])
    else:
        action = 'GUIDE_EQUATION' if stage == 'method' else 'GIVE_HINT'
        state.update(mastery='guided', error_type='UNKNOWN', next_action=action, current_goal=action,
                     concept_term='', emotional_support=False)


def context(state):
    """只提供行动与已确认事实；模型诊断的自由文本不进入系统指令。"""
    return {key: value for key, value in state.items() if key not in ('grade', 'difficulty_key', 'source')}
