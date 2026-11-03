"""Physical shop items mapped to pinned dsh-pet animations.

Food is consumed once; toys are permanent. Images are original object-only
catalog illustrations; the associated licensed animations remain unchanged.
"""

# id: name, price, mood, upstream animation, category
FOODS = {
    'rice': ('暖暖白米饭', 10, 8, '吃白饭', 'daily'),
    'breakfast': ('元气早餐', 15, 10, '吃早餐', 'daily'),
    'lunch': ('丰盛午餐', 20, 14, '吃午餐', 'daily'),
    'dinner': ('暖心晚餐', 20, 14, '吃晚餐', 'daily'),
    'icecream': ('甜筒冰淇淋', 15, 10, '吃冰淇淋融化', 'daily'),
    'crab': ('鲜美大闸蟹', 30, 20, '吃大闸蟹', 'daily'),
    'tanghulu': ('冰糖葫芦', 15, 10, '吃糖葫芦', 'daily'),
    'noodles': ('长寿面', 20, 14, '吃长寿面', 'daily'),
    'watermelon': ('清甜西瓜', 15, 10, '吃西瓜', 'daily'),
    'hotpot': ('咕嘟小火锅', 35, 24, '涮火锅', 'daily'),
    'token_snack': ('字符泡泡糖', 10, 8, '吃Token', 'daily'),
    'mooncake': ('团圆月饼', 20, 14, '中秋赏月吃月饼', 'festival'),
    'zongzi': ('粽香小粽子', 15, 10, '吃粽子', 'festival'),
    'niangao': ('软糯年糕', 15, 10, '吃年糕', 'festival'),
    'qingtuan': ('春日青团', 15, 10, '吃青团', 'festival'),
    'laba': ('暖暖腊八粥', 15, 10, '吃腊八粥', 'festival'),
    'chongyang': ('香甜重阳糕', 15, 10, '吃重阳糕', 'festival'),
    'tangyuan': ('团圆汤圆', 15, 10, '吃汤圆', 'festival'),
    'dumplings': ('热乎小饺子', 20, 14, '吃饺子', 'festival'),
}

TOYS = {
    'cube': ('彩色魔方', 50, 18, '原地专心玩魔方'),
    'toy_car': ('迷你小汽车', 50, 18, '原地蹲下玩玩具汽车'),
    'balloon': ('彩色气球', 40, 16, '吹气球'),
    'kite': ('晴空小风筝', 60, 20, '放风筝'),
    'spinning_top': ('旋转小陀螺', 45, 16, '抽陀螺'),
    'swing': ('微风小秋千', 70, 24, '荡秋千'),
    'rocking_horse': ('摇摇小木马', 65, 22, '骑木马'),
}

ITEMS = {}
for _key, (_name, _price, _mood, _source, _category) in FOODS.items():
    ITEMS[_key] = {
        'name': _name, 'kind': 'food', 'category': _category, 'price': _price,
        'mood': _mood, 'image': f'/assets/items/shop/illustrated/{_key}.png',
        'animation': 'token' if _key == 'token_snack' else f'food_{_key}',
        'source_action': _source, 'embedded_prop': True,
        'description': f'喂食后播放{_source}的专属动作 · 每次消耗 1 份',
    }
for _key, (_name, _price, _mood, _source) in TOYS.items():
    ITEMS[_key] = {
        'name': _name, 'kind': 'toy', 'category': 'toy', 'price': _price,
        'mood': _mood, 'image': f'/assets/items/shop/illustrated/{_key}.png',
        'animation': f'toy_{_key}', 'source_action': _source, 'embedded_prop': True,
        'description': f'一起{_source} · 购买后可反复玩',
    }
