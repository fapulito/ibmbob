#!/usr/bin/env python3
"""Pull ALL ground-truth label JSONs for the Score cricket BallTrack training set.

Labels only — no videos. Resumable: skips challenges already saved.
v2: thread-local sessions (connection reuse), 32 workers, 3 retries with backoff.
Output: data/labels.jsonl (one row per challenge) + data/index.json (raw copy).
Origin: https://manako.scoredata.me/train/index.json  (13,824 entries, checked 2026-10-28)
"""
import json, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import requests

ORIGIN = "https://manako.scoredata.me/"
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "labels.jsonl"
RAW_INDEX = ROOT / "data" / "index.json"
_local = threading.local()

def _session():
    if not hasattr(_local, "s"):
        _local.s = requests.Session()
    return _local.s

def fetch(path):
    last = None
    for attempt in range(3):
        try:
            r = _session().get(f"{ORIGIN}{path}", timeout=20)
            r.raise_for_status()
            return path, r.json()
        except Exception as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise last

def main():
    ROOT.joinpath("data").mkdir(parents=True, exist_ok=True)
    index = requests.get(f"{ORIGIN}train/index.json", timeout=30).json()
    RAW_INDEX.write_text(json.dumps(index))
    done = set()
    if OUT.exists():
        for line in OUT.read_text().splitlines():
            if line.strip():
                done.add(json.loads(line)["challenge_path"])
    todo = [p for p in index if p not in done]
    print(f"index={len(index)} already={len(done)} to_fetch={len(todo)}", flush=True)
    ok = fail = 0
    with OUT.open("a") as fh, ThreadPoolExecutor(max_workers=32) as ex:
        futures = {ex.submit(fetch, p): p for p in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            p = futures[fut]
            try:
                path, chal = fut.result()
                fh.write(json.dumps({"challenge_path": path, "video_url": chal.get("video_url"),
                                     "groundtruth": chal.get("groundtruth")}) + "\n")
                ok += 1
            except Exception as e:
                fail += 1
                print(f"FAIL {p}: {e}", flush=True)
            if i % 200 == 0:
                fh.flush()
                print(f"{i}/{len(todo)} ok={ok} fail={fail}", flush=True)
    print(f"DONE ok={ok} fail={fail} total_file={sum(1 for _ in OUT.open())}", flush=True)

if __name__ == "__main__":
    main()
