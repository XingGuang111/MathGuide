"""Build local hat anchors from the largest skin-colored face in each clip.

Development helper only. Requires Playwright, Chromium and Pillow. Source videos
are decoded locally, sampled at 5 Hz, and anchors are visually reviewed in QA.
"""
import base64
import argparse
import io
import json
from pathlib import Path

from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'web/assets/pet'


def face(image):
    small = image.resize((320, 180)).convert('RGBA')
    pixels = small.load()
    mask = set()
    for y in range(15, 145):
        for x in range(55, 265):
            r, g, b, a = pixels[x, y]
            if a > 180 and r > 170 and g > 125 and b > 110 and r > g * 1.045 and r > b * 1.05:
                mask.add((x, y))
    best = []
    while mask:
        seed = mask.pop(); component = [seed]; todo = [seed]
        while todo:
            x, y = todo.pop()
            for point in [(x-1,y),(x+1,y),(x,y-1),(x,y+1)]:
                if point in mask:
                    mask.remove(point); component.append(point); todo.append(point)
        if len(component) > len(best): best = component
    if len(best) < 40:
        return None
    xs, ys = zip(*best)
    return [min(xs) + max(xs), min(ys) + max(ys)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clips', nargs='+', help='Rebuild only these clips, preserving all other anchors')
    args = parser.parse_args()
    output = ROOT / '.pet-qa/hat-tracks'
    output.mkdir(parents=True, exist_ok=True)
    tracks = {}
    tiles = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content('<video muted></video><canvas width="640" height="360"></canvas>')
        paths = sorted(ASSETS.glob('*.webm'))
        if args.clips:
            paths = [ASSETS / 'idle.webm'] + [ASSETS / (clip + '.webm') for clip in args.clips if clip != 'idle']
        for path in paths:
            raw = base64.b64encode(path.read_bytes()).decode('ascii')
            duration = page.evaluate('''async data => {
                const v=document.querySelector('video');
                const loaded=new Promise((ok,fail)=>{v.onloadeddata=ok;v.onerror=fail});
                v.src='data:video/webm;base64,'+data;v.load();await loaded;return v.duration;
            }''', raw)
            frames = []
            samples = []
            for index in range(int(duration * 5) + 1):
                t = min(duration - .02, max(.05, index / 5))
                data = page.evaluate('''async t=>{
                    const v=document.querySelector('video'),c=document.querySelector('canvas');
                    if(Math.abs(v.currentTime-t)>.001){const done=new Promise(ok=>v.onseeked=ok);v.currentTime=t;await done;}
                    const ctx=c.getContext('2d');ctx.clearRect(0,0,640,360);ctx.drawImage(v,0,0,640,360);return c.toDataURL('image/png').split(',')[1];
                }''', t)
                image = Image.open(io.BytesIO(base64.b64decode(data)))
                samples.append(face(image))
                if index in (0, int(duration*2.5), int(duration*5)-1):
                    frames.append(image.copy())
            tracks[path.stem] = {'interval': .2, 'points': samples}
            tile = Image.new('RGB', (640, 205), '#eff5fa')
            draw = ImageDraw.Draw(tile); draw.text((8, 3), path.stem, fill='#233044')
            for i, image in enumerate(frames[:3]):
                image.thumbnail((213, 180)); tile.paste(image, (i*213, 25), image)
            tiles.append(tile)
            print(path.stem, len(samples), 'face anchors', flush=True)
        browser.close()
    baseline = tracks['idle']['points'][0]
    for track in tracks.values():
        previous = baseline
        clean = []
        for point in track['points']:
            if point is None: point = previous
            # Reject hands/props when the face is temporarily occluded.
            if abs(point[0] - previous[0]) > 55 or abs(point[1] - previous[1]) > 55:
                point = previous
            clean.append([round(point[0]-baseline[0], 1), round(point[1]-baseline[1], 1)])
            previous = point
        track['points'] = clean
    if args.clips:
        previous_tracks = json.loads((ASSETS / 'hat-tracks.json').read_text(encoding='utf-8'))
        previous_tracks.update(tracks)
        tracks = previous_tracks
    (ASSETS / 'hat-tracks.json').write_text(json.dumps(tracks, separators=(',', ':')), encoding='utf-8')
    sheet = Image.new('RGB', (1280, ((len(tiles)+1)//2)*205), 'white')
    for i, tile in enumerate(tiles): sheet.paste(tile, ((i%2)*640, (i//2)*205))
    sheet.save(output / 'actions-contact-sheet.jpg')


if __name__ == '__main__':
    main()
