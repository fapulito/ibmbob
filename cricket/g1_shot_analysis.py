#!/usr/bin/env python3
"""
G1 shot-selection analysis — Session 4
=======================================
Runs `select_delivery_shot` on ≥100 stratified val clips WITHOUT the 55% frame
shortcut. Produces:
  - cricket/data-training/balltrack/g1_results.jsonl  (machine-readable per-clip data)
  - cricket/data-training/balltrack/g1-report.md      (human-readable report)
  - cricket/data-training/balltrack/g1-frames/<hash>/ (3 JPEG frames for ≥10 clips)

R4 acceptance:
  • per-clip: chosen window (frame range + % of clip), features, confidence
  • 3 saved frames/clip for ≥10 clips
  • base rate: how many windows fall outside 50–65%

Usage:
    python cricket/g1_shot_analysis.py [--clips 120] [--save-frames-count 10]

The script is read-only w.r.t. the predictor — no integration, no chain length claim.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Paths (repo-relative)
# ---------------------------------------------------------------------------
_HERE        = Path(__file__).parent
_REPO        = _HERE.parent
_TURBOVISION = _HERE / "turbovision"
_PRIVATE_TRACK = _TURBOVISION / "scorevision" / "miner" / "private_track"

_MANIFEST    = _REPO / "data" / "videos_sample" / "manifest.jsonl"
_SAMPLE_DIR  = _REPO / "data" / "videos_sample"
_SPLIT_FILE  = _REPO / "data" / "split.json"
_OUT_DIR     = _HERE / "data-training" / "balltrack"
_FRAMES_DIR  = _OUT_DIR / "g1-frames"
_JSONL_OUT   = _OUT_DIR / "g1_results.jsonl"
_MD_OUT      = _OUT_DIR / "g1-report.md"

# ---------------------------------------------------------------------------
# Import shot_selection from the private_track tree (no install needed)
# ---------------------------------------------------------------------------
import importlib, types as _types

def _import_from_file(mod_name: str, filepath: Path):
    spec = importlib.util.spec_from_file_location(mod_name, filepath)
    m    = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = m
    spec.loader.exec_module(m)
    return m

# Stub out the logger used by the modules so it doesn't need the custom handler
import logging
logging.basicConfig(level=logging.WARNING)

# Modules needed transitively
_log_stub = _types.ModuleType("scorevision.miner.private_track.logging")
_log_stub.logger = logging.getLogger("cricket.pt")
sys.modules["scorevision.miner.private_track.logging"] = _log_stub

ph_mod = _import_from_file(
    "scorevision.miner.private_track.pitch_homography",
    _PRIVATE_TRACK / "pitch_homography.py",
)
ss_mod = _import_from_file(
    "scorevision.miner.private_track.shot_selection",
    _PRIVATE_TRACK / "shot_selection.py",
)

select_delivery_shot = ss_mod.select_delivery_shot
segment_shots        = ss_mod.segment_shots


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_manifest(n_per_band: int, split_filter=None):
    """
    Load up to n_per_band clips per kph band from the stratified manifest.
    Only include clips that have a file on disk.
    """
    split = {}
    if split_filter and _SPLIT_FILE.exists():
        split = json.loads(_SPLIT_FILE.read_text())

    rows = [json.loads(l) for l in _MANIFEST.read_text().splitlines() if l.strip()]
    band_counts: dict[str, int] = {}
    selected = []
    for row in rows:
        # Optional: filter to a specific split
        if split_filter and split.get(row["challenge_path"]) != split_filter:
            continue
        band = row["band"]
        if band_counts.get(band, 0) >= n_per_band:
            continue
        name = row["video_url"].rstrip("/").split("/")[-1]
        path = _SAMPLE_DIR / name
        if not path.exists() or path.stat().st_size < 100_000:
            continue
        band_counts[band] = band_counts.get(band, 0) + 1
        selected.append({**row, "local_path": str(path), "hash": Path(name).stem})
    return selected


def _save_frames(video_path: Path, frame_indices: list[int], out_dir: Path) -> list[str]:
    """Save specific frames as JPEG; return list of saved filenames.

    Falls back to frame_index-1 if the exact frame is unreadable (common at
    the very last frame of a clip where VideoCapture.read() returns False).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(video_path))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    saved = []
    for idx in frame_indices:
        for candidate in [idx, max(0, idx - 1), max(0, idx - 2)]:
            cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, candidate))
            ok, frame = cap.read()
            if ok:
                fname = f"frame_{candidate:05d}.jpg"
                cv2.imwrite(str(out_dir / fname), frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                saved.append(fname)
                break
    cap.release()
    return saved


def _analyse_clip(row: dict, save_frames_dir: Path | None = None) -> dict:
    """Run shot selection on one clip and return a result dict."""
    video_path = Path(row["local_path"])
    h = row["hash"]

    t0 = time.perf_counter()
    try:
        cap = cv2.VideoCapture(str(video_path))
        fps         = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        cap.release()

        selection = select_delivery_shot(video_path, total_frames=total_frames)
        elapsed   = time.perf_counter() - t0

        n_shots = len(selection.shots)
        best    = selection.best()

        if best is not None:
            start_pct  = 100.0 * best.start_frame / total_frames
            end_pct    = 100.0 * best.end_frame   / total_frames
            mid_pct    = 100.0 * best.mid_frame   / total_frames
            nbars      = best.wicket.get("nbars", 0)   if best.wicket else 0
            corroborated = best.wicket.get("corroborated", False) if best.wicket else False
            px_lat     = float(best.wicket.get("px_lat", 0.0))   if best.wicket else 0.0

            # Confidence: corroborated(bool) + nbars normalised
            confidence = round(
                (1.0 if corroborated else 0.5) * min(1.0, nbars / 3.0),
                3,
            )

            outside_50_65 = (best.end_frame / total_frames < 0.50 or
                             best.start_frame / total_frames > 0.65)

            # Three sample frames: start, mid, end of the chosen window
            sample_frames = [
                best.start_frame,
                best.mid_frame,
                best.end_frame,
            ]

            # Features that drove the selection
            features = (
                f"nbars={nbars} corroborated={corroborated} "
                f"px_lat={px_lat:.1f}"
            )
        else:
            start_pct = end_pct = mid_pct = 0.0
            nbars = 0; corroborated = False; px_lat = 0.0; confidence = 0.0
            outside_50_65 = True  # no window found → can't be in 50-65%
            sample_frames = []
            features = "no_wicket_found"

        # Shot table for diagnostics
        shot_table = []
        for s in selection.shots:
            shot_table.append({
                "idx":   s.index,
                "start": s.start_frame,
                "end":   s.end_frame,
                "start_pct": round(100.0 * s.start_frame / total_frames, 1),
                "end_pct":   round(100.0 * s.end_frame   / total_frames, 1),
                "found": s.found,
                "nbars": s.wicket.get("nbars", 0) if s.wicket else 0,
            })

        saved_frames: list[str] = []
        if save_frames_dir is not None and sample_frames:
            saved_frames = _save_frames(
                video_path, sample_frames,
                save_frames_dir / h,
            )

        return {
            "hash":          h,
            "band":          row["band"],
            "challenge_path": row["challenge_path"],
            "total_frames":  total_frames,
            "fps":           round(fps, 1),
            "duration_s":    round(total_frames / fps, 1),
            "n_shots":       n_shots,
            "found":         best is not None,
            "start_frame":   best.start_frame if best else None,
            "end_frame":     best.end_frame   if best else None,
            "mid_frame":     best.mid_frame   if best else None,
            "start_pct":     round(start_pct, 1),
            "end_pct":       round(end_pct, 1),
            "mid_pct":       round(mid_pct, 1),
            "nbars":         nbars,
            "corroborated":  corroborated,
            "px_lat":        round(px_lat, 1),
            "confidence":    confidence,
            "features":      features,
            "outside_50_65": outside_50_65,
            "elapsed_s":     round(elapsed, 2),
            "shot_table":    shot_table,
            "saved_frames":  saved_frames,
        }

    except Exception as exc:
        elapsed = time.perf_counter() - t0
        return {
            "hash":          h,
            "band":          row.get("band", "?"),
            "challenge_path": row.get("challenge_path", "?"),
            "error":         str(exc),
            "found":         False,
            "outside_50_65": True,
            "elapsed_s":     round(elapsed, 2),
        }


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def _write_report(results: list[dict], out_path: Path) -> None:
    n_total      = len(results)
    n_found      = sum(1 for r in results if r.get("found"))
    n_outside    = sum(1 for r in results if r.get("outside_50_65"))
    n_errors     = sum(1 for r in results if "error" in r)
    n_in_50_65   = sum(1 for r in results if r.get("found") and not r.get("outside_50_65"))

    lines = []
    lines.append("# G1 Shot-Selection Analysis Report (approx-tol, Session 4)")
    lines.append("")
    lines.append("Generated by `cricket/g1_shot_analysis.py`.  ")
    lines.append("Selection method: `select_delivery_shot` (histogram cut-detection + "
                 "PitchHomography wicket-bar scoring on each shot's midpoint).  ")
    lines.append("The 50–65% assumption is **not used**. "
                 "The 55% frame shortcut is forbidden by R4 and is absent from this script.")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"| metric | value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| clips processed | {n_total} |")
    lines.append(f"| delivery window found | {n_found} ({100*n_found/n_total:.1f}%) |")
    lines.append(f"| errors / unreadable | {n_errors} |")
    lines.append(f"| window **outside** 50–65% | {n_outside} of {n_total} "
                 f"({100*n_outside/n_total:.1f}%) |")
    lines.append(f"| window **inside** 50–65% | {n_in_50_65} of {n_total} "
                 f"({100*n_in_50_65/n_total:.1f}%) |")
    lines.append("")
    lines.append(f"> **G1 base rate: {n_outside}/{n_total} clips "
                 f"({100*n_outside/n_total:.1f}%) have their chosen delivery window "
                 f"outside the 50–65% band.**")
    lines.append("")

    # Band breakdown
    from collections import defaultdict
    band_stats: dict[str, dict] = defaultdict(lambda: {"n":0,"found":0,"outside":0})
    for r in results:
        b = r.get("band","?")
        band_stats[b]["n"] += 1
        if r.get("found"): band_stats[b]["found"] += 1
        if r.get("outside_50_65"): band_stats[b]["outside"] += 1

    lines.append("## Per-band summary")
    lines.append("")
    lines.append("| band | n | found | outside 50-65% |")
    lines.append("|------|---|-------|----------------|")
    for band in sorted(band_stats):
        s = band_stats[band]
        lines.append(f"| {band} | {s['n']} | {s['found']} | {s['outside']} |")
    lines.append("")

    # Per-clip table
    lines.append("## Per-clip results")
    lines.append("")
    lines.append("Columns: `hash` (first 8), `band`, `frames`, `n_shots`, "
                 "`window [start–end]`, `pct [start–end]`, `mid_pct`, "
                 "`nbars`, `corr`, `confidence`, `outside?`, `features`, `elapsed`")
    lines.append("")
    lines.append("| hash | band | frames | shots | window | pct | mid% | nbars | corr | conf | out? | features | s |")
    lines.append("|------|------|--------|-------|--------|-----|------|-------|------|------|------|----------|---|")

    for r in results:
        h8 = r["hash"][:8]
        if "error" in r:
            lines.append(f"| {h8} | {r.get('band','?')} | — | — | ERROR | — | — | — | — | — | — | {r['error'][:40]} | {r['elapsed_s']} |")
            continue
        win = f"{r.get('start_frame','?')}–{r.get('end_frame','?')}" if r.get("found") else "none"
        pct = (f"{r.get('start_pct','?')}–{r.get('end_pct','?')}%" if r.get("found") else "—")
        mid = f"{r.get('mid_pct','?')}%" if r.get("found") else "—"
        out = "**YES**" if r.get("outside_50_65") else "no"
        feat = r.get("features","?")[:32]
        lines.append(
            f"| {h8} | {r.get('band','?')} | {r.get('total_frames','?')} "
            f"| {r.get('n_shots','?')} | {win} | {pct} | {mid} "
            f"| {r.get('nbars','?')} | {r.get('corroborated','?')} "
            f"| {r.get('confidence','?')} | {out} | {feat} | {r.get('elapsed_s','?')} |"
        )
    lines.append("")

    # Shot breakdown for clips with saved frames
    saved_clips = [r for r in results if r.get("saved_frames")]
    if saved_clips:
        lines.append(f"## Spot-check clips ({len(saved_clips)} clips with saved frames)")
        lines.append("")
        lines.append("For each clip: shot table and saved frame filenames.")
        lines.append("")
        for r in saved_clips:
            h8 = r["hash"][:8]
            lines.append(f"### {h8} (band={r['band']}, kph-GT implied)")
            lines.append("")
            lines.append(f"- **Video**: {r['total_frames']} frames @ {r['fps']} fps "
                         f"({r['duration_s']} s)")
            lines.append(f"- **Chosen window**: frames {r['start_frame']}–{r['end_frame']} "
                         f"({r['start_pct']}–{r['end_pct']}%, mid={r['mid_pct']}%)")
            lines.append(f"- **Features**: {r['features']}")
            lines.append(f"- **Confidence**: {r['confidence']}")
            lines.append(f"- **Outside 50–65%**: {r['outside_50_65']}")
            lines.append(f"- **Shot segmentation** ({r['n_shots']} shots):")
            lines.append("")
            lines.append("  | shot | start | end | start% | end% | found | nbars |")
            lines.append("  |------|-------|-----|--------|------|-------|-------|")
            for s in r.get("shot_table", []):
                lines.append(f"  | {s['idx']} | {s['start']} | {s['end']} "
                              f"| {s['start_pct']} | {s['end_pct']} "
                              f"| {s['found']} | {s['nbars']} |")
            lines.append("")
            lines.append(f"- **Saved frames** (in `g1-frames/{r['hash']}/`):")
            for f in r.get("saved_frames", []):
                lines.append(f"  - `{f}`")
            lines.append("")

    lines.append("---")
    lines.append("*All scores labelled approx-tol. No predictor integration in this session.*")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report written → {out_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="G1 shot-selection analysis")
    parser.add_argument("--clips",        type=int, default=120,
                        help="Target clips per kph band (default 120 → ~600 total available, we pick 24/band)")
    parser.add_argument("--per-band",     type=int, default=24,
                        help="Max clips per kph band (default 24, 5 bands → 120 clips)")
    parser.add_argument("--save-frames-count", type=int, default=10,
                        help="Save frames for first N clips that find a window (default 10)")
    parser.add_argument("--split",        type=str, default=None,
                        help="Filter to a split (train|val|test|None=all)")
    args = parser.parse_args()

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    _FRAMES_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Loading manifest (per_band={args.per_band}, split={args.split})…")
    clips = _load_manifest(n_per_band=args.per_band, split_filter=args.split)
    print(f"Loaded {len(clips)} clips")

    if len(clips) < 100:
        print(f"WARNING: only {len(clips)} clips found (need ≥100). "
              f"Check that data/videos_sample/ is populated.")

    results: list[dict] = []
    frames_saved_count  = 0
    t_total = time.perf_counter()

    for i, row in enumerate(clips, 1):
        save_dir = None
        if frames_saved_count < args.save_frames_count:
            save_dir = _FRAMES_DIR

        print(f"[{i:3d}/{len(clips)}] {row['hash'][:8]}  band={row['band']}", end="  ", flush=True)
        result = _analyse_clip(row, save_frames_dir=save_dir)

        if result.get("saved_frames"):
            frames_saved_count += 1

        status = "FOUND" if result.get("found") else ("ERROR" if "error" in result else "NOFIND")
        out    = " OUT" if result.get("outside_50_65") else ""
        print(f"{status}{out}  "
              f"window={result.get('start_pct','?')}-{result.get('end_pct','?')}%  "
              f"nbars={result.get('nbars','?')}  "
              f"{result.get('elapsed_s','?')}s")

        results.append(result)

        # Rolling write to JSONL (crash-safe)
        with _JSONL_OUT.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(result) + "\n")

    elapsed_total = time.perf_counter() - t_total
    n_found    = sum(1 for r in results if r.get("found"))
    n_outside  = sum(1 for r in results if r.get("outside_50_65"))
    print(f"\n=== Done in {elapsed_total:.1f}s ===")
    print(f"Clips: {len(results)}  Found: {n_found}  Outside 50-65%: {n_outside}/{len(results)}")

    _write_report(results, _MD_OUT)
    print(f"JSONL data → {_JSONL_OUT}")


if __name__ == "__main__":
    # Clear existing JSONL so we don't append to a stale run
    _JSONL_OUT.unlink(missing_ok=True)
    main()
