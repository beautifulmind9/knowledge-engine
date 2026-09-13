"""Local single-owner launcher. Environment variables override .env values."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps' / 'api'))


def main():
    from dotenv import load_dotenv
    import uvicorn
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    load_dotenv(ROOT / '.env', override=False)
    uvicorn.run('app.main:app', host='127.0.0.1', port=args.port, workers=1)


if __name__ == '__main__':
    main()
