"""Compare recent teaching questions and choose an actually different next step."""
from difflib import SequenceMatcher
import re
import unicodedata


def normalize(text):
    text=unicodedata.normalize('NFKC',text)
    text=re.sub(r'\[(?:CONTINUE|UNDERSTOOD|CARD:\d+)\]','',text)
    text=re.sub(r'^(?:(?:对了|很好|好|没关系|我们|那|现在|接下来)[，,！!。 ]*)+','',text)
    return re.sub(r'\W','',text)


def intent(text):
    if re.search(r'单位.*[?？]|[?？].*单位',text): return 'unit'
    if re.search(r'(?:算式|列式).*[?？]',text): return 'equation'
    if re.search(r'(?:什么方法|什么公式|数量关系).*[?？]',text): return 'method'
    if re.search(r'(?:明白|清楚|理解).*(?:吗|[?？])',text): return 'understand'
    return ''


def clean(body):
    """Remove exact repeated sentences, never similar formulas with different numbers."""
    parts = re.findall(r'[^。！？!?\n]+[。！？!?]?|\n', body)
    questions = [part for part in parts if re.search(r'[？?]', part)]
    if len(questions) > 1:
        last = questions[-1]
        parts = [part for part in parts if part == last or not re.search(r'[？?]', part)
                 or not (re.search(r'记得|明白|清楚|对不对|好吗|你觉得呢', part)
                         or (_question_intent(part) and _question_intent(part) == _question_intent(last)
                             and re.findall(r'\d+(?:\.\d+)?', part) == re.findall(r'\d+(?:\.\d+)?', last)))]
    seen, result = set(), []
    for part in parts:
        key = normalize(part)
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        result.append(part)
    return ''.join(result).strip()


def focus_on_unit(body):
    """Drop a redundant quantity question only after the result is verified.

    Retain the model's explanation and unit request, never synthesize a reply.
    If no unit request exists, leave the candidate for the normal retry guard.
    """
    if '单位' not in body:
        return body
    parts = re.findall(r'[^。！？!?\n]+[。！？!?]?|\n', body)
    return ''.join(part for part in parts
                   if not (re.search(r'[？?]', part) and '单位' not in part)).strip()


def _question(body):
    parts = re.split(r'[。；;！!\n]', body)
    return next((part.strip() for part in reversed(parts) if re.search(r'[？?]', part)), '')


def _question_intent(question):
    if re.search(r'(?:列出|写出|列|写).{0,12}算式', question):
        return 'equation'
    if re.search(r'(?:得到|算出|算得).{0,15}(?:数值|结果)', question):
        return 'result'
    if re.search(r'(?:什么|哪个|哪种|怎样|怎么|想到).*(?:方法|公式|运算|数量关系)|(?:方法|公式|数量关系).*(?:什么|哪个|怎样)', question):
        return 'method'
    if re.search(r'(?:结果|算出|算得|等于).*(?:多少|几)|(?:多少|几).*(?:结果)', question):
        return 'result'
    if re.search(r'(?:求什么|找什么|哪个量|所求|要求什么)', question):
        return 'target'
    if re.search(r'什么意思|什么含义|表示什么|怎么理解', question):
        return 'concept'
    return intent(question)


def _new_support(body, previous):
    """A new concrete explanation/example is useful even when its check is similar."""
    prefix = body.rsplit(_question(body), 1)[0] if _question(body) else body
    return bool(normalize(prefix) and normalize(prefix) not in normalize(previous)
                and re.search(r'例如|小例子|想象|一轮|表示|就是|等于|每份|一样多|平方|[×÷=＝]|\d', prefix))


def repeated(body,history):
    candidate=normalize(body)
    if not candidate: return True
    for previous in history[-4:]:
        other=normalize(previous)
        if candidate==other: return True
        if len(candidate)>=8 and len(other)>=8 and SequenceMatcher(None,candidate,other).ratio()>=.82:
            return True
    # Compare the actual request separately from praise/encouragement before it.
    question = _question(body)
    previous = history[-1] if history else ''
    old_question = _question(previous)
    if question and old_question and not _new_support(body, previous):
        numbers = lambda text: re.findall(r'\d+(?:\.\d+)?', text)
        if numbers(question) == numbers(old_question):
            a, b = normalize(question), normalize(old_question)
            if a == b or (min(len(a), len(b)) >= 6 and SequenceMatcher(None, a, b).ratio() >= .78):
                return True
            kind = _question_intent(question)
            if kind and kind == _question_intent(old_question):
                # Concepts with distinct names still represent distinct learning goals.
                if kind != 'concept' or any(term in question and term in old_question for term in
                        ('平均分', '面积', '周长', '打折', '八折', '半径', '直径', '平均数')):
                    return True
    # Consecutive paraphrases of the same request are still a loop.
    def bare_question(text):
        return len(normalize(text))<=28 and not re.search(r'[。；;\n]|例如|小例子|想象|一轮',text)
    return bool(history and bare_question(body) and bare_question(history[-1])
                and intent(body) and intent(body)==intent(history[-1]))


def alternatives(stage,question,card,student):
    if stage=='understand':
        goal=re.split(r'[，,。！!]',question.rstrip('？?。'))[-1]
        return [f'先看“{goal}”这一问，你要找的是哪个量？',
                '从题目中挑出一个已知条件，用自己的话说给我听，好吗？',
                '题目里的哪一个词还不清楚？选一个，我们先解释它。']
    if stage=='method':
        return ['把要求的量放在等号左边，你觉得右边应该用哪两个已知量？',
                '我们先分清关系：题目要把几个部分合起来，还是把一个整体分开？',
                '先说说你准备使用哪个已知条件，以及它为什么有用，好吗？']
    if '单位' in student:
        return ['数值保留，单位表示这道题在数什么。题目求的是钱、长度，还是面积？',
                '看题目所求的量，选一个对应的单位写在结果后面。',
                '从题目条件里找找表示同一种量的单位，把它补到结果后面。']
    return ['先保留你写的算式，只检查最后一个等号两边是否相等，好吗？',
            '指出你最不确定的一个计算步骤，我们只检查这一步，好吗？',
            '先说你卡在列式、计算，还是单位，选一项就好。']
