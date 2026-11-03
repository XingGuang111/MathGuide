"""Import extra clips used by dsh-dafeiyu-enhanced, with hash checks.

Uses the plugin's pinned upstream sources. See ASSET-NOTICE.md for asset terms.
Re-running resumes by skipping verified files. Nothing is fetched at runtime.
"""
import base64
import argparse
import hashlib
import http.client
import json
import subprocess
from functools import partial
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'web/assets/pet'


def fetch_clip(entry, from_git=None):
    name, clip = entry
    target = TARGET / clip['file']
    if target.exists():
        data = target.read_bytes()
        sha256 = hashlib.sha256(data).hexdigest()
        blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        if sha256 == clip.get('sha256') or (not clip.get('sha256') and blob == clip.get('git_blob')):
            print(f'{name}: verified local file', flush=True)
            return name, {**clip, 'sha256': sha256, 'bytes': len(data)}
    path = urllib.parse.quote('dsh-pet/assets/webm/' + clip['source'])
    urls = [f"https://raw.githubusercontent.com/PC2005-cloud/dsh-pet/{clip['commit']}/{path}",
            f"https://api.github.com/repos/PC2005-cloud/dsh-pet/contents/{path}?ref={clip['commit']}"]
    if clip.get('git_blob'):
        urls = [urls[1], urls[1]]
    for attempt in range(3):
        try:
            print(f'{name}: downloading (attempt {attempt + 1})', flush=True)
            if from_git:
                data = subprocess.check_output(['git', '-C', str(from_git), 'show',
                    f"{clip['commit']}:dsh-pet/assets/webm/{clip['source']}"], timeout=90)
            else:
                url = urls[min(attempt, 1)]
                request = urllib.request.Request(url, headers={'User-Agent': 'MathGuide-asset-import'})
                with urllib.request.urlopen(request, timeout=30) as response:
                    data = response.read()
                if 'api.github.com' in url:
                    payload = json.loads(data)
                    if payload.get('encoding') != 'base64':
                        raise ValueError('No base64 data returned by GitHub')
                    data = base64.b64decode(payload['content'])
            if not data.startswith(bytes.fromhex('1a45dfa3')):
                raise ValueError('Invalid WebM header')
            sha256 = hashlib.sha256(data).hexdigest()
            blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
            if clip.get('sha256') and sha256 != clip['sha256']:
                raise ValueError('Source hash mismatch or incomplete download')
            if clip.get('git_blob') and blob != clip['git_blob']:
                raise ValueError('Pinned Git blob mismatch')
            target.with_suffix('.tmp').write_bytes(data)
            target.with_suffix('.tmp').replace(target)
            print(f'{name}: verified {len(data)} bytes', flush=True)
            return name, {**clip, 'sha256': sha256, 'bytes': len(data)}
        except (OSError, ValueError, http.client.HTTPException, subprocess.SubprocessError) as exc:
            print(f'{name}: {exc}', flush=True)
            if attempt == 2:
                raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from-git', type=Path, help='Use a local upstream checkout, fetching missing Git blobs if needed')
    args = parser.parse_args()
    manifest = json.loads((TARGET / 'tricks.json').read_text(encoding='utf-8'))
    with ThreadPoolExecutor(max_workers=3) as pool:
        for name, clip in pool.map(partial(fetch_clip, from_git=args.from_git), manifest['clips'].items()):
            manifest['clips'][name] = clip
            (TARGET / 'tricks.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
