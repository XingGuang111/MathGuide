"""Original SVG shop illustrations, exported to transparent 256px PNGs.

These editable objects extend MathGuide's existing vector item icon style.
They are purpose-drawn catalog illustrations, not animation screenshots.
"""
import base64
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pet_shop import ITEMS

TARGET = ROOT / 'web/assets/items/shop/illustrated'


def path(d, fill, stroke='#684e45', width=2.2, extra=''):
    return f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round" {extra}/>'


def ellipse(x, y, rx, ry, fill, stroke='none', width=2):
    return f'<ellipse cx="{x}" cy="{y}" rx="{rx}" ry="{ry}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"/>'


def circle(x, y, r, fill, stroke='none', width=2):
    return ellipse(x, y, r, r, fill, stroke, width)


def line(x1, y1, x2, y2, color, width=2):
    return path(f'M{x1} {y1}L{x2} {y2}', 'none', color, width)


def group(art, transform):
    return f'<g transform="{transform}">{art}</g>'


def plate(x=64, y=94, rx=45, ry=12):
    return ellipse(x,y+3,rx,ry,'#dce8ed','#6d8793')+ellipse(x,y,rx,ry,'#fcfcf4','#6d8793')+ellipse(x,y,rx-6,ry-3,'#f5eee0','#d9cbb9',1)


def bowl(contents, brown=False, pattern=False):
    body = '#a96b43' if brown else '#dbe6f1'
    rim = '#704526' if brown else '#668aa2'
    art = path('M23 65Q26 102 64 106Q102 102 105 65Z',body,rim)
    art += path('M31 73Q36 94 53 98', 'none', '#c48c59' if brown else '#f9fcff', 4)
    art += ellipse(64,65,41,12,'#fdfaf1',rim)
    art += ellipse(64,65,35,8,contents)
    art += path('M53 105Q64 111 76 105','none',rim,3)
    if pattern:
        art += path('M48 84Q57 77 63 87Q71 76 79 84Q74 94 64 94Q53 94 48 84Z','#729fc2','#5e8eb2',1)
        art += circle(39,83,2,'#729fc2')+circle(89,83,2,'#729fc2')
    return art


def rice():
    a=bowl('#fbf6df')
    a+=path('M29 63Q28 56 36 54Q35 47 44 48Q45 38 55 42Q64 31 72 42Q82 38 84 47Q95 45 96 55Q103 57 99 64Z','#fff9e8','#cdbb99',1.5)
    for i in range(27):
        x=35+(i*17)%60;y=48+(i*11)%14
        a+=line(x,y,x+3,y-1,'#e3d6b6',1)
    return a


def noodle(dark=False):
    a=bowl('#dbae5e',brown=dark)
    for i in range(8):
        a+=path(f'M{38+i*6} 64q-5 -5 3 -8q9 -3 6 4q-2 4 6 5','none','#fff0b2',2)
    a+=line(37,48,97,31,'#725134',3)+line(39,53,99,37,'#725134',3)
    for i in range(4):
        a+=path(f'M{65+i*3} 44Q{61+i*3} 53 {67+i*3} 63','none','#f5cf6f',2)
    a+=ellipse(43,60,5,2,'#78a365')+ellipse(81,61,5,2,'#78a365')
    return a


def bun(x,y,r,color='#f3ead3'):
    a=path(f'M{x-r} {y}Q{x-r} {y-r*.9} {x} {y-r}Q{x+r} {y-r*.9} {x+r} {y}Q{x+r*.4} {y+r*.5} {x-r} {y}Z',color,'#bba386',1.5)
    a+=path(f'M{x-r*.5} {y-r*.45}q{r*.2} {-r*.35} {r*.6} {-r*.3}','none','#fff9e8',2)
    return a


def meal():
    a=group(rice(),'translate(24 -8) scale(.65)')
    a+=plate(38,98,29,9)+plate(91,95,27,9)
    for i in range(8):
        x=19+(i*13)%39;y=82+(i*7)%11
        a+=path(f'M{x} {y}l9 -2l5 6l-3 6l-10 -1Z','#ad5734','#7c3e2b',1.3)+path(f'M{x+2} {y+1}l5 -1','none','#e5a15e',1.4)
    for i in range(9):
        a+=circle(74+(i*11)%33,82+(i*7)%12,5,['#e8b34b','#d97843','#82a75d'][i%3],'#a97c43',1)
    return a


def dumpling(x,y):
    a=path(f'M{x-12} {y+5}Q{x-11} {y-11} {x} {y-12}Q{x+10} {y-10} {x+13} {y+3}Q{x+1} {y+12} {x-12} {y+5}Z','#fff1cc','#bda17a',1.5)
    for i in range(4):a+=path(f'M{x-6+i*4} {y-7}l-2 7','none','#d9be91',1)
    return a


def cube():
    a=''
    colors=['#e7b866','#e37668','#9bc8a5','#a8c6e1','#f6e7b5','#d4aad4']
    for row in range(3):
        for col in range(3):
            x=29+col*18;y=42+row*18
            a+=path(f'M{x} {y}h17v17h-17Z',colors[(row*3+col)%6],'#665956',1.6)
    for col in range(3):
        x=29+col*18
        a+=path(f'M{x} 42l18 -15h17l-18 15Z',colors[(col+2)%6],'#665956',1.6)
    for row in range(3):
        y=42+row*18
        a+=path(f'M83 {y}l18 -15v17l-18 15Z',colors[(row+4)%6],'#665956',1.6)
    return a


def illustration(key):
    if key=='rice':return rice()
    if key=='breakfast':
        return group(bowl('#f5e5bf'),'translate(33 15) scale(.65)')+path('M24 79L37 39Q39 33 45 34L65 43L50 87Q40 92 24 79Z','#d99b4d','#986131')+path('M32 75L43 43L56 49L46 80Z','#f8d48b','#e5b064',1.5)
    if key=='lunch':return noodle(True)
    if key=='dinner':return meal()
    if key=='icecream':
        a=path('M42 60L86 60L65 112Z','#e2ad6b','#a97846')
        for i in range(4):a+=line(45+i*7,64,68+i*3,94-i*3,'#bc874e',1)+line(83-i*7,64,60-i*2,94-i*3,'#bc874e',1)
        a+=path('M35 57Q31 49 38 43Q34 33 45 30Q51 17 63 24Q75 18 82 30Q96 32 91 44Q102 56 90 63Q82 67 76 61Q66 69 58 61Q46 68 35 57Z','#efb1be','#b67483')
        a+=path('M45 35Q49 29 56 31','none','#ffe2e5',4)
        return a
    if key=='crab':
        a=plate()
        for side in [-1,1]:
            for i in range(4):
                x=64+side*21;y=65+i*5
                a+=path(f'M{x} {y}l{side*(17+i)} {-8+i*2}l{side*4} 9','none','#b85a2c',5)
            a+=path(f'M{64+side*22} 61q{side*22} -13 {side*16} -28q{side*-6} 5 -5 15q-9 -5 -9 -13q-8 11 1 23Z','#e6893e','#a6532d')
        a+=ellipse(64,72,30,20,'#dc7c35','#a6532d')+path('M44 67Q62 51 84 67','none','#f3ad5b',4)
        a+=circle(54,53,3,'#68452d')+circle(74,53,3,'#68452d')
        return a
    if key=='tanghulu':
        a=line(64,19,64,115,'#bd914c',4)
        for y in [35,60,85]:a+=circle(64,y,15,'#cf5549','#923b37')+path(f'M56 {y-5}q3 -5 8 -4','none','#ffd0a0',3)
        return a
    if key=='noodles':return noodle()
    if key=='watermelon':
        a=path('M18 57Q64 102 110 57Q110 101 64 108Q19 102 18 57Z','#6ea064','#426d48')
        a+=ellipse(64,58,46,23,'#b9cf79','#426d48')+ellipse(64,56,39,18,'#ed8a83','#f7d4a0',2)
        for x,y in [(39,53),(57,47),(75,49),(89,57),(50,62),(72,65)]:a+=ellipse(x,y,1.8,3,'#634b46')
        a+=path('M29 78q5 12 15 16M51 85l3 15M78 84l-2 15M98 77l-7 17','none','#476e45',4)
        return a
    if key=='hotpot':
        a=path('M35 105L44 84L55 98L65 81L74 100L87 86L94 107Z','#e9a344','#c87a35')
        a+=path('M42 106l9 -12l6 9l8 -14l6 15l7 -8l10 12Z','#ffd981','none')
        a+=path('M24 57Q23 91 64 97Q106 92 105 57Z','#a27b55','#6f5743')+ellipse(64,57,42,14,'#d0a878','#6f5743')+ellipse(64,57,35,9,'#f1dcad','#907047')
        a+=path('M24 65Q8 57 12 73Q15 79 28 76M104 65Q120 57 116 73Q113 79 100 76','none','#6f5743',5)
        for x,y,col in [(45,55,'#e48c69'),(63,57,'#fff6d7'),(79,56,'#88a56a')]:a+=ellipse(x,y,6,3,col)
        a+=path('M46 34q-8 -9 0 -17M65 32q-8 -9 0 -17M84 34q-8 -9 0 -17','none','#b1c8c9',2)
        return a
    if key=='token_snack':
        a=''
        for x,y,r in [(41,52,24),(82,77,22)]:
            a+=circle(x,y,r,'#abd7e8','#6b9cbd')+circle(x,y,r-5,'#d7eff3','#82b6d2',1.5)+ellipse(x-7,y-9,5,3,'#f6ffff')+path(f'M{x} {y-12}l7 12l-7 12l-7 -12Z','#95c9df','#6b9cbd',1)
        return a
    if key=='mooncake':
        a=plate(y=100,rx=39,ry=9)
        for i in range(12):
            angle=i*math.pi/6
            a+=ellipse(round(64+27*math.cos(angle),2),round(66+15*math.sin(angle),2),8,10,'#cc8b47','#a66b34',1.5)
        a+=ellipse(64,69,29,21,'#dca15b','#a66b34')+ellipse(64,62,29,19,'#e9b76f','#a66b34')+ellipse(64,62,23,14,'none','#c78b46')
        a+=path('M55 62q-8 -9 0 -11q9 -2 9 9q-2 -10 7 -9q9 2 1 11q10 -3 10 3q-2 8 -13 3q0 9 -6 9q-7 0 -6 -9q-11 4 -12 -3q0 -6 10 -3Z','none','#bd803d',1.7)
        return a
    if key=='zongzi':
        a=path('M17 80L66 33L110 85L62 107Z','#6b9466','#486b4d')+path('M25 79L62 99L103 83','none','#a8bd7b',2)
        a+=path('M36 76Q43 56 63 39Q78 55 91 79Q63 91 36 76Z','#fff1cf','#bcaa86')+ellipse(65,62,6,8,'#b45d4b','#854236')
        a+=line(20,80,62,91,'#a9bc7a',2)+line(63,106,77,90,'#a9bc7a',2)
        return a
    if key=='niangao':
        a=plate(y=99,rx=46,ry=12)
        for x,y in [(42,79),(64,66),(85,82)]:
            a+=path(f'M{x-15} {y-8}q15 -10 30 0v15q-15 10 -30 0Z','#eee4cb','#b6a080',1.5)+ellipse(x,y-8,15,6,'#fff5dc','#b6a080',1.5)
        return a
    if key=='qingtuan':
        a=plate(y=99,rx=42,ry=10)
        for x,y,r in [(43,78,20),(80,80,21),(64,54,23)]:
            a+=circle(x,y,r,'#8ca35e','#607848')+ellipse(x-6,y-8,6,3,'#b8ca83')+path(f'M{x-r*.6} {y+r*.5}q{r*.6} {r*.5} {r*1.2} 0','none','#738d4d',1.5)
        return a
    if key=='laba':
        a=bowl('#b98670',True)
        for i in range(15):a+=ellipse(37+(i*13)%53,60+(i*7)%9,3,1.8,['#8e5144','#d8bc7d','#eee1b0'][i%3])
        return a+path('M80 63L105 39','none','#9c744d',4)+ellipse(79,65,7,3,'#c19c6e','#8c6946',1.5)
    if key=='chongyang':
        a=plate(y=101,rx=43,ry=9)
        for x,y in [(44,81),(78,68)]:
            a+=path(f'M{x-17} {y-17}q17 -12 34 0v29q-17 11 -34 0Z','#f2d9ab','#bda079')+ellipse(x,y-17,17,8,'#fff0ce','#bda079')
            a+=ellipse(x,y-17,9,5,'#a75e4b','#874b3e',1)+line(x-14,y+1,x+14,y+1,'#d6b886',2)
        return a
    if key=='tangyuan':
        a=bowl('#f2e9cf',pattern=True)
        for x,y in [(44,65),(62,61),(80,66)]:a+=ellipse(x,y,9,6,'#fff9e6','#d1c4a6',1.3)
        return a+path('M87 59L106 35','none','#86a5ba',4)+ellipse(85,61,7,4,'#e7f0f5','#7a9aae',1.5)
    if key=='dumplings':
        a=bowl('#f5e6c0',pattern=True)
        return a+dumpling(47,60)+dumpling(72,60)+dumpling(63,48)+line(26,39,98,27,'#8c6344',3)+line(28,45,100,33,'#8c6344',3)
    if key=='cube':return cube()
    if key=='toy_car':
        a=path('M18 69L28 65L39 44Q63 35 85 47L99 65L111 69L113 89L17 89Z','#dbbc6e','#8a734c')+path('M43 48L34 66L60 66L60 45Z','#a1c6d5','#748c90')+path('M66 45L66 66L91 66L80 48Z','#b6d6df','#748c90')
        a+=path('M19 71h92v14H19Z','#d98976','#8a734c',1.5)+circle(38,89,12,'#607483','#435968')+circle(92,89,12,'#607483','#435968')+circle(38,89,5,'#b1c9cd')+circle(92,89,5,'#b1c9cd')+ellipse(108,75,3,5,'#f7ecc3')
        return a
    if key=='balloon':
        return path('M65 83q-16 11 -3 18q9 7 -3 15','none','#9b8a7b',1.8)+ellipse(64,45,31,39,'#7db4d7','#557f9d')+path('M57 83L71 83L65 74Z','#659ac0','#557f9d',1.5)+ellipse(51,29,8,13,'#c5e6f1')
    if key=='kite':
        return path('M70 83q-8 19 10 19q18 1 7 15','none','#748eaa',2)+path('M63 14L99 51L70 85L30 52Z','#e1b16f','#7f7668')+path('M63 14L63 52L30 52Z','#d9907c','#7f7668',1.5)+path('M63 14L99 51L63 52Z','#8bb7cb','#7f7668',1.5)+path('M30 52L63 52L70 85Z','#b9c8a4','#7f7668',1.5)+path('M70 85q25 9 33 1','none','#d6a35e',3)+path('M80 104l-7 -6l-2 10Z','#d99580','#9b7564',1)
    if key=='spinning_top':
        return path('M58 31h12v13H58Z','#df9e62','#986e4d')+path('M22 68Q64 27 106 68Q97 94 64 105Q31 94 22 68Z','#d8ae5f','#8e7149')+ellipse(64,67,42,14,'#92bdc5','#6c8d99')+ellipse(64,63,31,9,'#d99283','#b47869')+ellipse(64,60,20,5,'#edcc82','#b5985d')+path('M59 103L64 115L69 103Z','#976c4b','#79543e')
    if key=='swing':
        return line(34,13,35,86,'#aa9274',4)+line(94,13,93,86,'#aa9274',4)+path('M24 84L93 80L107 91L36 98Z','#c89565','#8d694e')+path('M36 98v7l71 -7v-7Z','#aa7b56','#8d694e')+path('M24 84v7l12 14v-7Z','#d2a47a','#8d694e')+path('M30 86l66 -3','none','#edc49b',2)
    if key=='rocking_horse':
        return path('M20 101Q63 121 108 98L105 109Q64 128 22 111Z','#b76e55','#84503f')+path('M38 95L43 72L55 75L50 100M78 96L76 70L88 68L91 99','#b97852','#80573e')+path('M27 59Q41 48 63 56L79 33L83 24L93 31L103 29L112 46Q113 56 102 58L88 56L83 73Q55 91 32 75L20 81L21 68Z','#cb8b60','#80573e')+path('M78 33q5 -11 12 -8l-2 -12l-8 10q-12 7 -13 23','none','#8b5b45',6)+path('M34 55q-16 -10 -17 10','none','#8b5b45',5)+path('M48 54h22l-5 14H47Z','#cf8c8b','#955e5b')+circle(101,40,2,'#614a3b')+path('M98 52q6 3 9 -1','none','#9c6249',1.5)
    raise KeyError(key)


def main():
    from playwright.sync_api import sync_playwright
    from PIL import Image, ImageDraw
    TARGET.mkdir(parents=True, exist_ok=True)
    tiles=[]
    manifest={}
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page()
        for key, item in ITEMS.items():
            art=illustration(key)
            svg='<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 128 128">'+ellipse(64,114,38,4,'#75909b18')+art+'</svg>'
            (TARGET/(key+'.svg')).write_text(svg,encoding='utf-8')
            encoded=base64.b64encode(svg.encode()).decode()
            png=page.evaluate('''async encoded=>{
                const im=new Image();im.src='data:image/svg+xml;base64,'+encoded;await im.decode();
                const c=document.createElement('canvas');c.width=256;c.height=256;
                c.getContext('2d').drawImage(im,0,0);return c.toDataURL('image/png').split(',')[1];
            }''',encoded)
            (TARGET/(key+'.png')).write_bytes(base64.b64decode(png))
            tile=Image.new('RGB',(256,280),'#f1f7fb');icon=Image.open(TARGET/(key+'.png'))
            tile.paste(icon,(0,24),icon);ImageDraw.Draw(tile).text((8,5),key,fill='#345771');tiles.append(tile)
            manifest[key]={'source':'original MathGuide vector illustration','svg':key+'.svg','png':key+'.png','animation':item['animation'],'contains_character':False}
        browser.close()
    (TARGET/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    sheet=Image.new('RGB',(1280,280*6),'#f1f7fb')
    for i,tile in enumerate(tiles):sheet.paste(tile,((i%5)*256,(i//5)*280))
    sheet.save(ROOT/'.pet-qa/shop-illustrated-contact.jpg')
    print(f'Created {len(tiles)} original object-only SVG + transparent PNG icons.')


if __name__=='__main__':main()
