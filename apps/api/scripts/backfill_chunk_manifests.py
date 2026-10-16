#!/usr/bin/env python3
"""Explicit maintenance command; default is dry-run, --apply saves once."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.chunk_manifest_backfill import backfill_chunk_manifests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="persist staged manifests in one state snapshot")
    args = parser.parse_args()
    report = backfill_chunk_manifests(apply=args.apply)
    report["mode"] = "apply" if args.apply else "dry_run"
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
