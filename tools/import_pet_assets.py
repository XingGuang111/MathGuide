"""Fetch the pinned dsh-pet clips used by MathGuide; see ASSET-NOTICE.md.

Run manually to refresh assets; the application never needs GitHub at runtime.
"""
import argparse
import base64
import hashlib
import json
import time
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "web" / "assets" / "pet"
COMMIT = "ad9e2cb50348280634021e0699482f43b56ce1ca"
BASE = f"https://raw.githubusercontent.com/PC2005-cloud/dsh-pet/{COMMIT}"
CLIPS = {
    "idle": "待机呼吸休闲",
    "touch": "点击回应-开心跃动",
    "wave": "点击回应-元气挥手",
    "drag": "被鼠标拖拽悬空反馈",
    "eat": "大口吃零食",
    "play": "三球抛接",
    "think": "工作状态-思考冒泡",
    "celebrate": "工作状态-雀跃庆祝",
    "sleep": "原地小憩沉眠",
}


def fetch(path, target, from_api=False):
    encoded = urllib.parse.quote(path, safe='/')
    api = f'https://api.github.com/repos/PC2005-cloud/dsh-pet/contents/{encoded}?ref={COMMIT}'
    urls = [api] if from_api else [BASE + '/' + encoded, api,
            f'https://cdn.jsdelivr.net/gh/PC2005-cloud/dsh-pet@{COMMIT}/' + encoded]
    for attempt in range(3):
        try:
            url = urls[attempt % len(urls)]
            request = urllib.request.Request(url, headers={"User-Agent": "MathGuide-asset-import"})
            with urllib.request.urlopen(request, timeout=20) as response:
                data = response.read()
            if url == api:
                payload = json.loads(data)
                if payload.get('encoding') != 'base64':
                    raise ValueError('GitHub did not return a base64 asset')
                data = base64.b64decode(payload['content'])
            target.write_bytes(data)
            return data
        except OSError:
            if attempt == 2:
                raise
            time.sleep(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-git", type=Path, help="Use an already downloaded upstream checkout")
    parser.add_argument("--force", action="store_true", help="Download even already verified local clips")
    parser.add_argument("--from-api", action="store_true", help="Use GitHub contents API for download")
    args = parser.parse_args()

    def download(path, target):
        if args.from_git:
            data = subprocess.check_output(["git", "-C", str(args.from_git), "show", f"{COMMIT}:{path}"])
            target.write_bytes(data)
            return data
        return fetch(path, target, args.from_api)

    TARGET.mkdir(parents=True, exist_ok=True)
    previous_path = TARGET / 'manifest.json'
    previous = json.loads(previous_path.read_text(encoding='utf-8')) if previous_path.exists() else {}
    manifest = {"repository": "https://github.com/PC2005-cloud/dsh-pet", "commit": COMMIT,
                "license": "Non-commercial assets; see ASSET-NOTICE.md", "code_license": "MIT",
                "asset_notice": "ASSET-NOTICE.md", "character": "whale-tail maid", "clips": {}}
    if args.force or not (TARGET / 'LICENSE.txt').exists():
        download("LICENSE", TARGET / "LICENSE.txt")
    for name, source in CLIPS.items():
        target = TARGET / f"{name}.webm"
        existing = previous.get('clips', {}).get(name, {})
        data = target.read_bytes() if target.exists() else b''
        if (args.force or previous.get('commit') != COMMIT or existing.get('source') != source + '.webm'
                or hashlib.sha256(data).hexdigest() != existing.get('sha256')):
            data = download(f"dsh-pet/assets/webm/{source}.webm", target)
        if not data.startswith(bytes.fromhex("1a45dfa3")):
            raise ValueError(f"Invalid WebM: {name}")
        manifest["clips"][name] = {"file": target.name, "source": source + ".webm",
                                    "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
        print(f"{name}: {len(data)} bytes", flush=True)
    (TARGET / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
