"""Server-owned prices and local assets for pet lessons and permanent hats."""

TRICKS = {
    'stretch': {'name': '大大伸懒腰', 'price': 20, 'emoji': '🙆', 'description': '伸伸手、舒展一下，学习间隙放松身体。'},
    'giggle': {'name': '咯咯笑', 'price': 30, 'emoji': '😆', 'description': '被挠痒痒时，忍不住咯咯笑起来。'},
    'bubbles': {'name': '鲸鱼泡泡', 'price': 60, 'emoji': '🫧', 'description': '召唤鲸鱼吐出泡泡，送你一场小小惊喜。'},
    'scout': {'name': '好奇小侦探', 'price': 25, 'emoji': '🔎', 'description': '踱步张望，一起寻找藏起来的线索。'},
    'busy': {'name': '元气小助手', 'price': 25, 'emoji': '⌨️', 'description': '忙碌地点按，认真做好眼前的小事。'},
    'sort': {'name': '整理小能手', 'price': 30, 'emoji': '📚', 'description': '清点、归档，把小小世界整理好。'},
    'token': {'name': '字符小零食', 'price': 40, 'emoji': '🔤', 'description': '吃掉飘来的字符，表演特别的吃零食动作。'},
    'yawn': {'name': '困困哈欠', 'price': 20, 'emoji': '🥱', 'description': '打一个大哈欠，提醒我们记得休息。'},
    'sigh': {'name': '叹气再打气', 'price': 20, 'emoji': '💭', 'description': '偶尔叹口气也没关系，缓一缓再出发。'},
    'flute': {'name': '学习吹笛子', 'price': 60, 'emoji': '🪈', 'description': '吹起小笛子，用一段旋律庆祝学习进步。'},
    'violin': {'name': '学习拉小提琴', 'price': 70, 'emoji': '🎻', 'description': '架好小提琴，认真表演一段优雅的演奏。'},
    'sway_dance': {'name': '轻快摇摆舞', 'price': 40, 'emoji': '💃', 'description': '跟着节拍轻轻摇摆，课间放松一下。'},
    'cute_dance': {'name': '可爱宅舞', 'price': 50, 'emoji': '🎶', 'description': '学一支可爱舞蹈，为你的努力加油。'},
    'grace_dance': {'name': '优雅礼服舞', 'price': 50, 'emoji': '🩰', 'description': '转个圈、行个礼，带来一支优雅小舞蹈。'},
    'dove_magic': {'name': '变鸽子魔术', 'price': 60, 'emoji': '🕊️', 'description': '挥挥手，变出一只小鸽子。'},
    'card_magic': {'name': '扑克小魔术', 'price': 50, 'emoji': '🃏', 'description': '跟着手中的纸牌，见证小小的奇迹。'},
    'flower_magic': {'name': '凭空生花', 'price': 60, 'emoji': '🌸', 'description': '把小小心愿变成盛开的花朵。'},
    'juggle': {'name': '三球抛接', 'price': 50, 'emoji': '🤹', 'description': '练习眼手协调，让三个小球轮流飞起来。'},
    'shuttlecock': {'name': '学习踢毽子', 'price': 40, 'emoji': '🪶', 'description': '踢起小毽子，一起数数接住了几次。'},
    'gomoku': {'name': '学习五子棋', 'price': 50, 'emoji': '⚫', 'description': '摆好棋盘，表演认真思考落子的样子。'},
    'pet_cat': {'name': '温柔撸猫', 'price': 40, 'emoji': '🐈', 'description': '轻轻摸摸小猫，分享一段温柔的休息时间。'},
    'animals': {'name': '森林小伙伴', 'price': 60, 'emoji': '🐾', 'description': '邀请小动物围在身边，一起为你加油。'},
    'garden': {'name': '蝶舞花开', 'price': 60, 'emoji': '🦋', 'description': '蝴蝶、蜜蜂环绕，头顶开出小花。'},
    'whale': {'name': '召唤蓝鲸', 'price': 80, 'emoji': '🐋', 'description': '召唤蓝鲸伙伴，送上特别的庆祝表演。'},
    'gift': {'name': '惊喜拆礼物', 'price': 40, 'emoji': '🎁', 'description': '拆开一个神秘礼盒，看看里面的惊喜。'},
    'jump_catch': {'name': '跳跃接物', 'price': 40, 'emoji': '🙌', 'description': '伸手跳一跳，抓住头顶的小物品。'},
}
for _key, _value in TRICKS.items():
    _value.update(kind='action', animation=_key)

HATS = {
    'hat_beret': {'name': '莓莓贝雷帽', 'price': 30, 'description': '柔软的莓果色小帽子，陪你认真思考。'},
    'hat_sun': {'name': '晴天小草帽', 'price': 40, 'description': '系上蓝丝带，把晴天戴在头顶。'},
    'hat_wizard': {'name': '星星魔法帽', 'price': 60, 'description': '收集一点点努力，变成闪亮的小魔法。'},
}
for _key, _value in HATS.items():
    _value.update(kind='hat', image=f'/assets/hats/{_key}.svg',
                  overlay=f'/assets/hats/{_key}-worn.svg')
