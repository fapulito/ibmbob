"""
Standalone validation script — runs the cricket CV pipeline against the local
ground-truth fixtures and scores the result.

Usage:
    python cricket/validate.py               # both fixtures
    python cricket/validate.py be13          # one fixture
    python cricket/validate.py be13 efc0

Imports the three pipeline modules directly to avoid the scorevision CLI/bittensor
dependency chain.

Two implementations are scored side by side for every fixture:

  "stub"  — TrajectoryAnalyser.analyse(), the production path. Returns 13
            hardcoded constants and never reads its trajectory argument.
  "real"  — the physics pipeline that sits in the same file but is never called:
            _analyse_endon / _analyse_sideon → _select_confident_fields →
            _fill_defaults. Composed here, in the harness, so that production
            behaviour is untouched.
"""
import json
import sys
import importlib
import importlib.util
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PRIVATE_TRACK = Path(__file__).parent / "turbovision" / "scorevision" / "miner" / "private_track"
FIXTURE_DIR = Path(__file__).parent / "turbovision" / "data-training" / "cricket"

# stem -> (video filename, groundtruth filename)
FIXTURES = {
    "be13": ("be1382745ea10902e8ebb8bc74c3533e4f8f76eb.mp4", "groundtruth-be13.json"),
    "efc0": ("efc05ed4ef0b266d16385ce497d742e7ae75b4b0.mp4", "groundtruth-efc0.json"),
}

# ---------------------------------------------------------------------------
# Imports — use importlib to load files directly, bypassing package __init__
# and avoiding the logging.py shadow in private_track/
# ---------------------------------------------------------------------------
import cv2
import numpy as np

def _import_from_file(module_name, filepath):
    """Load a .py file as a module without touching sys.path."""
    spec = importlib.util.spec_from_file_location(module_name, str(filepath))
    mod = importlib.util.module_from_spec(spec)
    # Pre-register so relative imports within the module resolve correctly
    sys.modules[module_name] = mod
    # Patch: replace 'logging' import inside the module with stdlib logging
    # by ensuring stdlib logging is already cached before exec
    import logging as _stdlib_logging  # noqa — ensure it is cached
    spec.loader.exec_module(mod)
    return mod

# Stub out the private_track logging module before loading our modules
# so "import logging" inside pitch_homography.py hits stdlib, not the local file
import logging as _logging  # pre-cache stdlib logging
import types as _types
_pt_logging_stub = _types.ModuleType("scorevision.miner.private_track.logging")
_pt_logging_stub.logger = _logging.getLogger("cricket_pipeline")
sys.modules["scorevision.miner.private_track.logging"] = _pt_logging_stub

ph_mod = _import_from_file("scorevision.miner.private_track.pitch_homography",
                            PRIVATE_TRACK / "pitch_homography.py")
bt_mod = _import_from_file("scorevision.miner.private_track.ball_tracker",
                            PRIVATE_TRACK / "ball_tracker.py")
tr_mod = _import_from_file("scorevision.miner.private_track.trajectory",
                            PRIVATE_TRACK / "trajectory.py")

PitchHomography    = ph_mod.PitchHomography
BallTracker        = bt_mod.BallTracker
TrajectoryAnalyser = tr_mod.TrajectoryAnalyser

# ---------------------------------------------------------------------------
# Scoring config (mirrors the validator's cricket weights/tolerances)
# ---------------------------------------------------------------------------
WEIGHTS = {
    "bounce_x": 0.23, "stump_y": 0.18, "deviation": 0.13,
    "swing_angle": 0.11, "stump_z": 0.11, "kph": 0.04,
    "release_y": 0.03, "release_z": 0.03, "bounce_y": 0.03,
    "impact_x": 0.03, "impact_y": 0.03, "impact_z": 0.03,
    "interception_distance": 0.02,
}

TOLERANCES = {
    "kph": 3.0, "release_y": 0.15, "release_z": 0.15,
    "bounce_x": 0.25, "bounce_y": 0.15, "impact_x": 0.25,
    "impact_y": 0.15, "impact_z": 0.15, "interception_distance": 0.25,
    "stump_y": 0.12, "stump_z": 0.12, "swing_angle": 2.0, "deviation": 2.0,
}


def load_fixture(stem):
    """Return (video_path, groundtruth, other_miner_prediction) for a fixture stem.

    Ground truth is read from the JSON's `groundtruth` block so it cannot drift
    from the checked-in fixture. The `miner_response.prediction` block is a
    DIFFERENT miner's recorded answer, not ground truth — it is returned only as
    a reference column.
    """
    video_name, gt_name = FIXTURES[stem]
    video_path = FIXTURE_DIR / video_name
    with open(FIXTURE_DIR / gt_name, "r", encoding="utf-8") as fh:
        blob = json.load(fh)
    groundtruth = blob["groundtruth"]
    other_miner = blob.get("miner_response", {}).get("prediction", {})
    return video_path, groundtruth, other_miner


def score_field(pred, gt, tol):
    if pred is None:
        return 0.0
    err = abs(float(pred) - float(gt))
    return max(0.0, 1.0 - err / tol) if err < tol else 0.0


def total_score(fields, groundtruth):
    total = 0.0
    for field, w in WEIGHTS.items():
        total += w * score_field(fields.get(field), groundtruth[field], TOLERANCES[field])
    return total


# ---------------------------------------------------------------------------
# The real (never-called) physics pipeline, composed here rather than in
# production code. trajectory.py is NOT modified: analyse() keeps returning its
# constants, and the private helpers are invoked directly from the harness.
# ---------------------------------------------------------------------------
def real_pipeline(analyser, hom, traj):
    """Compose the physics path the way trajectory.py was evidently designed to.

    Returns (final_fields, raw_physics_fields, overrides, diagnostics).
    """
    raw = analyser._analyse_endon(traj) if hom.is_endon else analyser._analyse_sideon(traj)
    defaults = analyser._default_fields()
    overrides = analyser._select_confident_fields(defaults, raw, traj)
    fields = dict(defaults)
    fields.update(overrides)
    fields = analyser._fill_defaults(fields)
    return fields, raw, overrides


def gate_diagnostics(analyser, hom, traj):
    """Recompute the numbers _select_confident_fields gates on."""
    pts = []
    for fn, px, py in traj:
        if hom.is_endon:
            x_m, y_m = hom.pixel_to_metres(px, py)
        else:
            x_m, _z = hom.pixel_to_metres(px, py)
            y_m = 0.0
        pts.append((x_m, y_m))
    if len(pts) < 2:
        return {"pts": len(pts), "depth_travel": None, "y_spread": None}
    xs = np.array([p[0] for p in pts])
    ys = np.array([p[1] for p in pts])
    return {
        "pts": len(pts),
        "depth_travel": float(abs(xs[0] - xs[-1])),
        "y_spread": float(abs(ys.max() - ys.min())),
    }


def run_fixture(stem):
    video_path, GT, OTHER_MINER = load_fixture(stem)
    if not video_path.exists():
        print(f"ERROR: video not found at {video_path}")
        return None

    print("=" * 100)
    print(f"FIXTURE {stem}: {video_path.name}")
    print("=" * 100)

    # ------------------------------------------------------------------ #
    # 1. Load video metadata + reference frame
    # ------------------------------------------------------------------ #
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    delivery_start = int(frame_count * 0.55)
    cap.set(cv2.CAP_PROP_POS_FRAMES, delivery_start)
    ret, ref_frame = cap.read()
    cap.release()

    print(f"Video: fps={fps}  frames={frame_count}")

    # ------------------------------------------------------------------ #
    # 2. Build homography
    # ------------------------------------------------------------------ #
    hom = PitchHomography(ref_frame if ret else None)
    camera_type = getattr(hom, 'camera_type', 'unknown')
    print(f"Homography: valid={hom.valid}  px/m={hom.pixels_per_metre_x:.2f}  camera={camera_type}")
    if camera_type == "end_on":
        print(f"  end-on stump_px={hom._stump_px_endon}  px/m_depth={hom._px_per_m_depth:.2f}  px/m_lat={hom._px_per_m_lat:.2f}")

    # ------------------------------------------------------------------ #
    # 3. Track ball
    # ------------------------------------------------------------------ #
    tracker = BallTracker(model_path=None)
    print("Tracking ball...")
    traj = tracker.track(video_path, homography=hom)
    print(f"Trajectory: {len(traj)} points")
    if traj:
        print(f"  first={traj[0]}  last={traj[-1]}")

    # ------------------------------------------------------------------ #
    # 4. Analyse trajectory — production stub AND the real physics path
    # ------------------------------------------------------------------ #
    analyser = TrajectoryAnalyser(homography=hom, fps=fps)
    stub_fields = analyser.analyse(traj)          # production behaviour, unchanged

    if len(traj) < 3:
        print("NOTE: trajectory shorter than 3 points — real pipeline cannot run, "
              "it would return _default_fields()")
        real_fields = analyser._fill_defaults({})
        raw, overrides = {}, {}
        diag = {"pts": len(traj), "depth_travel": None, "y_spread": None}
    else:
        real_fields, raw, overrides = real_pipeline(analyser, hom, traj)
        diag = gate_diagnostics(analyser, hom, traj)

    print()
    print("Real-pipeline diagnostics:")
    print(f"  world points          : {diag['pts']}")
    print(f"  depth_travel (m)      : "
          f"{diag['depth_travel'] if diag['depth_travel'] is None else round(diag['depth_travel'], 3)}"
          f"   (gates: >6.0 lateral, >8.0 depth)")
    print(f"  y_spread (m)          : "
          f"{diag['y_spread'] if diag['y_spread'] is None else round(diag['y_spread'], 4)}"
          f"   (gate: >0.05)")
    print(f"  raw physics fields    : {raw if raw else '{} (empty — <3 usable points)'}")
    print(f"  fields past the gates : {sorted(overrides) if overrides else 'NONE — all defaults'}")
    if not overrides:
        print("  => real pipeline output IS _default_fields() (the documented 74% baseline),")
        print("     not a physics result. This is a tracker/homography quality finding.")

    # ------------------------------------------------------------------ #
    # 5. Score
    # ------------------------------------------------------------------ #
    print()
    hdr = (f"{'Field':<22} {'stub':>9} {'real':>9} {'GT':>9} "
           f"{'sErr':>7} {'rErr':>7} {'sScore':>7} {'rScore':>7} {'Wt':>5} {'sWt':>7} {'rWt':>7}")
    print(hdr)
    print("-" * len(hdr))
    total_stub = 0.0
    total_real = 0.0
    total_other = 0.0
    for field, w in WEIGHTS.items():
        g = GT[field]
        tol = TOLERANCES[field]
        p_stub = stub_fields.get(field)
        p_real = real_fields.get(field)
        p_other = OTHER_MINER.get(field)
        s_stub = score_field(p_stub, g, tol)
        s_real = score_field(p_real, g, tol)
        total_stub += w * s_stub
        total_real += w * s_real
        total_other += w * score_field(p_other, g, tol)
        f_stub = f"{p_stub:.3f}" if p_stub is not None else "None"
        f_real = f"{p_real:.3f}" if p_real is not None else "None"
        e_stub = f"{abs(float(p_stub)-g):.3f}" if p_stub is not None else "N/A"
        e_real = f"{abs(float(p_real)-g):.3f}" if p_real is not None else "N/A"
        print(f"{field:<22} {f_stub:>9} {f_real:>9} {g:>9.3f} "
              f"{e_stub:>7} {e_real:>7} {s_stub:>7.3f} {s_real:>7.3f} {w:>5.2f} "
              f"{w*s_stub:>7.3f} {w*s_real:>7.3f}")

    print("-" * len(hdr))
    print(f"{'TOTAL stub (production)':<32} {total_stub:.4f}  ({total_stub*100:.1f}%)")
    print(f"{'TOTAL real physics pipeline':<32} {total_real:.4f}  ({total_real*100:.1f}%)")
    print(f"{'TOTAL other miner (reference)':<32} {total_other:.4f}  ({total_other*100:.1f}%)")
    print(f"{'real - stub':<32} {(total_real-total_stub)*100:+.1f} pts")
    print()

    return {
        "stem": stem,
        "stub": total_stub,
        "real": total_real,
        "other": total_other,
        "gates_passed": sorted(overrides),
        "diag": diag,
        "camera": camera_type,
        "hom_valid": hom.valid,
        "traj_pts": len(traj),
    }


def run(stems=None):
    stems = stems or list(FIXTURES)
    results = []
    for stem in stems:
        if stem not in FIXTURES:
            print(f"ERROR: unknown fixture '{stem}'. Known: {', '.join(FIXTURES)}")
            sys.exit(1)
        r = run_fixture(stem)
        if r:
            results.append(r)

    if len(results) > 1:
        print("=" * 100)
        print("SUMMARY")
        print("=" * 100)
        print(f"{'fixture':<10} {'camera':<10} {'hom':<6} {'pts':>5} "
              f"{'stub':>8} {'real':>8} {'other':>8}  gates passed")
        for r in results:
            print(f"{r['stem']:<10} {r['camera']:<10} {str(r['hom_valid']):<6} {r['traj_pts']:>5} "
                  f"{r['stub']*100:>7.1f}% {r['real']*100:>7.1f}% {r['other']*100:>7.1f}%  "
                  f"{r['gates_passed'] or 'none (defaults)'}")
        mean_stub = sum(r["stub"] for r in results) / len(results)
        mean_real = sum(r["real"] for r in results) / len(results)
        print(f"\nmean over {len(results)} fixtures: stub={mean_stub*100:.1f}%  real={mean_real*100:.1f}%")
        print("n is far too small to justify switching or not switching.")

    return results


if __name__ == "__main__":
    run(sys.argv[1:] or None)
