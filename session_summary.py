"""Build a short student-facing notebook from the tutor's existing evidence."""
import re

import calculation


def build(tutor):
    state = tutor.teaching_state
    steps = state.get('confirmed_steps', [])
    verified = (calculation.rectangle(tutor.question_text, tutor.question_card or tutor.card)
                or calculation.discount(tutor.question_text)
                or calculation.equal_share(tutor.question_text))
    reading = tutor._reading_progress() if tutor.state.value == 'STAGE1_UNDERSTAND' else None
    # While reading, reconstruct the current evidence so corrections remove old facts.
    facts = reading.facts if reading is not None else state.get('known_facts', {})
    conditions = []
    target = ''
    if isinstance(verified, calculation.Rectangle):
        conditions = [dict(label=key, value=calculation.display(value) + verified.unit,
                           confirmed=key in facts)
                      for key, value in [('长', verified.length), ('宽', verified.width)]]
        target = '长方形的' + ('面积' if verified.area else '周长')
    elif isinstance(verified, calculation.Discount):
        conditions = [dict(label='原价', value=calculation.display(verified.price) + '元',
                           confirmed='原价' in facts),
                      dict(label='折扣', value=calculation.display(verified.rate * 100) + '%',
                           confirmed='折扣' in facts)]
        target = '打折后需要付多少钱'
    elif isinstance(verified, calculation.EqualShare):
        conditions = [dict(label='物品总数', value=str(verified.total) + verified.answer_unit,
                           confirmed=False),
                      dict(label='人数', value=str(verified.people) + '人', confirmed=False)]
        target = '每个人分到多少'
    else:
        # Original question clauses remain explicitly attributed to the question.
        # Do not promote arbitrary student statements or model hints into facts.
        clauses = [part.strip() for part in re.split(r'[，,。；;\n]', tutor.question_text) if part.strip()]
        for clause in clauses:
            if re.search(r'求|多少|几[个米元本颗支时分天人]|计算|[?？]', clause):
                target = clause
            elif len(conditions) < 5:
                conditions.append(dict(label='题目条件', value=clause, confirmed=False))
    if not target:
        target = facts.get('target', '')
    method = tutor.previous_stage_answer if 'method' in steps else ''
    if not method and tutor.compute_expression:
        method = '数量关系已放进下面的算式。'
    labels = {'understand':'读懂题目', 'method':'找到方法', 'compute':'完成计算'}
    completed = [labels[key] for key in steps if key in labels]
    if tutor.finished:
        status = '本题已解出' if state.get('mastery') == 'solved_current' else '本题已看过讲解'
        next_step = '可以换一道题，或试一道同类题。'
    else:
        status, next_step = {
            'STAGE1_UNDERSTAND': ('读懂题目', '先说清题目告诉了什么、要求什么。'),
            'STAGE2_METHOD': ('找到方法', '想想这些条件之间有什么关系。'),
            'STAGE3_COMPUTE': ('动手算算', '沿着已确认的思路，继续算式、结果或单位。'),
        }.get(tutor.state.value, ('准备开始', '先读一读题目。'))
    return dict(question=tutor.question_text, conditions=conditions,
                target=target, target_confirmed='target' in facts,
                method=method[:240], expression=tutor.compute_expression[:160],
                completed=completed, status=status, next_step=next_step)
