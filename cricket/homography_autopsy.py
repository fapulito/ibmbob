#!/usr/bin/env python3
"""
homography_autopsy.py — Session 6 homography validity autopsy.

Runs the instrumented PitchHomography (HOMOGRAPHY_DEBUG=1) over at least 50
VAL-split clips that exist on disk in data/videos_sample/.

Clip selection:
  - VAL split only (data/split.json).
  - Video must exist in data/videos_sample/ and be > 100 KB.
  - Stratified by kph band (up to N_PER_BAND per band, default=13 per band
    across 5 bands = 65 max; all available VAL clips used if fewer exist).
  - The calibration frame is chosen via Session 4 shot-selection (same method
    as Session 5), so results are directly comparable to Session 5 findings.

Outputs:
  - cricket/data-training/balltrack/autopsy_results.jsonl (machine-readable)
  - cricket/data-training/balltrack/homography-frames/<reason>/<hash>_frame.jpg
    (for the top-3 reason codes, at least 5 examples each)
  - cricket/data-training/balltrack/homography-autopsy.md (human-readable report)

Usage:
    python cricket/homography_autopsy.py
    python cricket/homography_autopsy.py --clips 80
"""

from __future__ import annotations

import argparse
import importlib
import json
import logging
import os
import sys
import time
import types as _types
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_HERE          = Path(__file__).parent
_REPO          = _HERE.parent
_TURBOVISION   = _HERE / "turbovision"
_PRIVATE_TRACK = _TURBOVISION / "scorevision" / "miner" / "private_track"

_LABELS_FILE   = _HERE / "data-training" / "balltrack" / "labels.jsonl"
_SPLIT_FILE    = _HERE / "data-training" / "balltrack" / "split.json"
_MANIFEST_FILE = _REPO / "data" / "videos_sample" / "manifest.jsonl"
_SAMPLE_DIR    = _REPO / "data" / "videos_sample"
_OUT_DIR       = _HERE / "data-training" / "balltrack"
_FRAMES_DIR    = _OUT_DIR / "homography-frames"
_JSONL_OUT     = _OUT_DIR / "autopsy_results.jsonl"
_REPORT_PATH   = _OUT_DIR / "homography-autopsy.md"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.WARNING,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("homography_autopsy")

# ---------------------------------------------------------------------------
# Import private_track modules
# ---------------------------------------------------------------------------
def _import_from_file(mod_name, filepath):
    spec = importlib.util.spec_from_file_location(mod_name, filepath)
    m    = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = m
    spec.loader.exec_module(m)
    return m

_log_stub        = _types.ModuleType("scorevision.miner.private_track.logging")
_log_stub.logger = logging.getLogger("pt_stub")
sys.modules["scorevision.miner.private_track.logging"] = _log_stub

ph_mod  = _import_from_file("scorevision.miner.private_track.pitch_homography",
                             _PRIVATE_TRACK / "pitch_homography.py")
ss_mod  = _import_from_file("scorevision.miner.private_track.shot_selection",
                             _PRIVATE_TRACK / "shot_selection.py")

PitchHomography      = ph_mod.PitchHomography
select_delivery_shot = ss_mod.select_delivery_shot

# All reason-code constants exported from pitch_homography
REASON_ENDON_NO_WICKET         = ph_mod.REASON_ENDON_NO_WICKET
REASON_ENDON_NO_BARS           = ph_mod.REASON_ENDON_NO_BARS
REASON_ENDON_BASE_ROW_OOB      = ph_mod.REASON_ENDON_BASE_ROW_OOB
REASON_ENDON_CENTRE_OFF        = ph_mod.REASON_ENDON_CENTRE_OFF
REASON_ENDON_PX_LAT_OOB        = ph_mod.REASON_ENDON_PX_LAT_OOB
REASON_ENDON_NO_DEPTH_LANDMARK = ph_mod.REASON_ENDON_NO_DEPTH_LANDMARK
REASON_SIDEON_NO_LINES         = ph_mod.REASON_SIDEON_NO_LINES
REASON_SIDEON_FEW_VLINES       = ph_mod.REASON_SIDEON_FEW_VLINES
REASON_SIDEON_FEW_CLUSTERS     = ph_mod.REASON_SIDEON_FEW_CLUSTERS
REASON_SIDEON_SPAN_SMALL       = ph_mod.REASON_SIDEON_SPAN_SMALL

ALL_REASON_CODES = [
    REASON_ENDON_NO_WICKET, REASON_ENDON_NO_BARS,
    REASON_ENDON_BASE_ROW_OOB, REASON_ENDON_CENTRE_OFF,
    REASON_ENDON_PX_LAT_OOB, REASON_ENDON_NO_DEPTH_LANDMARK,
    REASON_SIDEON_NO_LINES, REASON_SIDEON_FEW_VLINES,
    REASON_SIDEON_FEW_CLUSTERS, REASON_SIDEON_SPAN_SMALL,
]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def load_split():
    with open(_SPLIT_FILE) as f:
        return json.load(f)


def load_labels():
    labels = {}
    with open(_LABELS_FILE) as f:
        for line in f:
            rec = json.loads(line)
            labels[rec["challenge_path"]] = rec
    return labels


def load_manifest():
    rows = []
    with open(_MANIFEST_FILE) as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


# ---------------------------------------------------------------------------
# Clip selection
# ---------------------------------------------------------------------------
def select_val_clips(n_per_band: int = 13) -> list[dict]:
    """
    Return up to n_per_band VAL clips per kph band that have video on disk.
    Selection order is manifest order (stable, reproducible).
    """
    split  = load_split()
    labels = load_labels()

    band_counts: dict[str, int] = {}
    selected = []
    for row in load_manifest():
        cp = row["challenge_path"]
        if split.get(cp) != "val":
            continue
        if cp not in labels:
            continue
        band = row.get("band", "unknown")
        url  = row["video_url"]
        name = url.rstrip("/").split("/")[-1]
        path = _SAMPLE_DIR / name
        if not path.exists() or path.stat().st_size < 100_000:
            continue
        if band_counts.get(band, 0) >= n_per_band:
            continue
        band_counts[band] = band_counts.get(band, 0) + 1
        selected.append({
            "challenge_path": cp,
            "video_path":     str(path),
            "band":           band,
            "hash":           Path(name).stem,
            "groundtruth":    labels[cp]["groundtruth"],
        })
    return selected


# ---------------------------------------------------------------------------
# Per-clip analysis
# ---------------------------------------------------------------------------
def analyse_clip(row: dict) -> dict:
    """
    Run shot-selection + PitchHomography(HOMOGRAPHY_DEBUG=1) on one clip.
    Returns a result dict with valid, camera_type, debug_reasons, debug_values,
    anchor_calibrated, depth_landmark, elapsed_s, delivery_frame, frame_shape,
    error.
    """
    vp  = Path(row["video_path"])
    t0  = time.perf_counter()
    err = None
    result = {
        "challenge_path":  row["challenge_path"],
        "hash":            row["hash"],
        "band":            row["band"],
        "valid":           False,
        "camera_type":     "unknown",
        "anchor_calibrated": False,
        "depth_landmark":  "unknown",
        "debug_reasons":   [],
        "debug_values":    {},
        "delivery_frame":  -1,
        "frame_shape":     None,
        "ref_frame_path":  None,
        "elapsed_s":       0.0,
        "error":           None,
    }

    try:
        cap = cv2.VideoCapture(str(vp))
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        # Shot selection (Session 4 / Session 5 method)
        selection = select_delivery_shot(vp, total_frames=frame_count)
        best_shot = selection.best()
        delivery_frame = best_shot.mid_frame if best_shot is not None else int(frame_count * 0.55)

        cap.set(cv2.CAP_PROP_POS_FRAMES, delivery_frame)
        ret, ref_frame = cap.read()
        cap.release()

        if not ret or ref_frame is None:
            result["error"] = "frame_read_failed"
            return result

        result["delivery_frame"] = delivery_frame
        result["frame_shape"]    = list(ref_frame.shape[:2])  # [h, w]

        # Run homography with debug on
        os.environ["HOMOGRAPHY_DEBUG"] = "1"
        hom = PitchHomography(ref_frame)
        del os.environ["HOMOGRAPHY_DEBUG"]

        result["valid"]            = hom.valid
        result["camera_type"]      = hom.camera_type
        result["anchor_calibrated"] = hom.anchor_calibrated
        result["depth_landmark"]   = hom.depth_landmark
        result["debug_reasons"]    = list(hom.debug_reasons)
        result["debug_values"]     = {k: (float(v) if isinstance(v, (int, float)) else v)
                                      for k, v in hom.debug_values.items()}

    except Exception as exc:
        os.environ.pop("HOMOGRAPHY_DEBUG", None)
        result["error"] = str(exc)

    result["elapsed_s"] = time.perf_counter() - t0
    return result


def save_frame(frame_path: Path, ref_frame_dir: Path, reason: str, hash_: str) -> str | None:
    """Save the reference frame under homography-frames/<reason>/."""
    out_dir = _FRAMES_DIR / reason
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{hash_}_frame.jpg"
    # ref_frame was not saved during analysis; we need the video path
    return str(out_path)


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------
def build_report(results: list[dict], top3_examples: dict) -> str:
    lines = []
    n = len(results)
    n_valid = sum(1 for r in results if r["valid"])
    n_invalid = n - n_valid

    # Reason frequency
    reason_counts: Counter = Counter()
    for r in results:
        for rc in r["debug_reasons"]:
            reason_counts[rc] += 1

    top3 = [rc for rc, _ in reason_counts.most_common(3)]
    top1 = top3[0] if top3 else "none"
    top1_count = reason_counts.get(top1, 0)
    top1_pct   = top1_count / n * 100 if n else 0

    # Combination table
    combo_counts: Counter = Counter()
    for r in results:
        key = " + ".join(sorted(r["debug_reasons"])) if r["debug_reasons"] else "(none)"
        combo_counts[key] += 1

    lines.append("# Homography Validity Autopsy")
    lines.append("")
    lines.append(f"**The most common failure reason is `{top1}`, "
                 f"occurring in {top1_count}/{n} clips ({top1_pct:.1f}%).**")
    lines.append("")
    lines.append(f"Generated by `cricket/homography_autopsy.py`.  ")
    lines.append(f"n = {n} VAL clips.  ")
    lines.append(f"Clip selection: stratified by kph band (up to 13 per band), "
                 f"manifest order, videos_sample/ only, no downloads.  ")
    lines.append(f"Calibration frame: Session 4 / Session 5 shot-selection method.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Overall validity")
    lines.append("")
    lines.append(f"| metric | value |")
    lines.append(f"|:-------|------:|")
    lines.append(f"| n clips | {n} |")
    lines.append(f"| valid=True | {n_valid} ({n_valid/n*100:.1f}%) |")
    lines.append(f"| valid=False | {n_invalid} ({n_invalid/n*100:.1f}%) |")

    cam_counts: Counter = Counter(r["camera_type"] for r in results)
    for ct, cnt in cam_counts.most_common():
        lines.append(f"| camera_type={ct} | {cnt} ({cnt/n*100:.1f}%) |")

    anchor_count = sum(1 for r in results if r.get("anchor_calibrated"))
    lines.append(f"| anchor_calibrated=True | {anchor_count} ({anchor_count/n*100:.1f}%) |")
    lines.append("")

    lines.append("## Reason-code frequency")
    lines.append("")
    lines.append("Each clip can fire multiple reason codes.  ")
    lines.append("A clip with valid=False fires at least one reason code.  ")
    lines.append("")
    lines.append("| reason code | n clips | % of all clips |")
    lines.append("|:------------|--------:|:--------------:|")
    for rc in ALL_REASON_CODES:
        cnt = reason_counts.get(rc, 0)
        lines.append(f"| `{rc}` | {cnt} | {cnt/n*100:.1f}% |")
    lines.append("")

    lines.append("## Reason combination table")
    lines.append("")
    lines.append("Each row is a unique combination of reason codes that fired together.  ")
    lines.append("")
    lines.append("| reason combination | n clips |")
    lines.append("|:-------------------|--------:|")
    for combo, cnt in combo_counts.most_common():
        lines.append(f"| `{combo}` | {cnt} |")
    total_combo = sum(combo_counts.values())
    lines.append(f"| **TOTAL** | **{total_combo}** |")
    lines.append("")
    lines.append(f"Sum = {total_combo} = n ({n}) -- consistent.")
    lines.append("")

    lines.append("## Top-3 reason codes: examples and classification")
    lines.append("")
    for rank, rc in enumerate(top3, 1):
        examples = top3_examples.get(rc, [])
        lines.append(f"### {rank}. `{rc}` ({reason_counts[rc]} clips, {reason_counts[rc]/n*100:.1f}%)")
        lines.append("")

        # Classification
        if rc == REASON_ENDON_NO_WICKET:
            lines.append("**Classification**: Detection failure + possible wrong frame.")
            lines.append("The `_detect_wicket_endon` scan found no group of thin vertical bars")
            lines.append("satisfying all six wicket checks simultaneously. Sub-reasons recorded")
            lines.append("alongside (`endon_no_bars`, `endon_base_row_oob`, `endon_centre_off`,")
            lines.append("`endon_px_lat_oob`) indicate whether the frame had no edges at all")
            lines.append("(no-pitch frame) or had edges that failed individual sub-checks")
            lines.append("(threshold too strict / wrong shot).")
        elif rc == REASON_ENDON_NO_DEPTH_LANDMARK:
            lines.append("**Classification**: Detection failure — specific sub-system.")
            lines.append("The batter's-end wicket WAS found (anchor_calibrated=True), but neither")
            lines.append("the bowler's-end wicket nor the popping crease could be located to")
            lines.append("provide an independent depth-axis measurement. This is the ONLY reason")
            lines.append("valid=False is set when the wicket itself is found; it is the depth-axis")
            lines.append("bottleneck for end-on clips.")
        elif rc == REASON_ENDON_BASE_ROW_OOB:
            lines.append("**Classification**: Threshold possibly too strict, or wrong frame.")
            lines.append("The tallest detected bar's base row falls outside")
            lines.append(f"[{ph_mod._WICKET_BASE_ROW_FRAC[0]:.3f}, {ph_mod._WICKET_BASE_ROW_FRAC[1]:.3f}] * frame_height.")
            lines.append("This can mean the delivery frame shows a wide-angle shot with stumps")
            lines.append("lower in the frame, or the threshold was calibrated on a narrow set.")
        elif rc == REASON_ENDON_CENTRE_OFF:
            lines.append("**Classification**: Threshold possibly too strict.")
            lines.append(f"The wicket centroid is more than {ph_mod._WICKET_MAX_CENTRE_OFF_FRAC:.2f} * w")
            lines.append("away from the frame centre. Could indicate off-centre framing")
            lines.append("or a wrong-camera frame.")
        elif rc == REASON_ENDON_PX_LAT_OOB:
            lines.append("**Classification**: Detection failure or resolution mismatch.")
            lines.append("The estimated transverse scale (px/m) is outside the plausible range")
            lines.append(f"[{ph_mod._WICKET_PX_LAT_FRAC_RANGE[0]:.3f}, {ph_mod._WICKET_PX_LAT_FRAC_RANGE[1]:.3f}] * w.")
        elif rc in (REASON_SIDEON_NO_LINES, REASON_SIDEON_FEW_VLINES,
                    REASON_SIDEON_FEW_CLUSTERS, REASON_SIDEON_SPAN_SMALL):
            lines.append("**Classification**: Detection failure (side-on path).")
            lines.append("These fire on side-on clips only. The Hough-line / cluster pipeline")
            lines.append("did not find two well-separated stump clusters.")
        else:
            lines.append("**Classification**: see reason code comment in pitch_homography.py.")
        lines.append("")

        if examples:
            lines.append("| hash | camera | valid | anchor | depth_lm | sub-check values |")
            lines.append("|:-----|:-------|:-----:|:------:|:---------|:-----------------|")
            for ex in examples[:5]:
                dv = ex["debug_values"]
                # Format the most relevant sub-check values
                vals = []
                for k, v in sorted(dv.items()):
                    if isinstance(v, float):
                        vals.append(f"{k}={v:.2f}")
                    else:
                        vals.append(f"{k}={v}")
                vals_str = "; ".join(vals[:8])  # cap at 8 to keep table readable
                frame_rel = f"homography-frames/{rc}/{ex['hash']}_frame.jpg"
                lines.append(f"| [{ex['hash'][:8]}]({frame_rel}) | {ex['camera_type']} | "
                             f"{ex['valid']} | {ex['anchor_calibrated']} | "
                             f"{ex['depth_landmark']} | {vals_str} |")
        else:
            lines.append("*(no examples captured)*")
        lines.append("")

    # valid=True clips
    valid_clips = [r for r in results if r["valid"]]
    lines.append("## valid=True clips")
    lines.append("")
    if valid_clips:
        lines.append(f"{len(valid_clips)} clip(s) achieved valid=True:")
        lines.append("")
        lines.append("| hash | camera | anchor | depth_lm | key values |")
        lines.append("|:-----|:-------|:------:|:--------:|:-----------|")
        for r in valid_clips:
            dv = r["debug_values"]
            vals = []
            for k, v in sorted(dv.items()):
                if isinstance(v, float):
                    vals.append(f"{k}={v:.2f}")
                else:
                    vals.append(f"{k}={v}")
            vals_str = "; ".join(vals[:8])
            lines.append(f"| {r['hash'][:8]} | {r['camera_type']} | "
                        f"{r['anchor_calibrated']} | {r['depth_landmark']} | {vals_str} |")
    else:
        lines.append("**No clips achieved valid=True** on this sample.")
        lines.append("This confirms the Session 5 finding: the physics path never activates")
        lines.append("under `CRICKET_PREDICTOR_MODE=auto`.")
    lines.append("")

    # Wall-clock
    times = [r["elapsed_s"] for r in results]
    errs  = [r for r in results if r.get("error")]
    lines.append("## Wall-clock")
    lines.append("")
    lines.append("| metric | value |")
    lines.append("|:-------|------:|")
    lines.append(f"| n clips | {n} |")
    lines.append(f"| mean | {sum(times)/len(times):.2f} s |")
    lines.append(f"| median | {sorted(times)[len(times)//2]:.2f} s |")
    lines.append(f"| errors | {len(errs)} |")
    lines.append("")

    # Conclusion
    lines.append("## Conclusion")
    lines.append("")
    lines.append(f"The dominant failure is `{top1}` ({top1_count}/{n} = {top1_pct:.1f}%).")
    if top1 == REASON_ENDON_NO_DEPTH_LANDMARK:
        lines.append("The end-on wicket IS found (anchor_calibrated=True) but both depth landmarks")
        lines.append("(bowler's-end wicket and popping crease) are occluded or absent in every clip.")
        lines.append("This is a fundamental constraint of broadcast end-on footage: the bowler's-end")
        lines.append("wicket is typically blocked by the umpire or bowler at the delivery instant,")
        lines.append("and the popping crease is obscured by the batter's feet.")
    elif top1 == REASON_ENDON_NO_WICKET:
        lines.append("The wicket detector finds no satisfactory group of thin vertical bars.")
        lines.append("This can be a threshold issue (base row / centre-off / px_lat range)")
        lines.append("or a wrong-frame issue (shot-selection returned a non-pitch frame).")
    lines.append("")
    lines.append("---")
    lines.append("*Session 6 — observation only, no prediction behaviour changed.*")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Regression check helper
# ---------------------------------------------------------------------------
def regression_check_flag_off(clips: list[dict]) -> dict:
    """
    Run PitchHomography with HOMOGRAPHY_DEBUG unset on the same clips and
    verify debug_reasons=[] and debug_values={} (default attributes are empty).
    Does NOT run the full scoring pipeline — that is covered by the Session 5
    script; this just verifies the instrumentation adds zero overhead/side-effects.
    """
    mismatches = 0
    for row in clips[:20]:
        vp = Path(row["video_path"])
        cap = cv2.VideoCapture(str(vp))
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        selection = select_delivery_shot(vp, total_frames=frame_count)
        best_shot = selection.best()
        delivery_frame = best_shot.mid_frame if best_shot is not None else int(frame_count * 0.55)
        cap.set(cv2.CAP_PROP_POS_FRAMES, delivery_frame)
        ret, ref_frame = cap.read()
        cap.release()
        if not ret or ref_frame is None:
            continue

        # Ensure flag is NOT set
        os.environ.pop("HOMOGRAPHY_DEBUG", None)
        hom = PitchHomography(ref_frame)
        if hom.debug_reasons or hom.debug_values:
            mismatches += 1
            logger.error("Regression: clip %s has non-empty debug with flag off: reasons=%s",
                         row["hash"][:8], hom.debug_reasons)
    return {"clips_checked": min(20, len(clips)), "mismatches": mismatches}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", type=int, default=0,
                    help="Max clips to run (0 = all available VAL clips)")
    ap.add_argument("--n-per-band", type=int, default=13,
                    help="Max clips per kph band (default 13)")
    ap.add_argument("--skip-regression", action="store_true")
    args = ap.parse_args()

    print("=" * 70)
    print("Homography Validity Autopsy — Session 6")
    print("=" * 70)

    print("\n[1/4] Selecting VAL clips on disk...")
    clips = select_val_clips(n_per_band=args.n_per_band)
    if args.clips > 0:
        clips = clips[:args.clips]
    print(f"  {len(clips)} clips selected (n_per_band={args.n_per_band})")
    band_dist = Counter(c["band"] for c in clips)
    for b, cnt in sorted(band_dist.items()):
        print(f"    {b}: {cnt}")

    if len(clips) < 30:
        print(f"\nSTOP: only {len(clips)} VAL clips available on disk (minimum 30).")
        print("Run from a machine with more of data/videos_sample/ present.")
        sys.exit(1)

    print(f"\n[2/4] Running instrumented homography on {len(clips)} clips...")
    results = []
    for i, row in enumerate(clips):
        r = analyse_clip(row)
        results.append(r)
        if (i + 1) % 10 == 0 or (i + 1) == len(clips):
            n_valid = sum(1 for x in results if x["valid"])
            logger.warning("Progress %d/%d  valid=%d  invalid=%d",
                           i + 1, len(clips), n_valid, len(results) - n_valid)
            print(f"  {i+1}/{len(clips)}  valid={n_valid}  invalid={len(results)-n_valid}")

    # Write JSONL
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(_JSONL_OUT, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")
    print(f"  JSONL written: {_JSONL_OUT}")

    # Aggregate
    n = len(results)
    n_valid = sum(1 for r in results if r["valid"])
    print(f"\n  Overall: n={n}  valid={n_valid}  invalid={n - n_valid}")

    # Reason frequency
    reason_counts: Counter = Counter()
    for r in results:
        for rc in r["debug_reasons"]:
            reason_counts[rc] += 1
    top3 = [rc for rc, _ in reason_counts.most_common(3)]
    print("\n  Top reason codes:")
    for rc, cnt in reason_counts.most_common(6):
        print(f"    {rc}: {cnt} ({cnt/n*100:.1f}%)")

    print("\n[3/4] Saving reference frames for top-3 reasons...")
    # For each top-3 reason, save up to 5 example frames
    top3_examples: dict[str, list[dict]] = {rc: [] for rc in top3}
    MAX_EXAMPLES = 5

    for rc in top3:
        out_dir = _FRAMES_DIR / rc
        out_dir.mkdir(parents=True, exist_ok=True)

    for row in clips:
        r_dict = next((r for r in results if r["hash"] == row["hash"]), None)
        if r_dict is None:
            continue
        for rc in top3:
            if rc not in r_dict["debug_reasons"]:
                continue
            if len(top3_examples[rc]) >= MAX_EXAMPLES:
                continue
            # Save the reference frame
            vp = Path(row["video_path"])
            out_path = _FRAMES_DIR / rc / f"{row['hash'][:8]}_frame.jpg"
            if not out_path.exists():
                try:
                    cap = cv2.VideoCapture(str(vp))
                    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                    selection = select_delivery_shot(vp, total_frames=frame_count)
                    best_shot = selection.best()
                    df = best_shot.mid_frame if best_shot is not None else int(frame_count * 0.55)
                    cap.set(cv2.CAP_PROP_POS_FRAMES, df)
                    ret, ref_frame = cap.read()
                    cap.release()
                    if ret and ref_frame is not None:
                        cv2.imwrite(str(out_path), ref_frame,
                                    [cv2.IMWRITE_JPEG_QUALITY, 85])
                except Exception as e:
                    logger.warning("Frame save failed for %s: %s", row["hash"][:8], e)
            r_dict["ref_frame_path"] = str(out_path.relative_to(_OUT_DIR))
            top3_examples[rc].append(r_dict)

    for rc in top3:
        print(f"  {rc}: {len(top3_examples[rc])} frames saved")

    print("\n[4/4] Building report...")
    report = build_report(results, top3_examples)
    _REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"  Report: {_REPORT_PATH}")

    if not args.skip_regression:
        print("\n[5/5] Regression check (flag-off)...")
        reg = regression_check_flag_off(clips)
        if reg["mismatches"] == 0:
            print(f"  PASS: {reg['clips_checked']} clips, 0 mismatches — debug attributes empty with flag off")
        else:
            print(f"  FAIL: {reg['mismatches']} clips had non-empty debug attributes with flag off")

    print("\nDone.")


if __name__ == "__main__":
    main()
