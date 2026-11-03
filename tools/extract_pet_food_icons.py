"""Cut real visible food pixels from licensed animations, without the character.

Masks are traced in the existing 256px reference previews and transformed back
to the original video frame. No food is generated or substituted. Occluded
parts are not invented. Original character previews and videos stay intact.
"""
import argparse
import base64
import io
import json
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pet_shop import FOODS, ITEMS

SOURCE = ROOT / 'web/assets/items/shop'
OUTPUT = SOURCE / 'food'
CACHE = ROOT / '.pet-qa/shop-food-frames'

# A union of polygons keeps only food and its dishes, omitting hands/hair.
MASKS = {
    'rice': [[(96,149),(101,142),(111,138),(123,138),(132,143),(141,150),(139,155),(135,157),(132,169),(119,173),(108,171),(100,164)]],
    'breakfast': [[(91,174),(100,171),(122,172),(132,176),(129,184),(129,192),(117,197),(105,197),(96,192)],[(72,150),(78,151),(83,153),(91,151),(94,153),(87,166),(79,180),(74,185),(71,180),(69,178),(66,177)]],
    'lunch': [[(87,164),(100,161),(100,150),(103,148),(116,149),(118,153),(119,163),(128,165),(133,168),(130,178),(128,188),(119,194),(104,196),(92,191),(86,184),(82,171)]],
    'dinner': [[(12,206),(20,199),(31,196),(32,189),(40,185),(53,185),(59,180),(67,182),(77,188),(78,195),(88,200),(95,205),(91,213),(72,217),(37,217),(20,214)],[(163,202),(173,198),(181,193),(185,186),(192,187),(200,190),(205,187),(214,190),(215,194),(227,196),(239,201),(242,207),(235,213),(213,216),(186,216),(170,212)],[(111,169),(114,164),(122,162),(132,166),(140,172),(137,179),(138,183),(133,187),(124,190),(114,186),(109,177)]],
    'icecream': [[(49,143),(60,139),(72,140),(80,144),(75,147),(66,145),(62,148),(60,153),(55,151)],[(58,155),(65,152),(73,152),(79,157),(85,161),(90,171),(87,177),(85,180),(84,191),(81,199),(77,211),(74,216),(71,208),(70,191),(65,185),(64,181),(59,177),(57,168)]],
    'crab': [[(66,203),(74,199),(76,185),(82,180),(92,184),(103,181),(116,184),(121,181),(132,183),(138,191),(141,201),(151,204),(150,211),(139,216),(121,219),(94,219),(76,214)],[(139,171),(151,168),(162,170),(169,173),(165,182),(158,184),(145,181)]],
    'tanghulu': [[(101,133),(105,132),(110,134),(116,132),(121,135),(122,141),(119,147),(121,152),(119,157),(115,163),(106,162),(102,156),(101,151),(104,146),(100,141)]],
    'noodles': [[(76,161),(85,158),(94,158),(104,158),(108,155),(109,148),(114,147),(118,155),(122,158),(135,160),(141,164),(136,173),(133,183),(124,190),(109,192),(95,188),(87,181),(83,173)]],
    'watermelon': [[(78,187),(85,184),(80,181),(80,171),(88,166),(101,163),(114,165),(126,169),(137,168),(143,172),(140,181),(137,188),(143,189),(149,192),(146,200),(129,205),(104,208),(84,203),(73,199),(69,195)]],
    'hotpot': [[(37,187),(44,181),(57,176),(81,173),(109,174),(125,178),(136,185),(137,190),(145,190),(147,195),(139,198),(133,199),(129,212),(120,219),(113,222),(119,233),(107,239),(95,241),(82,240),(69,242),(58,238),(66,229),(67,224),(56,219),(49,213),(46,201),(39,200),(36,194)]],
    'token_snack': [[(14,120),(20,111),(27,109),(34,112),(39,120),(40,130),(36,138),(30,141),(22,138),(17,132)],[(149,146),(152,137),(160,132),(167,133),(174,138),(178,145),(175,154),(168,159),(159,158),(152,153)],[(210,126),(215,118),(223,115),(231,116),(240,121),(243,128),(241,136),(235,143),(226,144),(218,139)]],
    'mooncake': [[(54,141),(57,136),(62,133),(69,133),(77,136),(81,141),(80,147),(75,153),(64,153),(58,150)],[(43,169),(49,166),(61,164),(75,165),(87,168),(91,172),(87,175),(75,178),(59,178),(48,175)]],
    'zongzi': [[(69,168),(84,165),(100,166),(105,155),(114,147),(121,146),(130,150),(139,161),(146,167),(160,166),(179,167),(166,175),(152,180),(143,186),(126,186),(114,184),(102,181),(84,177)]],
    'niangao': [[(129,159),(135,155),(148,153),(161,156),(166,162),(168,166),(178,165),(187,171),(187,180),(179,186),(159,191),(133,190),(117,187),(114,181),(116,176),(126,174)]],
    'qingtuan': [[(94,145),(101,139),(111,134),(120,134),(128,138),(132,145),(130,152),(125,156),(124,164),(118,168),(109,167),(102,163),(100,156),(96,152)]],
    'laba': [[(66,158),(69,156),(82,161),(93,164),(107,162),(123,163),(135,167),(145,171),(148,175),(145,184),(142,193),(135,202),(124,209),(110,211),(96,208),(86,201),(80,193),(76,182),(77,175),(73,170)]],
    'chongyang': [[(86,169),(91,163),(99,160),(107,164),(114,174),(116,181),(113,187),(109,190),(95,190),(88,188),(87,182)],[(124,175),(129,167),(136,164),(142,167),(146,172),(143,180),(140,187),(130,191),(121,189),(121,183)]],
    'tangyuan': [[(94,171),(100,167),(115,164),(131,164),(144,168),(149,171),(146,176),(144,180),(144,187),(136,194),(122,198),(108,194),(98,189),(95,180)],[(115,148),(117,148),(119,166),(116,166)]],
    'dumplings': [[(35,213),(44,208),(58,206),(73,207),(86,212),(88,217),(85,228),(78,236),(66,239),(55,238),(43,233),(37,224)]],
}

# Tightened after checking enlarged cutouts: exclude sleeves and apron edges.
MASKS.update({
    'icecream': [[(58,126),(64,126),(67,131),(73,131),(80,138),(86,145),(86,151),(82,155),(83,161),(78,173),(72,187),(67,180),(63,170),(61,160),(58,152),(56,144)]],
    'dinner': MASKS['dinner'][:2] + [[(110,169),(116,166),(125,165),(134,169),(137,173),(134,180),(130,184),(121,185),(113,181),(110,176)]],
    'crab': [[(65,195),(74,191),(77,182),(83,179),(92,183),(103,180),(115,183),(121,180),(132,183),(138,191),(149,195),(147,201),(137,205),(119,207),(94,207),(76,203)]],
    'token_snack': [MASKS['token_snack'][0], MASKS['token_snack'][2]],
    'mooncake': [MASKS['mooncake'][0]],
    'niangao': [[(127,172),(134,170),(142,172),(150,173),(159,173),(166,176),(176,177),(183,181),(187,187),(185,192),(179,195),(165,194),(156,190),(147,188),(137,189),(127,185),(121,181)]],
    'qingtuan': [[(105,141),(109,137),(116,137),(123,140),(127,145),(127,151),(123,156),(122,162),(117,164),(111,162),(107,158),(106,153),(103,149)]],
    'laba': [[(85,171),(91,169),(99,170),(105,173),(115,174),(123,172),(134,174),(142,178),(143,185),(137,193),(129,198),(117,201),(104,198),(94,194),(89,187),(83,181)]],
    'zongzi': [[(69,168),(84,165),(100,166),(105,155),(114,147),(121,146),(130,150),(139,161),(146,167),(160,166),(179,167),(165,173),(151,177),(139,180),(126,183),(114,181),(102,178),(84,175)]],
})
MASKS['icecream'] = [[(62,145),(68,144),(75,146),(81,150),(84,156),(81,164),(76,177),(71,185),(67,181),(64,173),(61,164)]]
MASKS['niangao'] = [[(136,165),(143,165),(149,168),(157,168),(164,169),(172,172),(180,173),(186,179),(188,185),(184,188),(178,188),(169,184),(161,182),(152,181),(144,178),(138,174),(133,170)]]
MASKS['qingtuan'] = [[(108,141),(112,138),(117,139),(120,142),(121,147),(120,152),(119,156),(117,160),(114,161),(111,158),(109,154),(108,150),(107,146)]]
MASKS['laba'] = [[(89,173),(94,171),(100,173),(105,175),(112,177),(119,175),(126,176),(133,178),(139,182),(137,187),(133,193),(125,197),(116,198),(107,195),(99,191),(94,185),(90,180)]]

# The hand crosses the cone and a few bowl rims. Small texture repairs use
# neighbouring original pixels; no replacement food illustration is used.
REPAIR = {
    'icecream': [[(62,155),(66,155),(67,161),(70,168),(74,176),(73,182),(69,179),(65,171),(62,163)]],
    'rice': [[(130,157),(137,155),(141,156),(139,166),(133,171),(128,169)]],
    'breakfast': [[(126,180),(133,178),(135,184),(131,193),(126,193)]],
    'noodles': [[(133,165),(142,161),(144,166),(139,177),(133,187),(129,185)]],
    'watermelon': [[(80,168),(86,165),(96,164),(101,167),(100,174),(92,175),(85,172)]],
    'tangyuan': [[(139,177),(148,174),(151,180),(147,188),(139,191),(136,186)]],
}


def get_frames():
    from playwright.sync_api import sync_playwright
    metadata = json.loads((SOURCE / 'previews.json').read_text(encoding='utf-8'))
    CACHE.mkdir(parents=True, exist_ok=True)
    missing = [key for key in FOODS if not (CACHE / (key + '.png')).exists()]
    if not missing:
        return
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content('<video muted></video><canvas width="640" height="360"></canvas>')
        for key in missing:
            raw = base64.b64encode((ROOT / 'web/assets/pet' / (ITEMS[key]['animation'] + '.webm')).read_bytes()).decode()
            data = page.evaluate('''async ({raw,time})=>{
                const v=document.querySelector('video'),c=document.querySelector('canvas');
                let ready=new Promise((ok,fail)=>{v.onloadeddata=ok;v.onerror=fail});
                v.src='data:video/webm;base64,'+raw;v.load();await ready;
                ready=new Promise(ok=>v.onseeked=ok);v.currentTime=time;await ready;
                const ctx=c.getContext('2d');ctx.clearRect(0,0,640,360);ctx.drawImage(v,0,0,640,360);
                return c.toDataURL('image/png').split(',')[1];
            }''', {'raw': raw, 'time': metadata[key]['time']})
            (CACHE / (key + '.png')).write_bytes(base64.b64decode(data))
        browser.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-only', action='store_true', help='Quick mask review at existing preview resolution')
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if not args.reference_only:
        get_frames()
    tiles = []
    metadata = {}
    for key in FOODS:
        if args.reference_only:
            source = Image.open(SOURCE / (key + '.png')).convert('RGBA')
            polygons = MASKS[key]
            transform = lambda polygon: polygon
        else:
            source = Image.open(CACHE / (key + '.png')).convert('RGBA')
            box = source.getchannel('A').point(lambda value: 255 if value > 32 else 0).getbbox()
            box = (max(0, box[0]-8), max(0, box[1]-8), min(640, box[2]+8), min(360, box[3]+8))
            crop = source.crop(box)
            crop.thumbnail((240, 240), Image.Resampling.LANCZOS)
            sx, sy = (box[2]-box[0])/crop.width, (box[3]-box[1])/crop.height
            ox, oy = (256-crop.width)//2, (256-crop.height)//2
            transform = lambda polygon: [(round(box[0]+(x-ox)*sx), round(box[1]+(y-oy)*sy)) for x,y in polygon]
            polygons = [transform(poly) for poly in MASKS[key]]
        if key in REPAIR:
            import cv2
            import numpy as np
            repair = Image.new('L', source.size)
            for polygon in REPAIR[key]:
                ImageDraw.Draw(repair).polygon(transform(polygon), fill=255)
            rgb = cv2.inpaint(np.array(source.convert('RGB')), np.array(repair), 5, cv2.INPAINT_TELEA)
            alpha = source.getchannel('A')
            source = Image.fromarray(rgb).convert('RGBA')
            source.putalpha(alpha)
        mask = Image.new('L', source.size)
        draw = ImageDraw.Draw(mask)
        for polygon in polygons:
            draw.polygon(polygon, fill=255)
        source.putalpha(ImageChops.multiply(source.getchannel('A'), mask))
        content = source.crop(source.getbbox())
        scale = min(216/content.width, 216/content.height)
        content = content.resize((round(content.width*scale), round(content.height*scale)), Image.Resampling.LANCZOS)
        icon = Image.new('RGBA', (256, 256))
        icon.alpha_composite(content, ((256-content.width)//2, (256-content.height)//2))
        icon.save(OUTPUT / (key + '.png'), optimize=True)
        metadata[key] = {'animation': ITEMS[key]['animation'], 'method': 'visible-source-pixels-with-reviewed-food-mask', 'character_removed': True}
        tile = Image.new('RGB', (256, 284), '#f1f7fb')
        tile.paste(icon, (0, 24), icon)
        ImageDraw.Draw(tile).text((8, 5), key, fill='#345771')
        tiles.append(tile)
    (OUTPUT / 'manifest.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    sheet = Image.new('RGB', (1280, 284*4), '#f1f7fb')
    for i, tile in enumerate(tiles):
        sheet.paste(tile, ((i%5)*256, (i//5)*284))
    sheet.save(ROOT / '.pet-qa/shop-food-cutouts.jpg')
    print(f'Extracted {len(tiles)} food-only icons; original animations preserved.')


if __name__ == '__main__':
    main()
