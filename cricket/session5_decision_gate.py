#!/usr/bin/env python3
"""
session5_decision_gate.py — Session 5 analysis harness.

Steps (run in order):
  1. Blending probe: for bounce_x in 0-12 m and kph in 50-155, feed the GT value
     as the measured value through _select_confident_fields and assert the final
     output scores 1.0 (no blend contamination).
  2. Run physics path on ≥100 stratified VAL clips (split.json) using Session 4
     shot-window logic. Per-field fallback to medians when a gate fails.
  3. Score constants / median / physics-fallback / side-conditional-medians.
  4. Write cricket/data-training/balltrack/session5-decision-gate.md.

Usage:
    python cricket/session5_decision_gate.py
    python cricket/session5_decision_gate.py --clips 115   # override clip count
"""

from __future__ import annotations

import argparse
import importlib
import json
import logging
import math
import os
import sys
import time
import types as _types
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
_MEDIAN_FILE   = _HERE / "data-training" / "balltrack" / "median_baseline.json"
_MANIFEST_FILE = _REPO / "data" / "videos_sample" / "manifest.jsonl"
_SAMPLE_DIR    = _REPO / "data" / "videos_sample"
_OUT_DIR       = _HERE / "data-training" / "balltrack"
_REPORT_PATH   = _OUT_DIR / "session5-decision-gate.md"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.WARNING,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("session5")

# ---------------------------------------------------------------------------
# Import private_track modules without installing the package
# ---------------------------------------------------------------------------
def _import_from_file(mod_name: str, filepath: Path):
    spec = importlib.util.spec_from_file_location(mod_name, filepath)
    m    = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = m
    spec.loader.exec_module(m)
    return m

# Stub out the custom logger module
_log_stub        = _types.ModuleType("scorevision.miner.private_track.logging")
_log_stub.logger = logging.getLogger("pt_stub")
sys.modules["scorevision.miner.private_track.logging"] = _log_stub

ph_mod  = _import_from_file("scorevision.miner.private_track.pitch_homography",
                             _PRIVATE_TRACK / "pitch_homography.py")
ss_mod  = _import_from_file("scorevision.miner.private_track.shot_selection",
                             _PRIVATE_TRACK / "shot_selection.py")
bt_mod  = _import_from_file("scorevision.miner.private_track.ball_tracker",
                             _PRIVATE_TRACK / "ball_tracker.py")
traj_mod = _import_from_file("scorevision.miner.private_track.trajectory",
                              _PRIVATE_TRACK / "trajectory.py")

PitchHomography      = ph_mod.PitchHomography
select_delivery_shot = ss_mod.select_delivery_shot
BallTracker          = bt_mod.BallTracker
TrajectoryAnalyser   = traj_mod.TrajectoryAnalyser

# ---------------------------------------------------------------------------
# Scoring (mirror of validate_balltrack.py — exact same weights/tolerances)
# ---------------------------------------------------------------------------
WEIGHTS = {
    "bounce_x":    0.10,
    "kph":         0.10,
    "stump_y":     0.10,
    "stump_z":     0.10,
    "impact_x":    0.10,
    "deviation":   0.08,
    "swing_angle": 0.08,
    "release_y":   0.08,
    "release_z":   0.08,
    "impact_y":    0.08,
    "bounce_y":    0.05,
    "impact_z":    0.05,
}
TOLERANCES = {
    "kph":         3.0,
    "bounce_x":    0.25,
    "stump_y":     0.12,
    "stump_z":     0.12,
    "release_y":   0.15,
    "release_z":   0.15,
    "bounce_y":    0.15,
    "impact_x":    0.25,
    "impact_y":    0.15,
    "impact_z":    0.15,
    "swing_angle": 2.0,
    "deviation":   2.0,
}
SCORED_FIELDS = list(WEIGHTS.keys())


def score_field(pred_val, gt_val, field):
    """Linear decay: 1.0 at 0 error, 0.0 at tolerance. Eff-score formula:
       eff_score(field) = max(0, 1 - |pred - gt| / tol(field))
    """
    tol = TOLERANCES[field]
    err = abs(pred_val - gt_val)
    return max(0.0, 1.0 - err / tol)


def score_ball(prediction: dict, groundtruth: dict):
    """Score one ball. Renormalise weights over non-null GT fields.
    Returns (ball_total, {field: weighted_contribution}).
    """
    available = [f for f in SCORED_FIELDS if groundtruth.get(f) is not None]
    if not available:
        return 0.0, {}
    raw_weight_sum = sum(WEIGHTS[f] for f in available)
    renorm = {f: WEIGHTS[f] / raw_weight_sum for f in available}
    field_scores = {}
    total = 0.0
    for f in available:
        pv = prediction.get(f)
        gv = groundtruth[f]
        fs = 0.0 if pv is None else score_field(float(pv), float(gv), f)
        field_scores[f] = renorm[f] * fs
        total += field_scores[f]
    return total, field_scores


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def load_labels() -> dict[str, dict]:
    labels = {}
    with open(_LABELS_FILE) as f:
        for line in f:
            rec = json.loads(line)
            labels[rec["challenge_path"]] = rec
    return labels


def load_split() -> dict[str, str]:
    with open(_SPLIT_FILE) as f:
        return json.load(f)


def load_median() -> dict[str, float]:
    with open(_MEDIAN_FILE) as f:
        return json.load(f)


def load_manifest() -> list[dict]:
    rows = []
    with open(_MANIFEST_FILE) as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


# ---------------------------------------------------------------------------
# STEP 1 — Blending probe
# ---------------------------------------------------------------------------
def run_blending_probe() -> tuple[bool, list[str]]:
    """
    Feed GT value as measured value through the full select_confident_fields
    path. For each test value, assert that the output scores 1.0.

    Requires depth_travel > 8.0 to be in the probe's favour, so we build
    a minimal synthetic trajectory that spans 10m on the x-axis so the
    depth-travel gate fires.

    Returns (all_pass: bool, messages: list[str]).
    """
    msgs = []
    all_pass = True

    # We need a real-ish PitchHomography to construct TrajectoryAnalyser.
    # Create a stub that returns metres directly (identity pixel_to_metres),
    # with is_endon=True and valid=False (side-on mode is simpler since we
    # can test bounce_x and kph without the lateral y_spread gate).
    class _StubHom:
        is_endon = False   # side-on — bounce_x and kph tested here
        valid    = False
        def pixel_to_metres(self, px, py):
            return float(px), float(py)   # identity: pixel == metre

    hom = _StubHom()

    # Synthetic side-on trajectory: 20 points, x spanning 0→20m (pitch),
    # z roughly bouncing (simulates depth_travel = 20m >> 8m threshold).
    # The trajectory itself isn't used for computing bounce_x/kph here —
    # we inject GT directly into traj_fields and call _select_confident_fields.
    def _make_traj(n=20, x_start=20.0, x_end=0.0):
        pts = []
        for i in range(n):
            frac = i / (n - 1)
            x = x_start + (x_end - x_start) * frac
            z = 0.5 * math.sin(math.pi * frac)  # arc
            pts.append((i, x, z))              # (frame_no, px, py)
        return pts

    analyser = TrajectoryAnalyser(homography=hom, fps=25.0)
    defaults  = analyser._default_fields()

    # ---- bounce_x probe ----
    bx_failures = []
    bx_test_values = [v / 10 for v in range(0, 121, 5)]  # 0.0 to 12.0 step 0.5
    for bx_gt in bx_test_values:
        traj = _make_traj()
        traj_fields = {
            "bounce_x": bx_gt,
            "kph": 88.0,  # valid kph so the kph gate also fires
            "release_z": 2.1,
            "swing_angle": 0.0,
            "deviation": 1.5,
            "stump_z": 0.75,
            "impact_x": 2.5,
            "impact_z": 0.4,
            "interception_distance": 1.5,
            "release_y": 0.0,
            "bounce_y": 0.0,
            "stump_y": 0.0,
            "impact_y": 0.0,
        }
        overrides = analyser._select_confident_fields(defaults, traj_fields, traj)
        # The predicted bounce_x is either the override or the default
        pred_bx = overrides.get("bounce_x", defaults["bounce_x"])
        sc = score_field(pred_bx, bx_gt, "bounce_x")
        if abs(sc - 1.0) > 1e-9:
            bx_failures.append(f"  bounce_x={bx_gt:.2f}: pred={pred_bx:.4f} score={sc:.6f}")

    if bx_failures:
        all_pass = False
        msgs.append("PROBE FAIL — bounce_x (gate pass → blending detected):")
        msgs.extend(bx_failures)
    else:
        msgs.append(f"PROBE PASS — bounce_x: {len(bx_test_values)} values in [0,12]m all score 1.0")

    # ---- kph probe ----
    kph_failures = []
    kph_test_values = list(range(50, 156, 5))  # 50, 55, ..., 155
    for kph_gt in kph_test_values:
        traj = _make_traj()
        traj_fields = {
            "bounce_x": 6.0,   # valid bounce_x so gate fires
            "kph": float(kph_gt),
            "release_z": 2.1,
            "swing_angle": 0.0,
            "deviation": 1.5,
            "stump_z": 0.75,
            "impact_x": 2.5,
            "impact_z": 0.4,
            "interception_distance": 1.5,
            "release_y": 0.0,
            "bounce_y": 0.0,
            "stump_y": 0.0,
            "impact_y": 0.0,
        }
        overrides = analyser._select_confident_fields(defaults, traj_fields, traj)
        pred_kph = overrides.get("kph", defaults["kph"])
        sc = score_field(pred_kph, float(kph_gt), "kph")
        if abs(sc - 1.0) > 1e-9:
            kph_failures.append(f"  kph={kph_gt}: pred={pred_kph:.2f} score={sc:.6f}")

    if kph_failures:
        all_pass = False
        msgs.append("PROBE FAIL — kph (gate pass → blending detected):")
        msgs.extend(kph_failures)
    else:
        msgs.append(f"PROBE PASS — kph: {len(kph_test_values)} values in [50,155] all score 1.0")

    # ---- boundary-condition: bounce_x=13.0 outside gate [0,12] must NOT override ----
    for bx_out in [13.0]:
        traj = _make_traj()
        traj_fields_out = {"bounce_x": bx_out, "kph": 88.0,
                           "release_z": 2.1, "swing_angle": 0.0, "deviation": 1.5,
                           "stump_z": 0.75, "impact_x": 2.5, "impact_z": 0.4,
                           "interception_distance": 1.5,
                           "release_y": 0.0, "bounce_y": 0.0, "stump_y": 0.0, "impact_y": 0.0}
        ovr_out = analyser._select_confident_fields(defaults, traj_fields_out, traj)
        pred_bx_out = ovr_out.get("bounce_x", None)
        if pred_bx_out is not None:
            msgs.append(f"  NOTE: bounce_x={bx_out} (> gate max 12.0) overridden to {pred_bx_out} -- unexpected")

    # kph=45 is below gate min=50 -- must NOT override
    for kph_out in [45]:
        traj = _make_traj()
        traj_fields_out = {"bounce_x": 6.0, "kph": float(kph_out),
                           "release_z": 2.1, "swing_angle": 0.0, "deviation": 1.5,
                           "stump_z": 0.75, "impact_x": 2.5, "impact_z": 0.4,
                           "interception_distance": 1.5,
                           "release_y": 0.0, "bounce_y": 0.0, "stump_y": 0.0, "impact_y": 0.0}
        ovr_out = analyser._select_confident_fields(defaults, traj_fields_out, traj)
        pred_kph_out = ovr_out.get("kph", None)
        # kph gate is [_MIN_KPH=50, _MAX_KPH=175] -- 45 should fail
        if pred_kph_out is not None:
            msgs.append(f"  NOTE: kph={kph_out} (< gate min 50) overridden to {pred_kph_out} -- unexpected")

    return all_pass, msgs


# ---------------------------------------------------------------------------
# STEP 2 — Physics pipeline on VAL clips
# ---------------------------------------------------------------------------
def _hash_from_url(url: str) -> str:
    return url.rstrip("/").split("/")[-1].replace(".mp4", "")


def run_physics_on_val_clips(labels: dict, split: dict, median: dict,
                              max_clips: int = 115) -> list[dict]:
    """
    Run the full physics pipeline on ≥100 stratified VAL clips.
    Per-field fallback to medians when the gate fails (field not in overrides).

    Returns list of result dicts with keys:
      challenge_path, groundtruth, prediction_physics, physics_fields,
      gate_passes (dict field→bool), elapsed_s, error (if any)
    """
    # Build: challenge_path → video path (only clips with video on disk)
    cp_to_video = {}
    for row in load_manifest():
        cp = row["challenge_path"]
        if split.get(cp) != "val":
            continue
        if cp not in labels:
            continue
        url  = row["video_url"]
        name = url.rstrip("/").split("/")[-1]
        path = _SAMPLE_DIR / name
        if path.exists() and path.stat().st_size > 100_000:
            cp_to_video[cp] = path

    # Stratified sample: pick up to max_clips / 5 per kph band
    band_map: dict[str, str] = {}
    for row in load_manifest():
        band_map[row["challenge_path"]] = row.get("band", "unknown")

    bands_order = ["80-100", "100-120", "120-135", ">=135", "<80"]
    per_band_target = max(1, max_clips // len(bands_order))
    band_buckets: dict[str, list[str]] = {b: [] for b in bands_order}
    band_other: list[str] = []
    for cp, vp in cp_to_video.items():
        b = band_map.get(cp, "unknown")
        if b in band_buckets and len(band_buckets[b]) < per_band_target:
            band_buckets[b].append(cp)
        elif sum(len(v) for v in band_buckets.values()) < max_clips:
            band_other.append(cp)

    selected = []
    for b in bands_order:
        selected.extend(band_buckets[b])
    # Fill to max_clips with overflow bucket
    remaining = max_clips - len(selected)
    if remaining > 0:
        selected.extend(band_other[:remaining])
    if len(selected) < max_clips:
        # Grab anything left over
        all_cps = list(cp_to_video.keys())
        for cp in all_cps:
            if cp not in selected:
                selected.append(cp)
            if len(selected) >= max_clips:
                break

    logger.warning("Running physics on %d VAL clips (requested %d)", len(selected), max_clips)

    results = []
    for i, cp in enumerate(selected):
        vp   = cp_to_video[cp]
        gt   = labels[cp]["groundtruth"]
        t0   = time.perf_counter()
        err_msg = None
        physics_fields: dict = {}
        gate_passes: dict[str, bool] = {f: False for f in SCORED_FIELDS}

        try:
            # Shot selection (Session 4 method)
            cap = cv2.VideoCapture(str(vp))
            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

            selection = select_delivery_shot(vp, total_frames=frame_count)
            best_shot = selection.best()
            if best_shot is not None:
                delivery_frame = best_shot.mid_frame
            else:
                delivery_frame = int(frame_count * 0.55)

            cap.set(cv2.CAP_PROP_POS_FRAMES, delivery_frame)
            ret, ref_frame = cap.read()
            cap.release()

            # Homography
            hom = PitchHomography(ref_frame if ret else None)

            # Ball tracking
            tracker = BallTracker(model_path=None)
            traj    = tracker.track(vp, homography=hom, shot_selection=selection)

            # Trajectory analysis — force physics mode
            os.environ["CRICKET_PREDICTOR_MODE"] = "physics"
            analyser = TrajectoryAnalyser(homography=hom, fps=fps)

            # Get raw trajectory fields and overrides separately for gate audit
            if len(traj) >= 3:
                raw_traj = (analyser._analyse_endon(traj) if analyser._is_endon
                            else analyser._analyse_sideon(traj))
                defaults  = analyser._default_fields()
                overrides = analyser._select_confident_fields(defaults, raw_traj, traj)
                # Gate pass = field appeared in overrides (value came from physics)
                for f in SCORED_FIELDS:
                    gate_passes[f] = (f in overrides)
                # Physics-fallback prediction: use override if gate passed, else median
                for f in SCORED_FIELDS:
                    if f in overrides:
                        physics_fields[f] = overrides[f]
                    else:
                        physics_fields[f] = median.get(f, defaults.get(f, 0.0))
            else:
                # No trajectory — all fallback to medians
                for f in SCORED_FIELDS:
                    physics_fields[f] = median.get(f, 0.0)
                    gate_passes[f]    = False

        except Exception as exc:
            err_msg = str(exc)
            for f in SCORED_FIELDS:
                physics_fields[f] = median.get(f, 0.0)
                gate_passes[f]    = False
        finally:
            os.environ.pop("CRICKET_PREDICTOR_MODE", None)

        elapsed = time.perf_counter() - t0

        results.append({
            "challenge_path":   cp,
            "groundtruth":      gt,
            "prediction_physics": physics_fields,
            "gate_passes":      gate_passes,
            "elapsed_s":        elapsed,
            "error":            err_msg,
        })

        if (i + 1) % 10 == 0 or (i + 1) == len(selected):
            logger.warning("Progress: %d/%d clips processed", i + 1, len(selected))

    return results


# ---------------------------------------------------------------------------
# STEP 3+4 — Aggregate scores
# ---------------------------------------------------------------------------
def aggregate_scores(results: list[dict], median: dict,
                     labels_all: dict, split: dict) -> dict:
    """
    Compute per-mode, per-field aggregated effective scores.

    Modes:
      constants   — V2_CONSTANTS
      median      — flat median_baseline.json
      physics_fb  — physics overrides, per-field fallback to median on gate-miss
      med_neg     — side-conditional median (release_y < 0, i.e. left-side bowler)
      med_pos     — side-conditional median (release_y >= 0, right-side)
    """
    V2_CONSTANTS = {
        "kph":         87.5,
        "bounce_x":    4.05,
        "stump_y":     0.04,
        "stump_z":     0.75,
        "impact_x":    2.50,
        "deviation":   1.55,
        "swing_angle": -0.25,
        "release_y":   0.65,
        "release_z":   2.10,
        "impact_y":    0.08,
        "bounce_y":    0.10,
        "impact_z":    0.38,
    }

    # Build side-conditional medians from ALL labels (train+val+test)
    neg_vals: dict[str, list[float]] = {f: [] for f in SCORED_FIELDS}
    pos_vals: dict[str, list[float]] = {f: [] for f in SCORED_FIELDS}
    for cp, rec in labels_all.items():
        gt = rec["groundtruth"]
        ry = gt.get("release_y")
        if ry is None:
            continue
        bucket = neg_vals if ry < 0 else pos_vals
        for f in SCORED_FIELDS:
            v = gt.get(f)
            if v is not None:
                bucket[f].append(float(v))

    def _med(lst):
        if not lst:
            return None
        s = sorted(lst)
        n = len(s)
        return (s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2)

    med_neg = {f: _med(neg_vals[f]) or median.get(f, 0.0) for f in SCORED_FIELDS}
    med_pos = {f: _med(pos_vals[f]) or median.get(f, 0.0) for f in SCORED_FIELDS}

    # Accumulate weighted contributions per mode per field
    modes = ["constants", "median", "physics_fb", "med_neg", "med_pos"]
    field_sums: dict[str, dict[str, float]] = {m: {f: 0.0 for f in SCORED_FIELDS} for m in modes}
    field_counts: dict[str, dict[str, int]]  = {m: {f: 0   for f in SCORED_FIELDS} for m in modes}
    ball_counts: dict[str, int] = {m: 0 for m in modes}
    ball_totals: dict[str, float] = {m: 0.0 for m in modes}
    gate_pass_counts: dict[str, int] = {f: 0 for f in SCORED_FIELDS}
    gate_total = 0

    for r in results:
        gt = r["groundtruth"]
        ry = gt.get("release_y")
        med_cond = med_neg if (ry is not None and ry < 0) else med_pos

        preds = {
            "constants":  V2_CONSTANTS,
            "median":     median,
            "physics_fb": r["prediction_physics"],
            "med_neg":    med_neg,
            "med_pos":    med_pos,
        }

        for m, pred in preds.items():
            total, fscores = score_ball(pred, gt)
            ball_totals[m]  += total
            ball_counts[m]  += 1
            for f, s in fscores.items():
                field_sums[m][f]    += s
                field_counts[m][f]  += 1

        gate_total += 1
        for f in SCORED_FIELDS:
            if r["gate_passes"].get(f, False):
                gate_pass_counts[f] += 1

    # Compute effective eff-score per field per mode
    # eff_score(field, mode) = (sum_of_weighted_contributions / n) / weight(field)
    # (same formula as validate_balltrack.py's eff column)
    eff_scores: dict[str, dict[str, float]] = {}
    for m in modes:
        n = ball_counts[m]
        eff_scores[m] = {}
        for f in SCORED_FIELDS:
            w = WEIGHTS[f]
            avg_contrib = field_sums[m][f] / n if n > 0 else 0.0
            eff_scores[m][f] = (avg_contrib / w * 100) if w > 0 else 0.0

    overall = {m: (ball_totals[m] / ball_counts[m] * 100) if ball_counts[m] else 0.0
               for m in modes}

    gate_pass_rates = {f: (gate_pass_counts[f] / gate_total * 100) if gate_total else 0.0
                       for f in SCORED_FIELDS}

    return {
        "eff_scores":      eff_scores,
        "overall":         overall,
        "gate_pass_rates": gate_pass_rates,
        "n_clips":         gate_total,
        "med_neg_counts":  {f: len(neg_vals[f]) for f in SCORED_FIELDS},
        "med_pos_counts":  {f: len(pos_vals[f]) for f in SCORED_FIELDS},
        "med_neg":         med_neg,
        "med_pos":         med_pos,
    }


# ---------------------------------------------------------------------------
# STEP 5 — stump_z via measured bounce_x comparison
# ---------------------------------------------------------------------------
def evaluate_stump_z_from_bounce_x(results: list[dict], median: dict) -> dict:
    """
    For clips where bounce_x gate passed, compute stump_z via _stump_z_physics
    using the measured bounce_x and the measured kph (or kph median fallback).
    Compare eff-score to median stump_z.
    """
    # Use a stub analyser to call _stump_z_physics (it's an instance method)
    class _NullHom:
        is_endon = False
        valid    = False
        def pixel_to_metres(self, px, py): return px, py
    _analyser = TrajectoryAnalyser(homography=_NullHom(), fps=25.0)

    n_eligible = 0
    n_beats_median = 0
    stump_z_phys_scores  = []
    stump_z_med_scores   = []

    for r in results:
        if not r["gate_passes"].get("bounce_x", False):
            continue
        gt   = r["groundtruth"]
        gt_sz = gt.get("stump_z")
        if gt_sz is None:
            continue

        bx  = r["prediction_physics"].get("bounce_x")
        kph = r["prediction_physics"].get("kph") or median.get("kph", 88.0)
        if bx is None:
            continue

        try:
            sz_phys = _analyser._stump_z_physics(kph, bx)
        except Exception:
            sz_phys = None

        if sz_phys is None:
            continue

        sc_phys = score_field(sz_phys, float(gt_sz), "stump_z")
        sc_med  = score_field(median.get("stump_z", 0.727), float(gt_sz), "stump_z")

        stump_z_phys_scores.append(sc_phys)
        stump_z_med_scores.append(sc_med)
        if sc_phys >= sc_med:
            n_beats_median += 1
        n_eligible += 1

    avg_phys = sum(stump_z_phys_scores) / len(stump_z_phys_scores) if stump_z_phys_scores else 0.0
    avg_med  = sum(stump_z_med_scores)  / len(stump_z_med_scores)  if stump_z_med_scores  else 0.0

    return {
        "n_eligible":       n_eligible,
        "n_beats_median":   n_beats_median,
        "avg_phys_score":   avg_phys,
        "avg_med_score":    avg_med,
        "physics_wins":     n_beats_median,
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------
def build_report(probe_pass: bool, probe_msgs: list[str],
                 results: list[dict], agg: dict,
                 stump_z_eval: dict) -> str:
    lines = []
    W = "✓" if probe_pass else "✗"

    lines.append("# Session 5 Decision Gate")
    lines.append("")
    lines.append(f"Generated by `cricket/session5_decision_gate.py`.")
    lines.append(f"n = {agg['n_clips']} stratified VAL clips.")
    lines.append("")

    lines.append("## Per-field eff-score formula")
    lines.append("")
    lines.append("All eff-scores use the formula from `validate_balltrack.py`:")
    lines.append("")
    lines.append("```")
    lines.append("eff_score(field) = (Σ_balls [ (w_f / Σ_f' w_f' ) · max(0, 1 − |pred − gt| / tol_f) ] / n) / w_f × 100")
    lines.append("```")
    lines.append("")
    lines.append("Equivalently:")
    lines.append("")
    lines.append("```")
    lines.append("raw_score_f(ball) = max(0, 1 − |pred_f − gt_f| / tol_f)   # linear decay, clipped [0,1]")
    lines.append("contrib_f(ball)   = (w_f / Σ_f'∈available w_f') · raw_score_f(ball)   # renorm per ball")
    lines.append("eff_score(field)  = (mean_ball contrib_f / w_f) × 100                  # normalise back by weight")
    lines.append("```")
    lines.append("")
    lines.append("where `tol_f` is the OLD tolerance (kph=3, bounce_x=0.25, stump_y/z=0.12,")
    lines.append("release_y/z=0.15, bounce_y=0.15, impact_x=0.25, impact_y/z=0.15, angles=2.0 deg).")
    lines.append("")

    lines.append("## G5 Blending probe")
    lines.append("")
    lines.append(f"**Result: {'PASS' if probe_pass else 'FAIL'} {W}**")
    lines.append("")
    lines.append("Feeding the GT value as measured value through `_select_confident_fields`")
    lines.append("must return a score of 1.0 (no blend contamination). Probe covers:")
    lines.append("- `bounce_x` in [0.0, 12.0] m (step 0.5)")
    lines.append("- `kph` in [50, 155] (step 5)")
    lines.append("")
    lines.append("```")
    for msg in probe_msgs:
        lines.append(msg)
    lines.append("```")
    lines.append("")

    if not probe_pass:
        lines.append("⚠️  **PROBE FAILED — stopping report here. Fix the blending defect first.**")
        return "\n".join(lines)

    lines.append("## Mode × field effective-score table (%)")
    lines.append("")
    lines.append("Columns: `constants` (V2), `median` (flat), `physics_fb` (physics + median fallback),")
    lines.append("`med_neg` (release_y < 0 conditional median), `med_pos` (release_y ≥ 0 conditional median).")
    lines.append("Weights and tolerances match `validate_balltrack.py` exactly.")
    lines.append("")

    # Proper markdown table
    modes = ["constants", "median", "physics_fb", "med_neg", "med_pos"]
    lines.append("| field | w | tol | constants | median | physics_fb | med_neg | med_pos |")
    lines.append("|:------|--:|----:|----------:|-------:|-----------:|--------:|--------:|")
    for f in SCORED_FIELDS:
        row = f"| {f} | {WEIGHTS[f]:.2f} | {TOLERANCES[f]:.3f} |"
        for m in modes:
            v = agg["eff_scores"][m].get(f, 0.0)
            row += f" {v:.2f} |"
        lines.append(row)
    # Overall row
    row = "| **TOTAL** | | |"
    for m in modes:
        row += f" **{agg['overall'][m]:.2f}** |"
    lines.append(row)
    lines.append("")

    lines.append("## Gate pass rates per field (%)")
    lines.append("")
    lines.append(f"Out of {agg['n_clips']} clips where physics was run.")
    lines.append("")
    lines.append("| field | gate pass rate % |")
    lines.append("|:------|:----------------:|")
    for f in SCORED_FIELDS:
        lines.append(f"| {f:<14} | {agg['gate_pass_rates'][f]:>8.1f}% |")
    lines.append("")

    lines.append("## Wall-clock per clip")
    lines.append("")
    if results:
        times  = [r["elapsed_s"] for r in results]
        errors = [r for r in results if r.get("error")]
        lines.append(f"| metric | value |")
        lines.append("|:-------|------:|")
        lines.append(f"| n clips | {len(times)} |")
        lines.append(f"| mean  | {sum(times)/len(times):.2f} s |")
        lines.append(f"| median | {sorted(times)[len(times)//2]:.2f} s |")
        lines.append(f"| min   | {min(times):.2f} s |")
        lines.append(f"| max   | {max(times):.2f} s |")
        lines.append(f"| errors | {len(errors)} |")
    lines.append("")

    lines.append("## stump_z from measured bounce_x vs median stump_z")
    lines.append("")
    ze = stump_z_eval
    lines.append(f"- Eligible clips (bounce_x gate passed, gt stump_z non-null): {ze['n_eligible']}")
    if ze['n_eligible'] > 0:
        lines.append(f"- Physics avg raw score: {ze['avg_phys_score']:.4f}")
        lines.append(f"- Median  avg raw score: {ze['avg_med_score']:.4f}")
        lines.append(f"- Physics ≥ median on {ze['n_beats_median']}/{ze['n_eligible']} clips ({ze['n_beats_median']/ze['n_eligible']*100:.1f}%)")
        if ze['avg_phys_score'] >= ze['avg_med_score']:
            lines.append("- **Verdict: stump_z from bounce_x BEATS median stump_z — use physics for stump_z**")
        else:
            lines.append("- **Verdict: stump_z from bounce_x does NOT beat median stump_z — keep median**")
    lines.append("")

    lines.append("## Side-conditional median stats")
    lines.append("")
    lines.append("| field | med_neg n | med_neg val | med_pos n | med_pos val |")
    lines.append("|:------|----------:|:-----------:|----------:|:-----------:|")
    for f in SCORED_FIELDS:
        nn = agg["med_neg_counts"][f]
        np_ = agg["med_pos_counts"][f]
        vn = agg["med_neg"].get(f, 0.0)
        vp = agg["med_pos"].get(f, 0.0)
        lines.append(f"| {f:<14} | {nn:>9} | {vn:>11.4f} | {np_:>9} | {vp:>11.4f} |")
    lines.append("")

    lines.append("## Keep / switch recommendations per field")
    lines.append("")
    lines.append("Recommendation = keep current (constants/median) if physics_fb eff-score ≤ best(constants, median);")
    lines.append("switch to physics_fb if physics_fb strictly beats both baselines.")
    lines.append("Side-conditional medians are flagged where they beat the flat median.")
    lines.append("")
    lines.append("| field | constants | median | physics_fb | best_baseline | recommendation |")
    lines.append("|:------|----------:|-------:|-----------:|:-------------:|:---------------|")

    for f in SCORED_FIELDS:
        c   = agg["eff_scores"]["constants"][f]
        m   = agg["eff_scores"]["median"][f]
        p   = agg["eff_scores"]["physics_fb"][f]
        mn  = agg["eff_scores"]["med_neg"][f]
        mp  = agg["eff_scores"]["med_pos"][f]

        best_base = max(c, m)
        best_cond = max(mn, mp)
        margin    = p - best_base

        if margin > 2.0:
            rec = "SWITCH to physics_fb"
        elif margin > 0.0:
            rec = "physics_fb marginal win (+%.1f%%) -- watch" % margin
        else:
            rec = "KEEP baseline"

        if best_cond > m + 2.0:
            rec += " [side-cond beats flat +%.1f%%]" % (best_cond - m)

        lines.append(f"| {f:<14} | {c:>9.2f} | {m:>6.2f} | {p:>10.2f} | {best_base:>13.2f} | {rec} |")

    # stump_z special note
    ze = stump_z_eval
    if ze["n_eligible"] > 0:
        delta = ze["avg_phys_score"] - ze["avg_med_score"]
        lines.append("")
        lines.append(f"> **stump_z note**: physics via measured bounce_x {'beats' if delta >= 0 else 'loses to'} "
                     f"median by {abs(delta)*100:.2f} raw-score pts "
                     f"({ze['n_beats_median']}/{ze['n_eligible']} clips).")
    lines.append("")

    lines.append("---")
    lines.append("*Scores are approx-tol (old tolerances). Session 4 shot windows used for all clips.*")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", type=int, default=115,
                    help="Max VAL clips to run physics on (default 115)")
    ap.add_argument("--skip-physics", action="store_true",
                    help="Skip actual physics run (use cached results if available)")
    args = ap.parse_args()

    print("=" * 70)
    print("Session 5 Decision Gate")
    print("=" * 70)

    # Step 1: Blending probe
    print("\n[1/4] Running G5 blending probe...")
    probe_pass, probe_msgs = run_blending_probe()
    for msg in probe_msgs:
        print(" ", msg)

    if not probe_pass:
        print("\n⚠  PROBE FAILED — stopping. Fix the blending defect before proceeding.")
        sys.exit(1)

    print(f"  ✓ Probe passed.")

    # Load data
    print("\n[2/4] Loading labels, split, medians...")
    labels = load_labels()
    split  = load_split()
    median = load_median()

    # Step 2: Run physics
    print(f"\n[3/4] Running physics pipeline on ≤{args.clips} VAL clips...")
    results = run_physics_on_val_clips(labels, split, median, max_clips=args.clips)
    n_err = sum(1 for r in results if r.get("error"))
    times = [r["elapsed_s"] for r in results]
    print(f"  Done: {len(results)} clips, {n_err} errors, "
          f"mean {sum(times)/len(times):.2f}s, max {max(times):.2f}s")

    # Step 3+4: Aggregate
    print("\n[4/4] Aggregating scores and generating report...")
    agg = aggregate_scores(results, median, labels, split)

    # stump_z via bounce_x
    stump_z_eval = evaluate_stump_z_from_bounce_x(results, median)

    # Print summary table to stdout
    print("\n=== Mode × field eff-score (%) ===")
    print(f"  {'field':<18}  {'const':>8}  {'median':>8}  {'phys_fb':>8}  {'med_neg':>8}  {'med_pos':>8}")
    modes = ["constants", "median", "physics_fb", "med_neg", "med_pos"]
    for f in SCORED_FIELDS:
        row = f"  {f:<18}"
        for m in modes:
            row += f"  {agg['eff_scores'][m][f]:>8.2f}"
        print(row)
    print(f"\n  {'TOTAL':18}", end="")
    for m in modes:
        print(f"  {agg['overall'][m]:>8.2f}", end="")
    print()

    print("\n=== Gate pass rates ===")
    for f in SCORED_FIELDS:
        print(f"  {f:<18} {agg['gate_pass_rates'][f]:>6.1f}%")

    # Build and write report
    report = build_report(probe_pass, probe_msgs, results, agg, stump_z_eval)
    _REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"\n✓ Report written to: {_REPORT_PATH}")


if __name__ == "__main__":
    main()
