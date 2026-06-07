#!/usr/bin/env python3
"""
Demo seed: trigger a scan against the local repo and watch sessions spawn.

Useful when you want to record a Loom and don't want to wait for the
nightly cron. Calls the same /scan/run endpoint the GH Action calls.

Usage:
    python scripts/demo_seed.py [--url http://localhost:8000]
"""
from __future__ import annotations

import argparse
import json
import sys
import time

import httpx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--watch", action="store_true",
                        help="Tail sessions for 60s after triggering")
    args = parser.parse_args()

    print(f"Triggering scan at {args.url}/scan/run ...")
    r = httpx.post(f"{args.url}/scan/run", timeout=10.0)
    r.raise_for_status()
    print(json.dumps(r.json(), indent=2))

    if not args.watch:
        return 0

    print("\nWatching sessions for 60 seconds...\n")
    for _ in range(12):
        time.sleep(5)
        sessions = httpx.get(f"{args.url}/sessions", timeout=10.0).json()
        print(f"[{time.strftime('%H:%M:%S')}] {len(sessions)} sessions: "
              f"{', '.join(s['status'] for s in sessions[:10])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
