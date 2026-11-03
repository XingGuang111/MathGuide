"""Extract actual shop previews and hat anchors from local licensed animations."""
import argparse
import base64
import io
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright
from build_pet_hat_tracks import face

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pet_shop import ITEMS

ASSETS = ROOT / 'web/assets/pet'
IMAGES = ROOT / 'web/assets/items/shop'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previews-only', action='store_true')
    args = parser.parse_args()
    IMAGES.mkdir(parents=True, exist_ok=True)
    qa = ROOT / '.pet-qa/shop-assets'
    qa.mkdir(parents=True, exist_ok=True)
    tracks = json.loads((ASSETS / 'hat-tracks.json').read_text(encoding='utf-8'))
    tiles = []
    previews = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content('<video muted></video><canvas width="640" height="360"></canvas>')

        def load(clip):
            raw = base64.b64encode((ASSETS / (clip + '.webm')).read_bytes()).decode('ascii')
            return page.evaluate('''async data=>{
                const v=document.querySelector('video');
                const ready=new Promise((ok,fail)=>{v.onloadeddata=ok;v.onerror=fail});
                v.src='data:video/webm;base64,'+data;v.load();await ready;return v.duration;
            }''', raw)

        def frame(t):
            data = page.evaluate('''async t=>{
                const v=document.querySelector('video'),c=document.querySelector('canvas');
                if(Math.abs(v.currentTime-t)>.001){const ready=new Promise(ok=>v.onseeked=ok);v.currentTime=t;await ready;}
                const ctx=c.getContext('2d');ctx.clearRect(0,0,640,360);ctx.drawImage(v,0,0,640,360);
                return c.toDataURL('image/png').split(',')[1];
            }''', t)
            return Image.open(io.BytesIO(base64.b64decode(data))).convert('RGBA')

        load('idle'); baseline = face(frame(.05))
        for key, item in ITEMS.items():
            clip = item['animation']; duration = load(clip)
            preview_t = min(duration - .1, 6.5 if key == 'balloon' else min(duration * .45, 4.5))
            image = frame(preview_t)
            box = image.getchannel('A').point(lambda value: 255 if value > 32 else 0).getbbox()
            if box is None: raise ValueError(f'Empty preview: {key}')
            crop = image.crop((max(0, box[0]-8), max(0, box[1]-8), min(640, box[2]+8), min(360, box[3]+8)))
            crop.thumbnail((240, 240), Image.Resampling.LANCZOS)
            thumbnail = Image.new('RGBA', (256, 256))
            thumbnail.alpha_composite(crop, ((256-crop.width)//2, (256-crop.height)//2))
            target = IMAGES / (key + '.png'); thumbnail.save(target, optimize=True)
            previews[key] = {'animation': clip, 'time': preview_t, 'file': target.name}
            tile = Image.new('RGB', (256, 285), '#f1f7fb')
            tile.paste(thumbnail, (0, 25), thumbnail)
            ImageDraw.Draw(tile).text((8, 5), key, fill='#345771'); tiles.append(tile)
            if clip not in tracks and not args.previews_only:
                previous = baseline; points = []
                for index in range(int(duration*5)+1):
                    t = min(duration-.02, max(.05, index/5))
                    point = face(frame(t)) or previous
                    if abs(point[0]-previous[0])>55 or abs(point[1]-previous[1])>55: point = previous
                    points.append([point[0]-baseline[0], point[1]-baseline[1]]); previous = point
                tracks[clip] = {'interval': .2, 'points': points}
            print(key + ': preview and hat anchors ready', flush=True)
        browser.close()
    (IMAGES / 'previews.json').write_text(json.dumps(previews,indent=2), encoding='utf-8')
    (ASSETS / 'hat-tracks.json').write_text(json.dumps(tracks,separators=(',',':')), encoding='utf-8')
    sheet = Image.new('RGB', (256*5, ((len(tiles)+4)//5)*285), 'white')
    for index, tile in enumerate(tiles): sheet.paste(tile, ((index%5)*256, (index//5)*285))
    sheet.save(qa / 'shop-contact-sheet.jpg')


if __name__ == '__main__':
    main()
