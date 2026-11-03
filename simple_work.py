"""Exact evidence for a few complete single-step questions; never evaluate user code."""
import ast
from dataclasses import dataclass
from fractions import Fraction
from math import lcm
import re

import calculation


def _text(value):
    return calculation.normalize(value).replace('除以', '/').replace('÷', '/').replace('＝', '=')


def _value(expression):
    if len(expression)>160 or not re.fullmatch(r'[\d.()+*/-]+', expression):
        raise ValueError('unsupported expression')
    def read(node):
        if isinstance(node,ast.Constant) and type(node.value) in (int,float):
            return Fraction(ast.get_source_segment(expression,node))
        if isinstance(node,ast.BinOp):
            a,b=read(node.left),read(node.right)
            if isinstance(node.op,ast.Add): return a+b
            if isinstance(node.op,ast.Sub): return a-b
            if isinstance(node.op,ast.Mult): return a*b
            if isinstance(node.op,ast.Div): return a/b
        raise ValueError('unsupported operation')
    return read(ast.parse(expression,mode='eval').body)


def _structure(expression):
    if len(expression)>160 or not re.fullmatch(r'[\d.()+*/-]+', expression):
        raise ValueError('unsupported expression')
    return ast.dump(ast.parse(expression,mode='eval'), include_attributes=False)


@dataclass(frozen=True)
class Problem:
    expressions: tuple
    answer: Fraction
    unit: str
    method: str
    method_pattern: str
    simplest: bool=False
    explanation_text: str=''

    def valid_expression(self, text):
        try:
            return any(_structure(_text(text))==_structure(e) for e in self.expressions)
        except (ValueError,SyntaxError,RecursionError):
            return False

    def valid_method(self, text):
        normalized=_text(text)
        return (not re.search(r'不|没|猜|忽略|\[|\?',normalized)
                and bool(re.search(self.method_pattern,normalized)))

    def guide(self, student, previous_expression='', result_correct=False):
        text=_text(student).rstrip('。!！')
        if result_correct and text==self.unit and self.unit:
            return '算式、结果和单位已经核对。',True,previous_expression,True
        unit=''
        if self.unit and text.endswith(self.unit):
            unit=self.unit; text=text[:-len(unit)]
        # Distinguish a wrong/missing unit from numeric work, never strip arbitrary words.
        if not text or re.search(r'[^\d.()+*/=\-]',text):
            return '保留已经写出的部分，请只写当前的算式或结果。',False,previous_expression,result_correct
        parts=text.split('=')
        if len(parts)==1 and self.valid_expression(text):
            return '数量关系已经放进算式，计算结果是多少？',False,text,False
        expression=parts[0] if len(parts)>1 else previous_expression
        if not self.valid_expression(expression):
            return '先核对算式是否对应题目中的数量关系。',False,previous_expression,False
        values=parts if len(parts)>1 else [text]
        try:
            correct=all(_value(part)==self.answer for part in values)
        except (ValueError,SyntaxError,ZeroDivisionError,RecursionError,OverflowError):
            correct=False
        # A complete answer ends in one explicit value, not another unfinished expression.
        final=parts[-1]
        if not re.fullmatch(r'\d+(?:\.\d+)?(?:/\d+)?',final):
            correct=False
        if correct and self.simplest and '/' in final:
            numerator,denominator=final.split('/')
            fraction=Fraction(final)
            correct=(int(numerator)==fraction.numerator and int(denominator)==fraction.denominator)
        if not correct:
            return '列式的关系保留，检查等号两边是否相等，再写出最后结果。',False,expression,False
        if self.unit and unit!=self.unit:
            return '数值已经核对，只需要补上本题的单位。',False,expression,True
        return '算式、结果和单位已经核对。',True,expression,True

    def explanation(self):
        if self.explanation_text:
            return self.explanation_text
        return f'数量关系：{self.method}。\n代入：{self.expressions[0].replace("*","×").replace("/","÷")}={calculation.display(self.answer)}{self.unit}。'


def match(question,card):
    """Require an exact question shape and matching card; reject extra tasks/conditions."""
    if not card: return None
    text=re.sub(r'\s+','',question)
    n=calculation.NUMBER
    kid=card.get('id')
    if kid==14:
        m=re.fullmatch(rf'(?:一个)?正方形(?:地砖|卡纸|纸片)?边长(?:是|为)?({n})(厘米|米)[，,]?(?:求)?(?:它的)?面积(?:是多少|有多大)?[？?。]?',text)
        if m:
            a,u=m.groups()
            return Problem((f'{a}*{a}',),Fraction(a)**2,'平方'+u,'面积=边长×边长',r'边长\*边长|边长的平方')
    if kid==8:
        m=re.fullmatch(r'计算[：:]?(\d+)/(\d+)([+＋−-])(\d+)/(\d+)[，,]?(?:结果写成最简分数|结果是多少)?[。？?]?',text)
        if m and int(m[2])>0 and int(m[5])>0:
            a,b,op,c,d=m.groups(); op='+' if op in '+＋' else '-'
            value=Fraction(int(a),int(b))+Fraction(int(c),int(d)) if op=='+' else Fraction(int(a),int(b))-Fraction(int(c),int(d))
            if value<0: return None
            operation = r'(?:相?\+|分子.*\+|计算)' if op=='+' else r'(?:相?减|相?[−-]|分子.*减|计算)'
            denominator=lcm(int(b),int(d))
            left=int(a)*(denominator//int(b)); right=int(c)*(denominator//int(d))
            combined=left+right if op=='+' else left-right
            explanation=(f'先通分：分母{b}和{d}的最小公倍数是{denominator}。\n'
                         f'{a}/{b}={left}/{denominator}，{c}/{d}={right}/{denominator}。\n'
                         f'再计算：{left}/{denominator}{op}{right}/{denominator}={combined}/{denominator}。\n'
                         f'约分后，最简结果是{calculation.display(value)}。')
            return Problem((f'{a}/{b}{op}{c}/{d}',),value,'','先通分，再将分子相加减',r'通分.*'+operation,True,explanation)
    if kid==16:
        m=re.fullmatch(rf'三角形底({n})(厘米|米)[，,]对应高({n})\2[，,]面积是多少[？?。]?',text)
        if m:
            base,unit,height=m.groups(); answer=Fraction(base)*Fraction(height)/2
            explanation=('两个完全相同的三角形可以拼成一个平行四边形，拼成的图形与原三角形同底等高。'
                         '平行四边形面积=底×高，一个三角形占它的一半，所以三角形面积=底×高÷2。\n'
                         f'本题：{base}×{height}÷2={calculation.display(answer)}平方{unit}。')
            return Problem((f'{base}*{height}/2',f'{height}*{base}/2'),answer,'平方'+unit,
                           '三角形面积=底×高÷2',r'底\*高/2',explanation_text=explanation)
    if kid==39:
        m=re.fullmatch(rf'(?:学校到图书馆有)?({n})千米[，,]?(?:换算成米是多少|是多少米|等于多少米)[？?。]?',text)
        if m:
            a=m[1]
            return Problem((f'{a}*1000',f'1000*{a}'),Fraction(a)*1000,'米','米数=千米数×1000',r'(?:千米|大单位).*\*1000')
    if kid==25:
        m=re.fullmatch(rf'骑车每小时行({n})千米[，,]?骑行({n})小时[，,]?(?:一共|共)行了多少千米[？?。]?',text)
        if m:
            a,b=m.groups()
            return Problem((f'{a}*{b}',f'{b}*{a}'),Fraction(a)*Fraction(b),'千米','路程=速度×时间',r'路程.*(?:速度\*时间|时间\*速度)')
    if kid==28:
        m=re.fullmatch(rf'一列长({n})米的火车以每秒({n})米的速度通过一座长({n})米的桥[，,]从车头上桥到车尾离桥一共需要多少秒[？?。]?',text)
        if m and Fraction(m[2])>0:
            train,speed,bridge=m.groups()
            return Problem((f'({bridge}+{train})/{speed}', f'({train}+{bridge})/{speed}'),
                           (Fraction(train)+Fraction(bridge))/Fraction(speed),'秒',
                           '过桥时间=(桥长+车长)÷速度',r'(?:桥长\+车长|车长\+桥长).*速度')
    if kid==47:
        m=re.fullmatch(rf'三次(?:数学练习)?得分(?:为|是)({n})分[、，,]({n})分[、，,]({n})分[，,](?:平均分|平均数)是多少[？?。]?',text)
        if m:
            a,b,c=m.groups()
            return Problem((f'({a}+{b}+{c})/3',),sum(map(Fraction,(a,b,c)))/3,'分','平均分=总分÷次数',r'(?:平均数|平均分).*总分/(?:次数|3)|总分/(?:次数|3)')
    return None
