"""Fetch pinned shop animations using official GitHub API, verified by Git SHA.

Only missing or changed assets are downloaded; no runtime network is needed.
"""
import base64
import hashlib
import json
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pet_shop import ITEMS

TARGET = ROOT / 'web/assets/pet'
COMMIT = 'ad9e2cb50348280634021e0699482f43b56ce1ca'
MANIFEST = TARGET / 'shop-manifest.json'


def request_json(path):
    url = f'https://api.github.com/repos/PC2005-cloud/dsh-pet/contents/{urllib.parse.quote(path)}?ref={COMMIT}'
    request = urllib.request.Request(url, headers={'User-Agent': 'MathGuide-shop-import'})
    with urllib.request.urlopen(request, timeout=40) as response:
        return json.load(response)


def fetch(entry):
    name, clip = entry
    target = TARGET / clip['file']
    if target.exists():
        data = target.read_bytes()
        if hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() == clip['git_blob']:
            return name, {**clip, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
    for attempt in range(3):
        try:
            payload = request_json('dsh-pet/assets/webm/' + clip['source'])
            if payload.get('encoding') != 'base64':
                raise ValueError('GitHub returned no base64 file content')
            data = base64.b64decode(payload['content'])
            actual = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
            if actual != clip['git_blob'] or payload['sha'] != clip['git_blob']:
                raise ValueError('Pinned Git blob mismatch')
            if not data.startswith(bytes.fromhex('1a45dfa3')):
                raise ValueError('Invalid WebM')
            temporary = target.with_suffix('.tmp')
            temporary.write_bytes(data); temporary.replace(target)
            print(f'{name}: verified {len(data)} bytes', flush=True)
            return name, {**clip, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
        except (OSError, ValueError) as exc:
            print(f'{name}: attempt {attempt + 1}: {exc}', flush=True)
            if attempt == 2: raise
            time.sleep(1)


def main():
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    # Keep the pinned README alongside the license: its character/asset notice
    # may differ from the code's MIT license.
    notice = TARGET / 'UPSTREAM-README.md'
    if not notice.exists():
        payload = request_json('README.md')
        notice.write_bytes(base64.b64decode(payload['content']))
    with ThreadPoolExecutor(max_workers=3) as pool:
        for name, clip in pool.map(fetch, manifest['clips'].items()):
            manifest['clips'][name] = clip
            temporary = MANIFEST.with_suffix('.tmp')
            temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(MANIFEST)


if __name__ == '__main__':
    main()
