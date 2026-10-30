#!/usr/bin/env python3
"""
validate_balltrack.py — BallTrack scoring harness (v4, approx-tol)

Weights: bounce_x/kph/stump_y/stump_z/impact_x=.10;
         deviation/swing_angle/release_y/release_z/impact_y=.08;
         bounce_y/impact_z=.05
Tolerances (OLD, approx): kph=3, bounce_x=.25, stump_y=.12, stump_z=.12,
         release_y/z=.15, bounce_y=.15, impact_x=.25, impact_y/z=.15, angles=2.0

Scored only over non-null GT fields; weights renormalised per ball.
All score claims are labelled approx-tol.

Usage:
  python validate_balltrack.py constants [val|train|test|all]
  python validate_balltrack.py median [val|train|test|all]
  python validate_balltrack.py mean [val|train|test|all]
  python validate_balltrack.py /path/to/predictions.jsonl [val|train|test|all]
"""

import json
import math
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_HERE = Path(__file__).parent
DATA_DIR = _HERE / "data-training" / "balltrack"
LABELS_FILE = DATA_DIR / "labels.jsonl"
SPLIT_FILE  = DATA_DIR / "split.json"
MEDIAN_FILE = DATA_DIR / "median_baseline.json"

# ---------------------------------------------------------------------------
# NEW weights (v4, from requirements.md Measured facts)
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

# Sanity-check weights sum to 1.0
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, "Weights must sum to 1.0"

# ---------------------------------------------------------------------------
# OLD tolerances (approx — requirements.md: "old tolerances as an approximation")
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# v2 constants — exact values from trajectory._tuned_constant_fields()
# (requirements.md: "v2 constants (kph 87.5, bounce_x 4.05) describe the be13 clip")
# ---------------------------------------------------------------------------
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


def score_field(pred_val, gt_val, field):
    """Linear decay: 1.0 at 0 error, 0.0 at tolerance, clipped to [0,1]."""
    tol = TOLERANCES[field]
    err = abs(pred_val - gt_val)
    return max(0.0, 1.0 - err / tol)


def score_ball(prediction, groundtruth):
    """
    Score one ball. Renormalise weights over non-null GT fields.
    Returns (ball_total, {field: field_score_contribution}).
    """
    # Identify which GT fields are non-null and scored
    available = [f for f in SCORED_FIELDS if groundtruth.get(f) is not None]
    if not available:
        return 0.0, {}

    # Renormalise weights over available fields
    raw_weight_sum = sum(WEIGHTS[f] for f in available)
    renorm = {f: WEIGHTS[f] / raw_weight_sum for f in available}

    field_scores = {}
    total = 0.0
    for f in available:
        pv = prediction.get(f)
        gv = groundtruth[f]
        if pv is None:
            fs = 0.0
        else:
            fs = score_field(float(pv), float(gv), f)
        field_scores[f] = renorm[f] * fs
        total += field_scores[f]

    return total, field_scores


def load_labels():
    labels = {}
    with open(LABELS_FILE) as f:
        for line in f:
            rec = json.loads(line)
            labels[rec["challenge_path"]] = rec["groundtruth"]
    return labels


def load_split():
    with open(SPLIT_FILE) as f:
        return json.load(f)


def load_median():
    with open(MEDIAN_FILE) as f:
        return json.load(f)


def compute_mean(labels):
    """Compute per-field mean over all labels (ignoring nulls)."""
    sums = {f: 0.0 for f in SCORED_FIELDS}
    counts = {f: 0 for f in SCORED_FIELDS}
    for gt in labels.values():
        for f in SCORED_FIELDS:
            v = gt.get(f)
            if v is not None:
                sums[f] += float(v)
                counts[f] += 1
    return {f: sums[f] / counts[f] if counts[f] > 0 else 0.0 for f in SCORED_FIELDS}


def run_scoring(predictor_fn, split_labels):
    """
    Run scoring over a dict of {challenge_path: groundtruth}.
    predictor_fn(challenge_path, groundtruth) -> prediction dict
    Returns (overall_score, per_field_accumulated, n_balls).
    """
    field_totals = {f: 0.0 for f in SCORED_FIELDS}
    grand_total = 0.0
    n = 0

    for cp, gt in split_labels.items():
        pred = predictor_fn(cp, gt)
        ball_total, field_scores = score_ball(pred, gt)
        grand_total += ball_total
        for f, s in field_scores.items():
            field_totals[f] += s
        n += 1

    return grand_total / n if n > 0 else 0.0, {f: v / n for f, v in field_totals.items()}, n


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    predictor_arg = args[0]
    split_name    = args[1] if len(args) > 1 else "val"

    labels = load_labels()
    split  = load_split()

    if split_name == "all":
        split_labels = labels
    else:
        split_labels = {cp: gt for cp, gt in labels.items() if split.get(cp) == split_name}

    if not split_labels:
        print(f"ERROR: no labels found for split={split_name!r}")
        sys.exit(1)

    # Build predictor
    if predictor_arg == "constants":
        consts = dict(V2_CONSTANTS)
        predictor_fn = lambda cp, gt: consts
        label = "constants"
    elif predictor_arg == "median":
        medians = load_median()
        predictor_fn = lambda cp, gt: medians
        label = "median"
    elif predictor_arg == "mean":
        mean_vals = compute_mean(labels)  # computed on ALL labels (not just split)
        predictor_fn = lambda cp, gt: mean_vals
        label = "mean"
    else:
        # Assume it's a path to a predictions JSONL: {challenge_path, prediction: {...}}
        preds_path = Path(predictor_arg)
        preds = {}
        with open(preds_path) as f:
            for line in f:
                rec = json.loads(line)
                preds[rec["challenge_path"]] = rec["prediction"]
        predictor_fn = lambda cp, gt: preds.get(cp, {})
        label = preds_path.name

    score, per_field, n = run_scoring(predictor_fn, split_labels)

    # Report
    print(f"\n=== BallTrack scoring (approx-tol) ===")
    print(f"  mode={label}  split={split_name}  n={n}")
    print(f"  TOTAL: {score*100:.2f}%\n")
    print(f"  {'field':<14}  {'contrib %':>10}  {'weight':>8}  {'eff-score %':>12}")
    print(f"  {'-'*50}")
    for f in SCORED_FIELDS:
        w = WEIGHTS[f]
        contrib = per_field[f] * 100
        # effective field score = contrib / weight (shows how well we did on that field)
        eff = (per_field[f] / w * 100) if w > 0 else 0.0
        print(f"  {f:<14}  {contrib:>10.3f}  {w:>8.2f}  {eff:>12.2f}")


if __name__ == "__main__":
    main()
