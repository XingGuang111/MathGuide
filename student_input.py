"""Separate problem statements from attempts without accepting arbitrary prose as proof."""
import re


def split_question(text):
    text = re.sub(r'^\s*题目\s*[:：]\s*', '', text.strip())
    parts = re.split(r'(?<=[？?])\s*|\n+', text, maxsplit=1)
    if len(parts) == 2 and re.match(
            r'(?:我(?:想|改|用|算|觉得|认为|不会|不知道|不懂|不明白|没|检查)|'
            r'不知道|不会|不懂|不明白|没明白|没读懂|看不懂|请解释)', parts[1]):
        return parts[0], parts[1]
    return text, ''


def work_text(text):
    """Only unwrap a single arithmetic attempt with a small, explicit prose grammar."""
    text = text.strip().rstrip('。.!！?？')
    text = re.sub(r'[，,]?\s*(?:这样对吗|这样算对吗|对吗)$', '', text)
    text = re.sub(r'^(?:我)?(?:检查后改成|检查后|改成|想用|改用|用|列式|算式是|算式为)', '', text)
    text = re.sub(r'^长乘宽[，,]\s*列式', '', text)
    text = re.sub(r'[，,]\s*但我算成了', '=', text)
    return text
