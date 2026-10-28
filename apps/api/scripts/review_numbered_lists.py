"""Read-only offline review: python scripts/review_numbered_lists.py chunks.json.

No application startup, credentials, providers, database or file writes.
"""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.numbered_list_review import review_chunk_pair


def main():
    chunks = json.loads(Path(sys.argv[1]).read_text())
    signals = []
    for index, chunk in enumerate(chunks):
        following = chunks[index + 1] if index + 1 < len(chunks) else None
        signals.extend(review_chunk_pair(chunk, following))
    print(json.dumps({'detector': 'numbered-list-review-v2', 'review_only': True,
                      'signals': signals}, indent=2))


if __name__ == '__main__':
    main()
