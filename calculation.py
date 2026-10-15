"""保守的长方形单步计算核验，不执行学生输入，不覆盖任意自然语言题。"""
import re
import unicodedata
from dataclasses import dataclass
from fractions import Fraction

NUMBER = r"\d+(?:\.\d+)?"
UNITS = r"千米|厘米|毫米|米"


def normalize(text):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', text)).replace('乘以', '*').replace('乘', '*').replace('×', '*').replace('加', '+').replace('等于', '=')


def display(number):
    return str(number.numerator) if number.denominator == 1 else str(number)


@dataclass(frozen=True)
class Rectangle:
    length: Fraction
    width: Fraction
    unit: str
    area: bool

    @property
    def answer(self):
        return self.length * self.width if self.area else (self.length + self.width) * 2

    @property
    def answer_unit(self):
        return ('平方' if self.area else '') + self.unit

    def respond(self, student):
        text = normalize(student).rstrip('。.!！')
        # 只接受明确的数值或一个受控算式，不能把命令、多个答案或复杂句子当作证明。
        text = re.sub(r'^(?:面积=长\*宽|周长=\(长\+宽\)\*2)[，,；;]?', '', text)
        text = re.sub(r'^(?:面积|周长|答案)(?:是|为|=)', '', text)
        match = re.fullmatch(rf'(?:(.+)=)?({NUMBER})(平方(?:{UNITS})|{UNITS})?', text)
        if not match:
            return '请写出你的计算算式和结果，再标上单位。', False
        expression, answer, unit = match.groups()
        if Fraction(answer) != self.answer:
            return ('面积要用长乘宽，请再检查这一步计算。' if self.area else
                    '周长是四条边的总长度，请检查长与宽相加后是否乘了2。'), False
        if unit != self.answer_unit:
            return ('面积的单位应是平方单位，请补上正确单位。' if self.area else
                    '周长使用长度单位，请补上正确单位。'), False
        if not expression or not self.valid_expression(expression):
            return ('请用题目的长和宽写出求面积的算式。' if self.area else
                    '请用题目的长和宽写出求周长的算式。'), False
        return '你的算式、计算结果和单位都正确，这道题完成了！', True

    def valid_expression(self, expression):
        if self.area:
            match = re.fullmatch(rf'({NUMBER})\*({NUMBER})', expression)
        else:
            match = re.fullmatch(rf'\(({NUMBER})\+({NUMBER})\)\*2', expression)
        return bool(match and sorted(Fraction(n) for n in match.groups()) == sorted([self.length, self.width]))

    def explanation(self):
        a, b, result = map(display, [self.length, self.width, self.answer])
        relation = '面积=长×宽' if self.area else '周长=(长+宽)×2'
        operation = f'{a}×{b}' if self.area else f'({a}+{b})×2'
        return f'已知长{a}{self.unit}、宽{b}{self.unit}。\n{relation}。\n{operation}={result}{self.answer_unit}。\n检查：' + ('面积使用平方单位。' if self.area else '周长使用长度单位。')


def rectangle(question, card):
    if not card or card.get('id') not in (11, 12):
        return None
    text = normalize(question)
    if '长方形' not in text or ('面积' in text) == ('周长' in text):
        return None
    area = '面积' in text
    if card['id'] != (12 if area else 11):
        return None
    shape = r'(?:一个)?长方形(?:花园|操场|纸片|地块|菜地)?'
    dimension = rf'长(?:为|是|:)?{NUMBER}(?:{UNITS})[，,、]?宽(?:为|是|:)?{NUMBER}(?:{UNITS})'
    target = r'[，,。]?(?:求|问|计算)?(?:它的|这个长方形的|长方形的|花园的)?(?:面积|周长)(?:是多少|有多大|有多长|是多大|是多长|为多少)?[？?。]?'
    if not re.fullmatch(shape + dimension + target, text):
        return None
    # 排除额外数字、条件变化、多步任务，宁可不支持也不误算。
    if len(re.findall(NUMBER, text)) != 2 or any(t in text for t in ('增加', '减少', '扩大', '缩小', '剪', '剩', '比', '倍', '不', '至少', '最多')):
        return None
    length = re.search(rf'长(?:为|是|:|：)?({NUMBER})({UNITS})', text)
    width = re.search(rf'宽(?:为|是|:|：)?({NUMBER})({UNITS})', text)
    if not length or not width or length[2] != width[2]:
        return None
    a, b = Fraction(length[1]), Fraction(width[1])
    return Rectangle(a, b, length[2], area) if a > 0 and b > 0 else None
