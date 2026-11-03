"""合并当前读题阶段的学生回答；只核验已有计算器支持的简单题。"""
import re
from dataclasses import dataclass, field
from fractions import Fraction

import calculation


@dataclass
class ReadingProgress:
    facts: dict = field(default_factory=dict)
    required: tuple = ()
    correction: str = ''

    @property
    def complete(self):
        return all(key in self.facts for key in ('target', *self.required))

    @property
    def missing(self):
        return [key for key in self.required if key not in self.facts]


def _rate(number):
    digits = dict(zip('一二三四五六七八九十', range(1, 11)))
    if number in digits:
        return Fraction(digits[number], 10)
    if all(char in digits and digits[char] < 10 for char in number):
        return Fraction(int(''.join(str(digits[char]) for char in number)), 100)
    try:
        return Fraction(number) / 10
    except ValueError:
        return None


def collect(question, verified, messages, eligible):
    """从已持久化的阶段历史重建进度，无独立缓存，重启和失败重试不会丢失或多记。"""
    if isinstance(verified, calculation.Discount):
        required = ('原价', '折扣')
    elif isinstance(verified, calculation.Rectangle):
        required = ('长', '宽')
    else:
        return None
    progress = ReadingProgress(required=required)
    previous_teacher = ''
    for message in messages:
        if message['role'] == 'assistant':
            previous_teacher = message['content']
            continue
        if message['role'] != 'user':
            continue
        student = message['content']
        text = calculation.normalize(student)
        progress.correction = ''
        # 重贴题目、提问、请求解释都不是学生已理解的证据。
        if (not eligible(student) or text == calculation.normalize(question)
                or re.search(r'[?？]|吗[。！!]*$|解释|什么|怎么|如何|不是|不对|不求|不要|不应该|错了', text)):
            continue
        found, wrong = {}, {}
        asked_target = bool(re.search(r'求什么|求的是|要求什么|要算什么', previous_teacher))
        if isinstance(verified, calculation.Discount):
            if re.search(r'(?:打折|折扣|折)后(?:的)?(?:价格|价钱|多少钱)|现价|现在(?:要付|付|的价格|多少钱)', text):
                found['target'] = student
            if re.search(r'(?:求|算|要找)(?:的是|的|出)?(?:原价|省|便宜|优惠|节省)|(?:省|便宜|优惠|节省)(?:了)?多少钱', text):
                wrong['target'] = '先看题目最后一句，它问的是打折后付多少钱。你能用自己的话说说要求什么吗？'
            if asked_target and re.fullmatch(r'(?:商品的)?原价[。！!]*', text):
                wrong['target'] = '原价是题目已经告诉我们的，最后一句要求的是什么价格？'
            if '原价' in text and 'target' not in wrong:
                found['原价'] = student
            if re.search(r'折扣|打折数|折数', text):
                found['折扣'] = student
            for match in re.finditer(rf'({calculation.NUMBER})元', text):
                if Fraction(match[1]) == verified.price:
                    found['原价'] = student
                else:
                    wrong['原价'] = '请再看题目中的原价，是多少元？'
            # 有数字的条件必须核对数值，不能只靠出现“原价”二字就认可。
            for match in re.finditer(rf'原价(?:格)?(?:是|为|[:=])?({calculation.NUMBER})', text):
                if Fraction(match[1]) != verified.price:
                    wrong['原价'] = '请再看题目中的原价，是多少元？'
            if re.search(r'原价(?:格)?(?:是|为|[:=])?[零一二三四五六七八九十百千万两]', text):
                found.pop('原价', None)  # 中文金额留给模型核对，不凭名称通过。
            for match in re.finditer(rf'([一二三四五六七八九十]{{1,2}}|{calculation.NUMBER})折', text):
                if _rate(match[1]) == verified.rate:
                    found['折扣'] = student
                else:
                    wrong['折扣'] = '请再看题目，商品打的是几折？'
            for match in re.finditer(rf'({calculation.NUMBER})%', text):
                if Fraction(match[1]) / 100 == verified.rate:
                    found['折扣'] = student
                else:
                    wrong['折扣'] = '这个百分数和题目的折扣一致吗？'
        else:
            target, other = ('面积', '周长') if verified.area else ('周长', '面积')
            if target in text:
                found['target'] = student
            if other in text and (target not in text or re.search(rf'(?:求|算)(?:的是|的)?{other}', text)):
                wrong['target'] = '先看题目最后一句，它要我们求什么？'
            if re.search(r'长(?:和|与|、|，|,)宽|宽(?:和|与|、|，|,)长', text):
                found.update({'长': student, '宽': student})
            for key, value in (('长', verified.length), ('宽', verified.width)):
                for match in re.finditer(rf'(?<!周)(?<!方){key}(?:是|为|[:=])?({calculation.NUMBER})({calculation.UNITS})?', text):
                    if Fraction(match[1]) == value and (not match[2] or match[2] == verified.unit):
                        found[key] = student
                    else:
                        wrong[key] = f'请再核对题目中的{key}和单位，题目是怎么说的？'
        progress.facts.update(found)
        for key, correction in wrong.items():
            progress.facts.pop(key, None)
            progress.correction = correction
    return progress
