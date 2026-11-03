"""从用户维护的三个文档加载辅导规则、回复模板和相关阶段示例。"""
import json
import logging
import re
from functools import lru_cache
from pathlib import Path

import config


log = logging.getLogger(__name__)
STAGES = ('understand', 'method', 'compute')
_DEFAULT_RULES = '你是耐心的小学数学老师。每轮只处理一个疑问、只问一个问题；不提前给本题答案，不把列式当作已经算完。'
_TOPICS = {
    'equal_share': ('平均分', '均分', '平分'),
    'discount': ('折', '折扣', '原价', '现价'),
    'area': ('面积',),
    'perimeter': ('周长',),
    'radius': ('半径',),
    'diameter': ('直径',),
    'average': ('平均',),
    'speed': ('速度',),
    'distance': ('路程',),
    'conversion': ('换算', '合多少', '等于多少厘米', '等于多少米'),
}
_INTENTS = {
    'example': ('还是', '仍然', '再举', '举例', '例子', '没明白', '没懂'),
    'explain': ('不懂', '不知道', '不会', '没有', '意思', '不明白'),
    'correct': ('为什么', '因为', '所以'),
}


def topic_for(question, student_msg=''):
    # “平均分是多少分”里的“分”是分数单位，不能套用分糖果的示例。
    if ('平均数' in question or (re.search(r'得分|成绩|分数|\d+分', question)
                                  and re.search(r'平均分|平均成绩', question))):
        return 'average'
    available = [topic for topic, words in _TOPICS.items() if any(word in question for word in words)]
    # “平均分”讨论每份一样多，不能直接套用“平均数”的定义或示例。
    if 'equal_share' in available and '平均数' not in question:
        available = [topic for topic in available if topic != 'average']
    for topic in available:
        if any(word in student_msg for word in _TOPICS[topic]):
            return topic
    return available[0] if available else 'general'


def _signature(path):
    path = Path(path)
    try:
        stat = path.stat()
        return str(path), stat.st_mtime_ns, stat.st_size
    except OSError:
        return str(path), 0, 0


def _read(path):
    try:
        return Path(path).read_text(encoding='utf-8-sig')
    except (OSError, UnicodeError) as exc:
        log.warning('无法读取辅导资料 %s：%s', path, exc)
        return ''


def _validate_example(item):
    if not isinstance(item, dict) or item.get('stage') not in (*STAGES, 'all'):
        raise ValueError('stage 必须为 understand、method、compute 或 all')
    if not isinstance(item.get('id'), str) or not item['id']:
        raise ValueError('缺少 id')
    if not isinstance(item.get('topics'), list) or not all(isinstance(t, str) for t in item['topics']):
        raise ValueError('topics 必须为字符串列表')
    messages = item.get('messages')
    if (not isinstance(messages, list) or len(messages) != 2
            or [m.get('role') for m in messages if isinstance(m, dict)] != ['user', 'assistant']
            or not all(isinstance(m.get('content'), str) and m['content'].strip() for m in messages)):
        raise ValueError('messages 必须包含一问一答：user、assistant')
    for key in ('template', 'term', 'intent', 'action'):
        if key in item and not isinstance(item[key], str):
            raise ValueError(f'{key} 必须为字符串')
    return item


@lru_cache(maxsize=1)
def _load(signatures):
    system_path, examples_path, dialogue_path = [value[0] for value in signatures]
    system = _read(system_path)
    sections = {}
    matches = list(re.finditer(r'^\[(global|understand|method|compute)\]\s*$', system, re.M))
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(system)
        sections[match[1]] = system[match.end():end].strip()
    if not matches and system.strip():
        sections['global'] = system.strip()
    sections.setdefault('global', _DEFAULT_RULES)
    examples = []
    for number, line in enumerate(_read(examples_path).splitlines(), 1):
        if not line.strip():
            continue
        try:
            examples.append(_validate_example(json.loads(line)))
        except (ValueError, TypeError) as exc:
            log.warning('%s:%s 辅导示例无效，已跳过：%s', examples_path, number, exc)
    # Markdown 中只有带机器标记的阶段片段进入模型，说明文字和完整答案不跨阶段灌入。
    dialogue = _read(dialogue_path)
    for match in re.finditer(r'<!-- tutor-example:\s*(\{[^\n]*\})\s*-->\s*```text\s*\n(.*?)\n```', dialogue, re.S):
        try:
            item = json.loads(match[1])
            lines = match[2].splitlines()
            user = next(line.split('：', 1)[1] for line in lines if line.startswith('学生：'))
            teacher = next(line.split('：', 1)[1] for line in lines if line.startswith('老师：'))
            item['messages'] = [{'role': 'user', 'content': user}, {'role': 'assistant', 'content': teacher}]
            examples.append(_validate_example(item))
        except (ValueError, TypeError, StopIteration) as exc:
            log.warning('%s 中的阶段示例无效，已跳过：%s', dialogue_path, exc)
    return sections, examples


def load_profile():
    return _load(tuple(_signature(path) for path in (
        config.TUTOR_SYSTEM_PATH, config.TUTOR_EXAMPLES_PATH, config.TUTOR_DIALOGUE_PATH,
    )))


def render_response(action, stage, question='', student_msg='', fallback='', **values):
    """仅填充已知字段，不执行模板代码；损坏模板回退到代码的安全问句。"""
    _, examples = load_profile()
    topic = topic_for(question, student_msg)
    candidates = [item for item in examples if item.get('action') == action
                  and item['stage'] in (stage, 'all')
                  and (topic in item['topics'] or 'general' in item['topics'])]
    candidates.sort(key=lambda item: topic not in item['topics'])
    for item in candidates:
        try:
            template = item.get('template', item['messages'][1]['content'])
            return template.format_map(values)
        except (KeyError, ValueError, IndexError) as exc:
            log.warning('辅导回复模板 %s 无效：%s', item['id'], exc)
    return fallback


def term_examples(question, student_msg=''):
    _, examples = load_profile()
    topic = topic_for(question, student_msg)
    matches = [item for item in examples if item.get('term') and item['term'] in question
               and (topic in item['topics'] or 'general' in item['topics'])]
    mentioned = [item for item in matches if item['term'] in student_msg]
    if mentioned:
        matches = mentioned
    source = student_msg if mentioned else question
    return sorted(matches, key=lambda item: source.index(item['term']))


def build_context(stage, question, student_msg=''):
    sections, examples = load_profile()
    topic = topic_for(question, student_msg)
    intent = next((name for name, words in _INTENTS.items() if any(word in student_msg for word in words)), '')
    candidates = [item for item in examples if item['stage'] == stage
                  and topic in item['topics'] and item.get('action') not in ('opening', 'finish', 'practice')]
    candidates.sort(key=lambda item: (item.get('intent') != intent,
                                      not item['id'].startswith('dialogue-')))
    selected = []
    # 每轮最多两个短片段，长示例不会挤掉当前阶段规则。
    for item in candidates:
        pair = '\n'.join(('学生：' if m['role'] == 'user' else '老师：') + m['content'] for m in item['messages'])
        if len(pair) <= 320 and pair not in selected:
            selected.append(pair)
        if len(selected) == 2:
            break
    context = sections['global'] + '\n' + sections.get(stage, '')
    if selected:
        context += ('\n【本阶段同类表达示例】只学习口吻和引导方式；示例不是本题条件，不能照抄数字、答案或学生身份。\n'
                    + '\n\n'.join(selected))
    return context
