"""Run the real MathGuide app with an isolated product-demo database.

No model, OCR, or product responses are mocked. The regular learning database
is not changed. Restart with the same data directory to resume the demo.
"""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--data-dir', type=Path,
                        default=ROOT / 'output' / 'product-demo-2026-11-02' / 'runtime')
    args = parser.parse_args()
    directory = args.data_dir.resolve()
    directory.mkdir(parents=True, exist_ok=True)

    import config
    config.DB_PATH = str(directory / 'product-demo.db')
    import uvicorn
    import web_app

    print(f'MathGuide product demo: http://127.0.0.1:{args.port}', flush=True)
    print(f'Isolated database: {config.DB_PATH}', flush=True)
    uvicorn.run(web_app.app, host=args.host, port=args.port)


if __name__ == '__main__':
    main()
