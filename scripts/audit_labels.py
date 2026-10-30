#!/usr/bin/env python3
"""Phase 0 audit of the BallTrack labels (data/labels.jsonl).

Scores, on EVERY labelled ball (impact fields only where GT is non-null):
  - v2 constants (the deployed model)
  - global mean, global median
  - oracle segmented medians are in the printed distribution section only

Uses BOTH scoring schemes:
  OLD (validate.py in ibmbob): 13 fields, bounce_x .23, stump_y .18, kph .04, interception .02
  NEW (BallTrack starter pack, 2026-10-28): 12 fields, interception zero weight,
      bounce_x/kph/stump_y/stump_z/impact_x .10 each,
      deviation/swing_angle/release_y/release_z/impact_y .08 each, bounce_y/impact_z .05 each
Tolerances are known only for OLD. For NEW the starter pack says "strict tolerance-based
decay" without publishing numbers, so NEW scores reuse OLD tolerances per field and are
labelled APPROXIMATE — good for ranking baselines, not a validator guarantee.
"""
import json, statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROWS = [json.loads(l) for l in (ROOT/"data"/"labels.jsonl").open() if l.strip()]
FIELDS = ["kph","release_y","release_z","bounce_x","bounce_y","impact_x","impact_y",
          "impact_z","stump_y","stump_z","swing_angle","deviation"]
TOL = {"kph":3.0,"release_y":0.15,"release_z":0.15,"bounce_x":0.25,"bounce_y":0.15,
       "impact_x":0.25,"impact_y":0.15,"impact_z":0.15,"stump_y":0.12,"stump_z":0.12,
       "swing_angle":2.0,"deviation":2.0,"interception_distance":0.25}
W_OLD = {"bounce_x":0.23,"stump_y":0.18,"deviation":0.13,"swing_angle":0.11,"stump_z":0.11,
         "kph":0.04,"release_y":0.03,"release_z":0.03,"bounce_y":0.03,"impact_x":0.03,
         "impact_y":0.03,"impact_z":0.03,"interception_distance":0.02}
W_NEW = {"bounce_x":0.10,"kph":0.10,"stump_y":0.10,"stump_z":0.10,"impact_x":0.10,
         "deviation":0.08,"swing_angle":0.08,"release_y":0.08,"release_z":0.08,
         "impact_y":0.08,"bounce_y":0.05,"impact_z":0.05}
CONST = {"kph":87.5,"bounce_x":4.05,"stump_y":0.04,"deviation":1.55,"swing_angle":-0.25,
         "stump_z":0.75,"release_y":0.65,"release_z":2.10,"bounce_y":0.10,"impact_x":2.50,
         "impact_y":0.08,"impact_z":0.38,"interception_distance":1.55}

def score(pred, gt, weights):
    """Weighted score renormalised over fields whose GT is present (nulls skipped)."""
    tot = wsum = 0.0
    for f, w in weights.items():
        if gt.get(f) is None:
            continue
        wsum += w
        err = abs(pred[f]-gt[f]) if pred.get(f) is not None else 1e9
        tot += w * max(0.0, 1-err/TOL[f]) if err < TOL[f] else 0.0
    return tot/wsum if wsum else 0.0

def main():
    print(f"rows={len(ROWS)}")
    gts = [r["groundtruth"] for r in ROWS]
    print("\n== null rates / distributions ==")
    stats = {}
    for f in FIELDS:
        vals = [g[f] for g in gts if g.get(f) is not None]
        stats[f] = vals
        qs = st.quantiles(vals, n=20)
        print(f"{f:12s} n={len(vals):5d} null={len(gts)-len(vals):5d} "
              f"mean={st.mean(vals):8.3f} median={st.median(vals):8.3f} sd={st.pstdev(vals):7.3f} "
              f"p5={qs[0]:8.3f} p95={qs[-1]:8.3f} min={min(vals):8.3f} max={max(vals):8.3f}")
    mean_pred = {f: st.mean(v) for f, v in stats.items()}; mean_pred["interception_distance"]=1.55
    med_pred  = {f: st.median(v) for f, v in stats.items()}; med_pred["interception_distance"]=1.55
    for name, weights in [("OLD", W_OLD), ("NEW(approx tol)", W_NEW)]:
        for label, pred in [("v2 constants", CONST), ("global mean", mean_pred), ("global median", med_pred)]:
            s = [score(pred, g, weights) for g in gts]
            print(f"{name:16s} {label:14s} mean score = {st.mean(s)*100:5.1f}%  median = {st.median(s)*100:5.1f}%")
    # kph clusters — the obvious segmentation
    kph = stats["kph"]
    bands = {"<80":0,"80-100":0,"100-120":0,"120-135":0,">=135":0}
    for v in kph:
        bands["<80" if v<80 else "80-100" if v<100 else "100-120" if v<120 else "120-135" if v<135 else ">=135"] += 1
    print("\nkph bands:", {k: f"{v} ({v/len(kph)*100:.1f}%)" for k,v in bands.items()})
    # correlations that matter for joint forecasting
    def corr(a,b):
        pairs=[(g[a],g[b]) for g in gts if g.get(a) is not None and g.get(b) is not None]
        xs=[p[0] for p in pairs]; ys=[p[1] for p in pairs]
        mx,my=st.mean(xs),st.mean(ys)
        return sum((x-mx)*(y-my) for x,y in pairs)/(sum((x-mx)**2 for x in xs)*sum((y-my)**2 for y in ys))**.5
    for a,b in [("kph","bounce_x"),("kph","stump_z"),("bounce_x","stump_z"),("bounce_x","impact_x"),("release_y","bounce_y"),("release_y","stump_y")]:
        print(f"corr {a} vs {b}: {corr(a,b):+.2f}")

if __name__ == "__main__":
    main()
