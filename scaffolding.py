"""可核验题型的递进提示和子问题；子问题的结果不当作原题结果。"""
import re
from fractions import Fraction

import calculation
import prompts
import tutor_profile


def _number(value):
    return calculation.display(Fraction(value))


def _render(action, stage, question, fallback, **values):
    return tutor_profile.render_response('strategy_' + action.lower(), stage, question,
                                         fallback=fallback, **values)


def _set_substep(state, question, expression, expected, continuation=None):
    state['substep'] = dict(question=question, expression=expression, expected=str(expected),
                            tries=0, continuation=continuation)
    return question


def reply_to_substep(state, student, stage='compute', original_expression=''):
    """只接收受控数值，失败两次后演示这个小步骤，再回到原题。"""
    step = state.get('substep')
    if not step:
        return None
    text = calculation.normalize(student).rstrip('。!！')
    match = re.fullmatch(r'(\d+(?:\.\d+)?(?:/\d+)?)(?:元|颗|个|支|块|本|平方厘米|平方米|厘米|米)?', text)
    try:
        correct = bool(match and Fraction(match[1]) == Fraction(step['expected']))
    except (ValueError, ZeroDivisionError):
        correct = False
    if correct:
        evidence = list(state.get('energy_substeps', []))
        key = step['expression'] + '=' + step['expected']
        if key not in evidence:
            evidence.append(key)
        state['energy_substeps'] = evidence
        next_step = step.get('continuation')
        state['substep'] = next_step
        state['consecutive_errors'] = 0
        state['difficulty_key'] = ''
        state['teaching_level'] = 1
        action = 'BREAK_DOWN' if next_step else {'compute': 'GUIDE_CALCULATION', 'method': 'GUIDE_EQUATION'}.get(stage, 'GIVE_HINT')
        state.update(next_action=action, current_goal=action, student_state='小步骤已完成，回到当前任务')
        if next_step:
            return '这小步算对了，' + next_step['question']
        if stage == 'compute' and original_expression:
            return f'小例子这一步对了。回到原题你已经列出的{original_expression.replace("*", "×")}，再算一算得多少？'
        return '小例子这一步对了，回到原题，你能继续完成刚才那一步吗？'
    step['tries'] += 1
    if step['tries'] < 2:
        state.update(next_action='BREAK_DOWN', current_goal='BREAK_DOWN')
        expression = calculation.normalize(step['expression']).replace('÷', '/')
        division = re.fullmatch(r'(\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)', expression)
        if division:
            total, groups = division.groups()
            return f'先用乘法倒过来检查这个小例子：{groups}乘几能得到{total}？'
        multiplication = re.fullmatch(r'(\d+(?:\.\d+)?)\*(\d+(?:\.\d+)?)', expression)
        if multiplication:
            left, right = multiplication.groups()
            if left == '10' and Fraction(right) < 1:
                return f'先只看10元的小例子，把{right}化成十分之几，10元的这个比例是多少元？'
            return f'先把{left}×{right}分成更好算的两部分，你准备先算哪一部分？'
        return '换个检查办法，用逆运算核对这个小步骤，你会从哪个数开始？'
    state['substep'] = None
    state.update(next_action='GIVE_HINT', current_goal='GIVE_HINT')
    return f'这个小步骤是{step["expression"]}={_number(step["expected"])}，回到原题，你能接着试试吗？'


def response(stage, question, verified, state, work=None):
    action, level = state['next_action'], state['teaching_level']
    if action == 'CHECK_REASONABLENESS' and isinstance(verified, calculation.Discount):
        return _render(action, stage, question, '打折后要付的钱一般比原价多还是少？')
    if state['error_type'] == 'UNIT_ERROR' and work:
        if level >= 3:
            unit = '元' if isinstance(verified, calculation.Discount) else verified.answer_unit
            return _render('check_unit', stage, question,
                f'数值已经算对了，这里要用“{unit}”表示，你能补上单位吗？', unit=unit)
        return None
    if level < 3 or verified is None:
        return None
    if state['error_type'] == 'CALCULATION_ERROR' and work and work.expression:
        if level >= 6:
            return f'保留你列对的算式{work.expression.replace("*", "×")}，只重新检查这一步的计算，结果是多少？'
        if isinstance(verified, calculation.Discount):
            values = prompts.discount_values(question)
            prompt = _render('simplify_numbers', 'compute', question,
                f'先换成原价10元的小例子，同样打{values["discount"]}，要付多少元？', **values)
            return _set_substep(state, prompt, f'10×{values["per_one"]}', 10 * verified.rate)
        if isinstance(verified, calculation.EqualShare):
            prompt = '先看小例子：6颗糖平均分给2个人，每人分到几颗？'
            return _set_substep(state, prompt, '6÷2', 3)
        if isinstance(verified, calculation.Rectangle):
            if not verified.area:
                prompt = f'我们先拆小，只算括号里的{_number(verified.length)}+{_number(verified.width)}，是多少？'
                return _set_substep(state, prompt, f'{_number(verified.length)}+{_number(verified.width)}',
                                    verified.length + verified.width)
            if verified.length > 10:
                rest = verified.length - 10
                next_step = dict(question=f'再只算{_number(rest)}×{_number(verified.width)}，是多少？',
                                 expression=f'{_number(rest)}×{_number(verified.width)}',
                                 expected=str(rest * verified.width), tries=0, continuation=None)
                prompt = f'把长拆成10和{_number(rest)}，先只算10×{_number(verified.width)}，是多少？'
                return _set_substep(state, prompt, f'10×{_number(verified.width)}', 10 * verified.width, next_step)
            # 原数值已经很小时，拆成重复相加，保留最后一步给学生。
            return f'先把{_number(verified.length)}×{_number(verified.width)}看成相同数量相加，你能从第一组数起吗？'
    if state['error_type'] in ('RELATION_ERROR', 'OPERATION_ERROR', 'EQUATION_ERROR'):
        if level >= 6:
            if isinstance(verified, calculation.Discount):
                factor = prompts.discount_values(question)['per_one']
                return f'关键关系是现价=原价×{factor}，你能把本题的原价放进去列式吗？'
            if isinstance(verified, calculation.EqualShare):
                return '每人分到的数量=总数÷人数，你能把本题的总数和人数放进去吗？'
            relation = '长×宽' if verified.area else '(长+宽)×2'
            return f'这里用{relation}，你能把题目中的长和宽放进算式吗？'
        if level >= 5 and isinstance(verified, calculation.Discount):
            values = prompts.discount_values(question)
            prompt = f'先只看10元的小例子，打{values["discount"]}时要付多少元？'
            return _set_substep(state, prompt, f'10×{values["per_one"]}', 10 * verified.rate)
        return prompts.build_method_hint(question, 2)
    if state['error_type'] in ('CONCEPT_ERROR', 'READ_ERROR') and level >= 5:
        if isinstance(verified, calculation.Discount):
            values = prompts.discount_values(question)
            if level >= 6:
                return f'{values["discount"]}就是原来每10元只付{values["per_ten"]}元，这题要找打折前还是打折后的价格？'
            prompt = f'我们只看原价10元，打{values["discount"]}时要付多少元？'
            return _set_substep(state, prompt, f'10×{values["per_one"]}', 10 * verified.rate)
    return None
