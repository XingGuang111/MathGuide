"""Small, deterministic expressions; learning outcomes remain server verified."""
import re

FEELINGS = {
    'smile': ('微笑陪伴', 'idle', '我会陪你慢慢想，每一小步都算进步。'),
    'thinking': ('认真思考', 'think', '先读清题目，我和你一起找线索。'),
    'concerned': ('有点担心', 'idle', '这题有点绕，我们先找出一个已知条件，好吗？'),
    'crying': ('泪汪汪', 'idle', '呜，这题把我也绕晕啦。我们一起拆成一小步，慢慢来。'),
    'laugh': ('开心大笑', 'idle', '哈哈，你认真思考的样子太棒啦！'),
    'coax': ('撒娇催学', 'idle', '再陪我做一道题嘛，做完我们再一起玩呀。'),
}


def feeling(name='smile', reason=None):
    # Existing profiles may still contain the retired pout expression.
    if name == 'pout':
        name, reason = 'coax', None
    name = name if name in FEELINGS else 'smile'
    label, animation, message = FEELINGS[name]
    return {'name': name, 'label': label, 'animation': animation, 'message': reason or message}


def from_text(text):
    """Only react to expressed feelings; a chat claim never awards progress."""
    if re.search(r'太难|好难|难哭|想哭|哭了|崩溃|做不出来|总是错|一直错', text):
        return 'crying'
    if re.search(r'不会|不懂|没懂|不明白|没信心|不想学|累了|担心|害怕', text):
        return 'concerned'
    if re.search(r'开心|高兴|哈哈|笑一|太棒|好耶', text):
        return 'laugh'
    return 'smile'


def tutor_reaction(tutor, previous_state=None, previous_help=0):
    if tutor.last_error:
        return feeling('thinking', '老师还在整理思路，我先安静陪着你。')
    helps = sum(tutor.help_counts.values())
    if helps > previous_help:
        return feeling('crying' if helps >= 2 else 'concerned')
    if tutor.finished:
        return feeling('smile' if tutor.needs_practice else 'laugh')
    if previous_state is not None and tutor.state != previous_state:
        return feeling('smile', '你已经想明白一小步啦！我们继续下一步。')
    return feeling('thinking')
