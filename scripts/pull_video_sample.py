#!/usr/bin/env python3
"""Pull a stratified sample of training VIDEOS (the full set is ~130-180 GB and
does not fit on this VM — 49 GB free at check). Stratified by true kph band so the
sample covers pace/medium/spin regimes in equal numbers, unlike the raw distribution.
Resumable: skips files already on disk with the right size (>100 KB).
Output: data/videos_sample/<hash>.mp4 + data/videos_sample/manifest.jsonl
"""
import json, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
ROWS = [json.loads(l) for l in (ROOT/"data"/"labels.jsonl").open() if l.strip()]
OUTDIR = ROOT/"data"/"videos_sample"
PER_BAND = int(sys.argv[1]) if len(sys.argv) > 1 else 120
BANDS = [("<80",0,80),("80-100",80,100),("100-120",100,120),("120-135",120,135),(">=135",135,999)]

def band_of(kph):
    for name, lo, hi in BANDS:
        if kph is not None and lo <= kph < hi:
            return name
    return None

def main():
    OUTDIR.mkdir(parents=True, exist_ok=True)
    picked, counts = [], {}
    for r in ROWS:
        b = band_of(r["groundtruth"].get("kph"))
        if b and counts.get(b, 0) < PER_BAND:
            counts[b] = counts.get(b, 0) + 1
            picked.append((b, r))
    print(f"picked={len(picked)} by band={counts}", flush=True)
    (OUTDIR/"manifest.jsonl").write_text("\n".join(
        json.dumps({"band": b, "challenge_path": r["challenge_path"], "video_url": r["video_url"],
                    "groundtruth": r["groundtruth"]}) for b, r in picked) + "\n")
    def dl(item):
        b, r = item
        name = r["video_url"].rstrip("/").split("/")[-1]
        dest = OUTDIR/name
        if dest.exists() and dest.stat().st_size > 100_000:
            return ("skip", name, dest.stat().st_size)
        tmp = dest.with_suffix(".part")
        last = None
        for attempt in range(4):
            try:
                with requests.get(r["video_url"], stream=True, timeout=120) as resp:
                    resp.raise_for_status()
                    with tmp.open("wb") as fh:
                        for chunk in resp.iter_content(1 << 20):
                            fh.write(chunk)
                tmp.rename(dest)
                return ("ok", name, dest.stat().st_size)
            except Exception as e:
                last = e
                tmp.unlink(missing_ok=True)
                import time as _t; _t.sleep(2 * (attempt + 1))
        raise last
    ok = skip = fail = total = 0
    with ThreadPoolExecutor(max_workers=2) as ex:
        for i, fut in enumerate(as_completed([ex.submit(dl, it) for it in picked]), 1):
            try:
                status, name, size = fut.result()
                total += size if status == "ok" else 0
                ok += status == "ok"; skip += status == "skip"
            except Exception as e:
                fail += 1; print(f"FAIL {e}", flush=True)
            if i % 100 == 0:
                print(f"{i}/{len(picked)} ok={ok} skip={skip} fail={fail} new_bytes={total/1e9:.2f}GB", flush=True)
    print(f"DONE ok={ok} skip={skip} fail={fail}", flush=True)

if __name__ == "__main__":
    main()
