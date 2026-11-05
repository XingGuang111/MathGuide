"""保守的单步计算核验，不执行学生输入，不覆盖任意自然语言题。"""
import re
import unicodedata
import student_input
from dataclasses import dataclass
from fractions import Fraction

NUMBER = r"\d+(?:\.\d+)?"
UNITS = r"千米|厘米|毫米|米"


def normalize(text):
    text = re.sub(r'\s+', '', unicodedata.normalize('NFKC', text)).replace('乘以', '*').replace('乘', '*').replace('×', '*').replace('加', '+').replace('等于', '=')
    return re.sub(r'(?<=\d)[xX](?=\d)', '*', text)


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

    def valid_method(self, student):
        """只核验已支持题型的数量关系，不把「懂了」当作找到了方法。"""
        text = normalize(student)
        if any(word in text for word in ('不能', '不是', '不用', '不对', '不知道')):
            return False
        if self.area:
            if '周长' in text:
                return False
            pattern = r'长\*宽|宽\*长|长(?:和|与)宽相乘'
        else:
            if '面积' in text:
                return False
            pattern = r'\((?:长\+宽|宽\+长)\)\*2|(?:长\+宽|宽\+长|长和宽|宽和长)的和\*2'
        match = re.search(pattern, text)
        if not match:
            return False
        remaining = text[:match.start()] + text[match.end():]
        return not re.search(r'[+*/÷−-]|\d', remaining)

    def respond(self, student):
        response, complete, _, _ = self.guide(student)
        return response, complete

    def guide(self, student, previous_expression='', result_correct=False):
        """按算式、结果、单位逐步核验，也允许一次提交完整的正确解答。"""
        text = normalize(student_input.work_text(student)).rstrip('。.!！')
        # 只接受明确的数值或一个受控算式，不能把命令、多个答案或复杂句子当作证明。
        text = re.sub(r'^(?:面积=长\*宽|周长=\(长\+宽\)\*2)[，,；;]?', '', text)
        text = re.sub(r'^(?:面积|周长|答案)(?:是|为|=)', '', text)
        if self.valid_expression(text):
            return '算式正确，这一步计算的结果是多少？', False, text, False
        if previous_expression and result_correct and re.fullmatch(rf'平方(?:{UNITS})|{UNITS}', text):
            if text == self.answer_unit:
                return '你的算式、计算结果和单位都正确，这道题完成了！', True, previous_expression, True
            return '请再检查一下，这里应该使用什么单位？', False, previous_expression, True
        match = re.fullmatch(rf'(?:(.+)=)?({NUMBER})(平方(?:{UNITS})|{UNITS})?', text)
        if not match:
            if result_correct:
                prompt = '这个结果应该用什么单位？'
            elif previous_expression:
                prompt = '先算刚才的这一步，结果是多少？'
            else:
                prompt = '请先用题目的长和宽写出算式。'
            return prompt, False, previous_expression, result_correct
        expression, answer, unit = match.groups()
        expression = expression or previous_expression
        if not expression or not self.valid_expression(expression):
            prompt = ('请用题目的长和宽写出求面积的算式。' if self.area else
                      '请用题目的长和宽写出求周长的算式。')
            if self.area and expression and '+' in expression:
                prompt = ('你用了加法，但面积不能把长和宽相加，要看能铺满多少个1平方' + self.unit + '的小方格。'
                          f'每排{display(self.length)}个，有{display(self.width)}排，可以怎样算一共有多少个？')
            return prompt, False, previous_expression, False
        if Fraction(answer) != self.answer:
            prompt = ('请再检查这一步的乘法计算，结果是多少？' if self.area else
                      '先算括号里的加法，再乘2，请重新检查结果。')
            if self.area and self.width.denominator == 1 and 1 < self.width <= 5:
                repeated = '+'.join([display(self.length)] * int(self.width))
                prompt = f'列式{expression.replace("*", "×")}是对的，只需检查计算。{repeated}等于多少？'
            return prompt, False, expression, False
        if unit != self.answer_unit:
            prompt = ('面积的单位应是平方单位，请补上正确单位。' if self.area else
                      '周长使用长度单位，请补上正确单位。')
            return prompt, False, expression, True
        return '你的算式、计算结果和单位都正确，这道题完成了！', True, expression, True

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
    shape = r'(?:一个|一张|一块)?长方形(?:花园|操场|纸片|卡纸|地块|菜地)?'
    dimension = rf'长(?:为|是|:)?{NUMBER}(?:{UNITS})[，,、]?宽(?:为|是|:)?{NUMBER}(?:{UNITS})'
    target = rf'[，,。]?(?:求|问|计算)?(?:它的|这个长方形的|长方形的|花园的)?(?:面积|周长)(?:是多少|有多大|有多长|是多大|是多长|为多少)?(?P<requested_unit>平方(?:{UNITS})|{UNITS})?[？?。]?'
    parsed = re.fullmatch(shape + dimension + target, text)
    if not parsed:
        return None
    # 排除额外数字、条件变化、多步任务，宁可不支持也不误算。
    if len(re.findall(NUMBER, text)) != 2 or any(t in text for t in ('增加', '减少', '扩大', '缩小', '剪', '剩', '比', '倍', '不', '至少', '最多')):
        return None
    length = re.search(rf'长(?:为|是|:|：)?({NUMBER})({UNITS})', text)
    width = re.search(rf'宽(?:为|是|:|：)?({NUMBER})({UNITS})', text)
    if not length or not width or length[2] != width[2]:
        return None
    if parsed['requested_unit'] and parsed['requested_unit'] != ('平方' if area else '') + length[2]:
        return None
    a, b = Fraction(length[1]), Fraction(width[1])
    return Rectangle(a, b, length[2], area) if a > 0 and b > 0 else None


@dataclass(frozen=True)
class Discount:
    """仅支持原价已知、一次打折、求现价的单步题。"""
    price: Fraction
    rate: Fraction

    @property
    def answer(self):
        return self.price * self.rate

    def valid_expression(self, expression):
        match = re.fullmatch(rf'({NUMBER})(%?)\*({NUMBER})(%?)', expression)
        if not match:
            return False
        a, a_percent, b, b_percent = match.groups()
        operands = [Fraction(a) / (100 if a_percent else 1), Fraction(b) / (100 if b_percent else 1)]
        return sorted(operands) == sorted([self.price, self.rate])

    def valid_method(self, student):
        text = normalize(student).replace('原价格', '原价').replace('现在的价格', '现价')
        if any(word in text for word in ('不', '没', '减', '便宜', '省下', '节省')):
            return False
        match = re.search(rf'原价\*(?:折扣|折扣率|({NUMBER})(%?))', text)
        if not match:
            return False
        if re.search(r'[+*/÷−-]|\d', text[:match.start()]):
            return False
        if match[1] is not None and Fraction(match[1]) / (100 if match[2] else 1) != self.rate:
            return False
        # 不能把“原价乘折扣再减去...”或多乘一个系数当作正确方法。
        tail = text[match.end():].split('因为', 1)[0].split('，', 1)[0].split(',', 1)[0]
        return not re.search(r'[+*/÷−-]|再|然后', tail)

    def guide(self, student, previous_expression='', result_correct=False):
        text = normalize(student).rstrip('。.!！')
        text = re.sub(r'^(?:现价|价格|答案)(?:是|为|=)', '', text)
        if self.valid_expression(text):
            return '你把原价和折扣放进算式了，接下来乘出来是多少？', False, text, False
        if previous_expression and result_correct and text in ('元', '单位是元', '单位为元'):
            return '你的算式、结果和单位都正确，这道题完成了。', True, previous_expression, True
        match = re.fullmatch(rf'(?:(.+)=)?({NUMBER})(元)?', text)
        if not match:
            prompt = ('价格应该带什么单位？' if result_correct else
                      '先算刚才的乘法，结果是多少？' if previous_expression else
                      '请先用题目的原价和折扣写出算式。')
            return prompt, False, previous_expression, result_correct
        expression, answer, unit = match.groups()
        expression = expression or previous_expression
        if not expression or not self.valid_expression(expression):
            return '请先用题目的原价和折扣写出算式。', False, '', False
        if Fraction(answer) != self.answer:
            return '原价和折扣的关系用对了，再检查这一步乘法的小数点位置，好吗？', False, expression, False
        if unit != '元':
            return '计算结果对了，价格应该带什么单位？', False, expression, True
        return '你的算式、结果和单位都正确，这道题完成了。', True, expression, True

    def explanation(self):
        def decimal(value):
            # 输入仅含有限小数，分母由2和5构成，可以精确转换而不经过浮点数。
            from decimal import Decimal, localcontext
            with localcontext() as context:
                context.prec = len(str(value.numerator)) + len(str(value.denominator)) + 2
                return format((Decimal(value.numerator) / Decimal(value.denominator)).normalize(), 'f')
        return f'现价=原价×折扣。\n{decimal(self.price)}×{decimal(self.rate)}={decimal(self.answer)}元。\n检查：价格的单位是元。'


def discount(question):
    text = normalize(question)
    match = re.fullmatch(
        rf'(?:一件|一个|一本)?(?:商品|衣服|玩具|书|文具|上衣|外套|裤子|商品的|衣服的)'
        rf'原价(?:是|为)?({NUMBER})元[，,]?(?:现在)?打([一二三四五六七八九十]{{1,2}}|{NUMBER})折'
        r'(?:后|出售|销售)?[，,]?(?:现价|现在价格|现在的价格|售价)?(?:是|为)?(?:多少钱|多少元|多少|是多少|是多少元|是多少钱)[？?。]?', text)
    if not match:
        return None
    price, number = match.groups()
    digits = dict(zip('一二三四五六七八九十', range(1, 11)))
    if number in digits:
        value = Fraction(digits[number])
    elif all(char in digits and digits[char] < 10 for char in number):
        value = Fraction(int(''.join(str(digits[char]) for char in number)), 10)
    else:
        try:
            value = Fraction(number)
        except ValueError:
            return None
    return Discount(Fraction(price), value / 10) if Fraction(price) > 0 and 0 < value <= 10 else None


@dataclass(frozen=True)
class EqualShare:
    """物品总数已知，整除分给若干人，只求每人的数量。"""
    total: int
    people: int
    answer_unit: str
    object_name: str

    @property
    def answer(self):
        return Fraction(self.total, self.people)

    def valid_expression(self, expression):
        text = normalize(expression).replace('除以', '/').replace('除', '/').replace('÷', '/')
        match = re.fullmatch(rf'({NUMBER})/({NUMBER})', text)
        return bool(match and Fraction(match[1]) == self.total and Fraction(match[2]) == self.people)

    def valid_method(self, student):
        text = normalize(student).replace('除以', '/').replace('除', '/')
        if re.search(r'不|没|猜|加|减|乘|\*', text):
            return False
        if self.valid_expression(text.removeprefix('用/法，').removeprefix('用/法,')):
            return True
        return bool(re.fullmatch(r'(?:用)?/法(?:因为)?(?:平均分)?', text)
                    or re.fullmatch(r'(?:用)?(?:总数|总量|总数量)[/÷](?:人数|份数|总份数)', text))

    def guide(self, student, previous_expression='', result_correct=False):
        text = normalize(student).rstrip('。.!！')
        text = re.sub(r'^(?:答案|每人|每个人)(?:是|为|有|=)', '', text)
        if self.valid_expression(text):
            return '总数和人数放对了，试着算出每个人分到多少？', False, text, False
        if previous_expression and result_correct and text in (self.answer_unit, '单位是'+self.answer_unit):
            return '你的算式、结果和单位都正确，这道题完成了。', True, previous_expression, True
        match = re.fullmatch(rf'(?:(.+)=)?({NUMBER})(颗|个|支|块|本)?', text)
        if not match:
            prompt = ('每个人分到的数量应该带什么单位？' if result_correct else
                      '继续算刚才的除法，结果是多少？' if previous_expression else
                      '把物品总数和小朋友人数放进算式，你会怎样写？')
            return prompt, False, previous_expression, result_correct
        expression, number, unit = match.groups()
        expression = expression or previous_expression
        if not expression or not self.valid_expression(expression):
            return '要找每个人的数量，总数和人数该怎样放进除法算式？', False, previous_expression, result_correct
        if Fraction(number) != self.answer:
            return '总数除以人数这个关系对了，再检查这一步除法，结果是多少？', False, expression, False
        if unit != self.answer_unit:
            return '计算结果对了，每个人分到的物品应该用什么单位？', False, expression, True
        return '你的算式、结果和单位都正确，这道题完成了。', True, expression, True

    def explanation(self):
        return (f'每人分到的数量=总数÷人数。\n{self.total}÷{self.people}={display(self.answer)}{self.answer_unit}。\n'
                f'检查：{display(self.answer)}×{self.people}={self.total}，每人一样多。')


def equal_share(question):
    """完整匹配有限情境，拒绝余数、多步题、额外条件与不明单位。"""
    text = normalize(question)
    match = re.fullmatch(
        r'(?:老师|小明|小红|妈妈|爸爸)?(?:有|买了|拿出)?(\d+)(颗糖|个苹果|支铅笔|块饼干|本书)[，,]?'
        r'(?:平均分|均分|平分)给(\d+)(?:个|名|位)?(?:小朋友|同学|学生|人)[，,]?'
        r'(?:每个人|每人|每个小朋友|每个同学)(?:分到|分得|有|能分到)?(?:几|多少)(颗|个|支|块|本)[？?。]?', text)
    if not match:
        return None
    total, item, people, unit = match.groups()
    total, people = int(total), int(people)
    if not total or not people or total % people or unit != item[0]:
        return None
    return EqualShare(total, people, unit, item[1:])
