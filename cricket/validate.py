"""
Standalone validation script — runs the cricket CV pipeline against the known
ground-truth clip and scores the result.

Usage:
    python cricket/validate.py

Imports the three pipeline modules directly to avoid the scorevision CLI/bittensor
dependency chain.
"""
import sys
import importlib
import importlib.util
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PRIVATE_TRACK = Path(__file__).parent / "turbovision" / "scorevision" / "miner" / "private_track"

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
# Ground truth for this clip
# ---------------------------------------------------------------------------
VIDEO_PATH = Path(__file__).parent / "be1382745ea10902e8ebb8bc74c3533e4f8f76eb.mp4"

GT = {
    "kph": 87.58,
    "bounce_x": 4.082,
    "stump_y": 0.046,
    "deviation": 1.555,
    "swing_angle": -0.302,
    "stump_z": 0.746,
    "release_y": 0.718,
    "release_z": 2.102,
    "bounce_y": 0.12,
    "impact_x": 2.495,
    "impact_y": 0.092,
    "impact_z": 0.373,
    "interception_distance": 1.587,
}

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

# Previous miner baseline for comparison
BASELINE = {
    "kph": 127.4, "bounce_x": 5.82, "stump_y": -0.281, "deviation": 0.0,
    "swing_angle": 0.0, "stump_z": 0.749, "release_y": -0.637,
    "release_z": 2.075, "bounce_y": -0.312, "impact_x": 1.802,
    "impact_y": -0.314, "impact_z": 0.715, "interception_distance": 4.02,
}


def score_field(pred, gt, tol):
    if pred is None:
        return 0.0
    err = abs(float(pred) - float(gt))
    return max(0.0, 1.0 - err / tol) if err < tol else 0.0


def run():
    if not VIDEO_PATH.exists():
        print(f"ERROR: video not found at {VIDEO_PATH}")
        sys.exit(1)

    # ------------------------------------------------------------------ #
    # 1. Load video metadata + reference frame
    # ------------------------------------------------------------------ #
    cap = cv2.VideoCapture(str(VIDEO_PATH))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    delivery_start = int(frame_count * 0.55)
    cap.set(cv2.CAP_PROP_POS_FRAMES, delivery_start)
    ret, ref_frame = cap.read()
    cap.release()

    print(f"Video: {VIDEO_PATH.name}  fps={fps}  frames={frame_count}")

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
    traj = tracker.track(VIDEO_PATH, homography=hom)
    print(f"Trajectory: {len(traj)} points")
    if traj:
        print(f"  first={traj[0]}  last={traj[-1]}")

    # ------------------------------------------------------------------ #
    # 4. Analyse trajectory
    # ------------------------------------------------------------------ #
    if len(traj) < 3:
        print("ERROR: trajectory too short — no predictions possible")
        fields = {}
    else:
        analyser = TrajectoryAnalyser(homography=hom, fps=fps)
        fields = analyser.analyse(traj)

    # ------------------------------------------------------------------ #
    # 5. Score
    # ------------------------------------------------------------------ #
    print()
    print(f"{'Field':<22} {'New pred':>10} {'Baseline':>10} {'GT':>8} {'Error':>8} {'Score':>7} {'Wt':>5} {'WtScore':>8}")
    print("-" * 85)
    total_new = 0.0
    total_base = 0.0
    for field, w in WEIGHTS.items():
        p = fields.get(field)
        b = BASELINE.get(field)
        g = GT[field]
        tol = TOLERANCES[field]
        s_new = score_field(p, g, tol)
        s_base = score_field(b, g, tol)
        ws_new = w * s_new
        total_new += ws_new
        total_base += w * s_base
        p_s = f"{p:.3f}" if p is not None else "None"
        b_s = f"{b:.3f}" if b is not None else "None"
        err_s = f"{abs(float(p)-g):.3f}" if p is not None else "N/A"
        flag = " ZERO" if s_new == 0.0 else ""
        print(f"{field:<22} {p_s:>10} {b_s:>10} {g:>8.3f} {err_s:>8} {s_new:>7.3f} {w:>5.2f} {ws_new:>8.3f}{flag}")

    print("-" * 85)
    print(f"{'NEW pipeline score':<22} {total_new:.3f}  ({total_new*100:.1f}%)")
    print(f"{'Baseline score':<22} {total_base:.3f}  ({total_base*100:.1f}%)")
    print(f"{'Improvement':<22} {(total_new-total_base)*100:+.1f} pts")


if __name__ == "__main__":
    run()
