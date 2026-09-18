"""
Standalone validation script — runs the cricket CV pipeline against the local
ground-truth fixtures and scores the result.

Usage:
    python cricket/validate.py               # all fixtures with a groundtruth
    python cricket/validate.py be13          # one fixture
    python cricket/validate.py be13 efc0
    python cricket/validate.py f81d          # behaviour-only probe, no score

Imports the three pipeline modules directly (by file path) to avoid the
scorevision CLI/bittensor dependency chain, exactly as production's own
container does not need bittensor either.

Fixtures are resolved from BOTH `data-training/cricket/` and its `foundation/`
subdirectory, so the harness does not care which layout a given fixture is
checked in under.

Three modes are scored side by side for every scoreable fixture, by calling
production's own `TrajectoryAnalyser.analyse()` under each value of
`CRICKET_PREDICTOR_MODE`:

  "constants" — always _tuned_constant_fields(), the v2.5 scoring-tuned
                literals and the rollback path.
  "physics"   — always the trajectory pipeline (_analyse_endon/_analyse_sideon
                -> _select_confident_fields -> _fill_defaults), falling back to
                _default_fields() below 3 points or on any internal failure.
  "auto"      — physics iff hom.valid, else constants. This is what production
                actually runs.

The harness does NOT re-compose the physics path itself (it used to, under the
now-retired "stub"/"real" vocabulary) — it only ever calls analyse(), so it
cannot silently drift from what predictor.py actually does. The private
_select_confident_fields()/_analyse_* helpers are still called here, but only
to print WHY a mode resolved the way it did (gate diagnostics), never to
produce the scored answer.
"""
import importlib
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
TURBOVISION   = Path(__file__).parent / "turbovision"
PRIVATE_TRACK = TURBOVISION / "scorevision" / "miner" / "private_track"
VALIDATOR_SCORING = TURBOVISION / "scorevision" / "validator" / "central" / "private_track" / "scoring.py"
FIXTURE_DIR   = TURBOVISION / "data-training" / "cricket"
FIXTURE_SUBDIRS = (FIXTURE_DIR, FIXTURE_DIR / "foundation", FIXTURE_DIR / "groundcheck")

# stem -> (video filename, groundtruth filename or None)
# groundtruth=None means the fixture is a behaviour-only probe: it can be run
# through the pipeline and its diagnostics reported, but it is never scored
# against anything, because no groundtruth exists for it.
FIXTURES = {
    "be13": ("be1382745ea10902e8ebb8bc74c3533e4f8f76eb.mp4", "groundtruth-be13.json"),
    "efc0": ("efc05ed4ef0b266d16385ce497d742e7ae75b4b0.mp4", "groundtruth-efc0.json"),
    "8b97": ("8b97ef5831a40782462222c847b5cdd3518101bd.mp4", "groundtruth-8b97.json"),
    "f81d": ("f81d092b6117be1126e0d6be97220b3f9a2870eb.mp4", "groundtruth-f81d.json"),
    "9ef5": ("9ef5c0e6e68a01d5435499bc0527c04386e527fc.mp4", "groundtruth-9ef5.json"),
    "98e5": ("98e537a2a3555da28ca7eea3227babb61df228d1.mp4", "groundtruth-98e5.json"),
    "6a79": ("6a79fbe0fd6792126c69087568f7f08318dcf449.mp4", "groundtruth-6a79.json"),
    "bad1": ("bad1530d039b7146a8ce4a1b1a6b29502c3c9491.mp4", "groundtruth-bad1.json"),
}

# Fixtures that have a groundtruth and are therefore scoreable.
SCOREABLE_FIXTURES = tuple(stem for stem, (_, gt) in FIXTURES.items() if gt is not None)

MODES = ("constants", "physics", "auto")

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
# shot_selection.py does `from scorevision.miner.private_track.pitch_homography
# import PitchHomography` internally — because ph_mod above was already
# registered in sys.modules under that exact dotted name before this load,
# that import resolves to the SAME PitchHomography class the harness uses
# everywhere else, not a second copy.
sel_mod = _import_from_file("scorevision.miner.private_track.shot_selection",
                             PRIVATE_TRACK / "shot_selection.py")

PitchHomography    = ph_mod.PitchHomography
BallTracker        = bt_mod.BallTracker
TrajectoryAnalyser = tr_mod.TrajectoryAnalyser
select_delivery_shot = sel_mod.select_delivery_shot
MODE_ENV_VAR        = tr_mod._MODE_ENV_VAR  # "CRICKET_PREDICTOR_MODE" — read from production, not restated

# Fallback calibration fraction — mirrors predictor.py's _FALLBACK_CALIBRATION_FRAC,
# used only when shot selection finds no shot scoring as a pitch view at all.
_FALLBACK_CALIBRATION_FRAC = 0.55

# ---------------------------------------------------------------------------
# Scoring config — verified against, and preferably LOADED FROM, the
# validator's own scoring.py, so this harness cannot silently disagree with
# production. If the validator's dependency chain (bittensor etc.) is not
# importable in this environment, fall back to a local copy and say so loudly:
# the fallback below is checked byte-for-byte against production whenever the
# import succeeds (see _verify_scoring_parity()), so drift is caught the
# moment this script runs in an environment that CAN import it.
# ---------------------------------------------------------------------------
_FALLBACK_WEIGHTS = {
    "bounce_x": 0.23, "stump_y": 0.18, "deviation": 0.13,
    "swing_angle": 0.11, "stump_z": 0.11, "kph": 0.04,
    "release_y": 0.03, "release_z": 0.03, "bounce_y": 0.03,
    "impact_x": 0.03, "impact_y": 0.03, "impact_z": 0.03,
    "interception_distance": 0.02,
}

_FALLBACK_TOLERANCES = {
    "kph": 3.0, "release_y": 0.15, "release_z": 0.15,
    "bounce_x": 0.25, "bounce_y": 0.15, "impact_x": 0.25,
    "impact_y": 0.15, "impact_z": 0.15, "interception_distance": 0.25,
    "stump_y": 0.12, "stump_z": 0.12, "swing_angle": 2.0, "deviation": 2.0,
}


def _fallback_score_numeric_match(predicted, actual, tolerance):
    """Local copy of scoring.py's _score_numeric_match, for when the real one
    cannot be imported. Mirrors it EXACTLY, including the >= tolerance boundary
    and the near-boundary epsilon clamp, so a fallback run still agrees with
    production at the boundary."""
    if predicted is None or actual is None:
        return 0.0
    try:
        distance = abs(float(predicted) - float(actual))
    except (TypeError, ValueError):
        return 0.0
    if tolerance <= 0:
        return 1.0 if distance == 0 else 0.0
    if distance >= tolerance or abs(distance - tolerance) <= 1e-12:
        return 0.0
    return max(0.0, 1.0 - (distance / tolerance))


def _load_validator_scoring():
    """Try to import the real validator scoring module by file path, bypassing
    scorevision/__init__.py's CLI/bittensor import chain the same way the
    pipeline modules above are loaded. Returns the module, or None."""
    try:
        # scoring.py does `from scorevision.utils.actions import ...` and
        # `from scorevision.utils.settings import ...` — absolute imports that
        # need the `scorevision` package resolvable, so turbovision/ must be on
        # sys.path for this one import only.
        turbovision_str = str(TURBOVISION)
        added = turbovision_str not in sys.path
        if added:
            sys.path.insert(0, turbovision_str)
        try:
            spec = importlib.util.spec_from_file_location(
                "scorevision.validator.central.private_track.scoring", str(VALIDATOR_SCORING)
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
        finally:
            if added:
                sys.path.remove(turbovision_str)
    except Exception as exc:  # pragma: no cover - environment dependent
        print(f"WARNING: could not import validator scoring.py directly ({exc!r}); "
              f"using the harness's local fallback copy of WEIGHTS/TOLERANCES/score_field. "
              f"This copy is checked against production whenever the import DOES succeed.")
        return None


_scoring_mod = _load_validator_scoring()

if _scoring_mod is not None:
    # Loaded from production: WEIGHTS/TOLERANCES restricted to the cricket
    # fields with nonzero weight (the exact/metadata fields carry weight 0.0
    # and this harness never predicts them).
    WEIGHTS = {k: v for k, v in _scoring_mod._CRICKET_FIELD_WEIGHTS.items() if v > 0}
    TOLERANCES = dict(_scoring_mod._CRICKET_FIELD_TOLERANCES)
    _score_numeric_match = _scoring_mod._score_numeric_match
    print(f"Scoring parity: loaded WEIGHTS/TOLERANCES directly from {VALIDATOR_SCORING}")
else:
    WEIGHTS = dict(_FALLBACK_WEIGHTS)
    TOLERANCES = dict(_FALLBACK_TOLERANCES)
    _score_numeric_match = _fallback_score_numeric_match

assert set(WEIGHTS) == set(TOLERANCES), "every scored field must carry both a weight and a tolerance"
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, f"WEIGHTS must sum to 1.0, got {sum(WEIGHTS.values())}"


def _verify_scoring_parity():
    """When the real scoring module IS importable, assert the fallback copy
    above still agrees with it exactly. Run unconditionally at import time so a
    fallback-mode run is never silently stale."""
    live = _load_validator_scoring() if _scoring_mod is None else _scoring_mod
    if live is None:
        print("Scoring parity: NOT VERIFIED this run (validator scoring.py not importable). "
              "Using the local fallback copy, last hand-verified against scoring.py by inspection.")
        return
    live_weights = {k: v for k, v in live._CRICKET_FIELD_WEIGHTS.items() if v > 0}
    live_tolerances = dict(live._CRICKET_FIELD_TOLERANCES)
    assert live_weights == _FALLBACK_WEIGHTS, (
        f"harness fallback WEIGHTS drifted from production: {live_weights} != {_FALLBACK_WEIGHTS}")
    assert live_tolerances == _FALLBACK_TOLERANCES, (
        f"harness fallback TOLERANCES drifted from production: {live_tolerances} != {_FALLBACK_TOLERANCES}")
    # Boundary semantics: distance == tolerance must score exactly 0 in both.
    for field, tol in live_tolerances.items():
        prod = live._score_numeric_match(0.0, tol, tol)
        fallback = _fallback_score_numeric_match(0.0, tol, tol)
        assert prod == fallback == 0.0, (field, prod, fallback)
    print("Scoring parity: VERIFIED — fallback WEIGHTS/TOLERANCES/boundary semantics match "
          f"{VALIDATOR_SCORING} exactly.")


_verify_scoring_parity()


# ---------------------------------------------------------------------------
# Fixture resolution — searches FIXTURE_DIR and FIXTURE_DIR/foundation, so a
# fixture registered here resolves regardless of which of the two directories
# it actually lives in.
# ---------------------------------------------------------------------------

def _find_fixture_file(filename):
    for d in FIXTURE_SUBDIRS:
        candidate = d / filename
        if candidate.exists():
            return candidate
    return None


def load_fixture(stem):
    """Return (video_path_or_None, groundtruth_or_None, other_miner_prediction).

    Ground truth is read from the JSON's `groundtruth` block so it cannot drift
    from the checked-in fixture. The `miner_response.prediction` block is a
    DIFFERENT miner's recorded answer, not ground truth — it is returned only as
    a reference column. Every local groundtruth-*.json carries a foreign
    miner_hotkey; none of them are ours.
    """
    video_name, gt_name = FIXTURES[stem]
    video_path = _find_fixture_file(video_name)
    if gt_name is None:
        return video_path, None, {}
    gt_path = _find_fixture_file(gt_name)
    if gt_path is None:
        return video_path, None, {}
    with open(gt_path, "r", encoding="utf-8") as fh:
        blob = json.load(fh)
    groundtruth = blob["groundtruth"]
    other_miner = blob.get("miner_response", {}).get("prediction", {})
    return video_path, groundtruth, other_miner


def score_field(pred, gt, tol):
    return _score_numeric_match(pred, gt, tol)


def total_score(fields, groundtruth):
    total = 0.0
    for field, w in WEIGHTS.items():
        total += w * score_field(fields.get(field), groundtruth[field], TOLERANCES[field])
    return total


# ---------------------------------------------------------------------------
# Diagnostics only — never used to produce the scored answer. The scored
# answer for every mode comes exclusively from analyser.analyse(); these
# helpers exist purely to explain WHY a mode resolved the way it did.
# ---------------------------------------------------------------------------

def gate_diagnostics(analyser, hom, traj):
    """World-point count / depth-travel / y-spread the confidence gate reads,
    and which fields it would pass. Read-only: does not affect any score."""
    pts = []
    for fn, px, py in traj:
        if hom.is_endon:
            x_m, y_m = hom.pixel_to_metres(px, py)
        else:
            x_m, _z = hom.pixel_to_metres(px, py)
            y_m = 0.0
        pts.append((x_m, y_m))
    if len(pts) < 2:
        return {"pts": len(pts), "depth_travel": None, "y_spread": None, "gates_passed": []}

    xs = np.array([p[0] for p in pts])
    ys = np.array([p[1] for p in pts])
    depth_travel = float(abs(xs[0] - xs[-1]))
    y_spread = float(abs(ys.max() - ys.min()))

    gates_passed = []
    if len(traj) >= 3:
        raw = analyser._analyse_endon(traj) if hom.is_endon else analyser._analyse_sideon(traj)
        if raw:
            defaults = analyser._default_fields()
            overrides = analyser._select_confident_fields(defaults, raw, traj)
            gates_passed = sorted(overrides)

    return {"pts": len(pts), "depth_travel": depth_travel, "y_spread": y_spread,
            "gates_passed": gates_passed}


def which_constant_set(fields, analyser):
    """Identify whether `fields` (an analyse() result) equals one of the two
    known fallback constant sets, purely for reporting. Neither comparison
    changes the score — the score is always total_score(fields, GT)."""
    if fields == analyser._tuned_constant_fields():
        return "_tuned_constant_fields (v2.5 tuned constants)"
    if fields == analyser._fill_defaults({}):
        return "_default_fields (physics fallback)"
    return "neither — a real physics answer"


def chain_frame_range_pct(traj, frame_count):
    if not traj or frame_count <= 0:
        return None
    first_fn = traj[0][0]
    last_fn = traj[-1][0]
    return (100.0 * first_fn / frame_count, 100.0 * last_fn / frame_count)


# ---------------------------------------------------------------------------
# Per-fixture run
# ---------------------------------------------------------------------------

def run_fixture(stem):
    video_path, GT, OTHER_MINER = load_fixture(stem)
    scoreable = GT is not None
    if video_path is None or not video_path.exists():
        print(f"ERROR: video not found for fixture '{stem}' "
              f"(searched {[str(d) for d in FIXTURE_SUBDIRS]})")
        return None
    if not scoreable:
        print(f"NOTE: fixture '{stem}' has no groundtruth on disk — running as an "
              f"UNSCOREABLE behaviour probe (camera type / valid / chain / mode only).")

    print("=" * 100)
    print(f"FIXTURE {stem}: {video_path.name}  {'[SCOREABLE]' if scoreable else '[UNSCOREABLE — behaviour probe only]'}")
    print("=" * 100)

    # ------------------------------------------------------------------ #
    # 1. Load video metadata, select the delivery shot (G1), reference frame
    # ------------------------------------------------------------------ #
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()

    # Mirrors predictor.py: shot selection is the single source of truth for
    # both the calibration frame (here) and the tracker's search window
    # (passed into tracker.track() below), replacing the old independent
    # int(frame_count * 0.55) / _WIN_START/_WIN_END fixed offsets.
    selection = select_delivery_shot(video_path, total_frames=frame_count)
    best_shot = selection.best()
    if best_shot is not None:
        delivery_start = best_shot.mid_frame
        shot_note = (f"shot #{best_shot.index} frames[{best_shot.start_frame},{best_shot.end_frame}] "
                     f"({100.0*best_shot.start_frame/frame_count:.1f}%-{100.0*best_shot.end_frame/frame_count:.1f}%), "
                     f"nbars={best_shot.wicket.get('nbars')} corroborated={best_shot.wicket.get('corroborated')} "
                     f"px_lat={best_shot.wicket.get('px_lat', 0.0):.1f}")
    else:
        delivery_start = int(frame_count * _FALLBACK_CALIBRATION_FRAC)
        shot_note = "NO DELIVERY SHOT FOUND — falling back to fixed 55% frame"

    cap = cv2.VideoCapture(str(video_path))
    cap.set(cv2.CAP_PROP_POS_FRAMES, delivery_start)
    ret, ref_frame = cap.read()
    cap.release()

    print(f"Video: fps={fps}  frames={frame_count}  "
          f"calibration_frame={delivery_start} ({100.0*delivery_start/frame_count:.1f}% of clip)")
    print(f"Shot selection: {len(selection.shots)} shot(s) segmented, found_any={selection.found_any}")
    print(f"  selected: {shot_note}")
    for shot in selection.shots:
        marker = " <= selected" if best_shot is not None and shot.index == best_shot.index else ""
        print(f"    shot #{shot.index} frames[{shot.start_frame},{shot.end_frame}] "
              f"({100.0*shot.start_frame/frame_count:.1f}%-{100.0*shot.end_frame/frame_count:.1f}%) "
              f"found={shot.found}{marker}")

    # ------------------------------------------------------------------ #
    # 2. Build homography
    # ------------------------------------------------------------------ #
    hom = PitchHomography(ref_frame if ret else None)
    camera_type = getattr(hom, 'camera_type', 'unknown')
    anchor_calibrated = getattr(hom, 'anchor_calibrated', False)
    print(f"Homography: camera={camera_type}  valid={hom.valid}  "
          f"anchor_calibrated={anchor_calibrated}  px/m={hom.pixels_per_metre_x:.2f}")
    if camera_type == "end_on":
        print(f"  end-on stump_px={hom._stump_px_endon}  "
              f"px/m_depth={hom._px_per_m_depth:.2f}  px/m_lat={hom._px_per_m_lat:.2f}")

    # ------------------------------------------------------------------ #
    # 3. Track ball — wall-clock measured here (Probe 12)
    # ------------------------------------------------------------------ #
    tracker = BallTracker(model_path=None)
    print("Tracking ball...")
    t0 = time.perf_counter()
    traj = tracker.track(video_path, homography=hom, shot_selection=selection)
    tracking_seconds = time.perf_counter() - t0
    print(f"Trajectory: {len(traj)} points  (tracking wall-clock: {tracking_seconds:.2f}s)")
    frame_range_pct = chain_frame_range_pct(traj, frame_count)
    if traj:
        print(f"  first={traj[0]}  last={traj[-1]}")
        print(f"  chain frame range: {traj[0][0]}-{traj[-1][0]} "
              f"({frame_range_pct[0]:.1f}%-{frame_range_pct[1]:.1f}% of clip)")

    # ------------------------------------------------------------------ #
    # 4. Analyse trajectory — call production's own analyse() in every mode.
    #    This is the ONLY thing that produces a scored answer; nothing here
    #    re-composes the physics path.
    # ------------------------------------------------------------------ #
    analyser = TrajectoryAnalyser(homography=hom, fps=fps)
    diag = gate_diagnostics(analyser, hom, traj) if traj else {
        "pts": 0, "depth_travel": None, "y_spread": None, "gates_passed": []}

    _prior_mode_env = os.environ.get(MODE_ENV_VAR)
    mode_fields = {}
    resolved_mode_by_setting = {}
    try:
        for setting in MODES:
            os.environ[MODE_ENV_VAR] = setting
            resolved_mode_by_setting[setting] = analyser.resolve_mode()
            mode_fields[setting] = analyser.analyse(traj)
    finally:
        if _prior_mode_env is None:
            os.environ.pop(MODE_ENV_VAR, None)
        else:
            os.environ[MODE_ENV_VAR] = _prior_mode_env

    print()
    print("Per-gate diagnostics:")
    print(f"  world points               : {diag['pts']}")
    print(f"  depth_travel (m)           : "
          f"{diag['depth_travel'] if diag['depth_travel'] is None else round(diag['depth_travel'], 3)}"
          f"   (gates: >6.0 lateral, >8.0 depth)")
    print(f"  y_spread (m)               : "
          f"{diag['y_spread'] if diag['y_spread'] is None else round(diag['y_spread'], 4)}"
          f"   (gate: >0.05)")
    print(f"  fields past confidence gate: {diag['gates_passed'] or 'NONE — all defaults'}")
    for setting in MODES:
        answer = mode_fields[setting]
        which = which_constant_set(answer, analyser)
        print(f"  mode={setting:<10} resolved={resolved_mode_by_setting[setting]:<10} -> {which}")

    result = {
        "stem": stem,
        "scoreable": scoreable,
        "camera": camera_type,
        "hom_valid": hom.valid,
        "anchor_calibrated": anchor_calibrated,
        "shot_found": selection.found_any,
        "shot_note": shot_note,
        "traj_pts": len(traj),
        "chain_frame_range_pct": frame_range_pct,
        "world_pts": diag["pts"],
        "depth_travel": diag["depth_travel"],
        "y_spread": diag["y_spread"],
        "gates_passed": diag["gates_passed"],
        "resolved_mode": resolved_mode_by_setting,
        "tracking_seconds": tracking_seconds,
        "scores": {},
        "which_constant_set": {s: which_constant_set(mode_fields[s], analyser) for s in MODES},
    }

    if not scoreable:
        print()
        print(f"  => fixture '{stem}' has no groundtruth: behaviour recorded above, NOT scored.")
        return result

    # ------------------------------------------------------------------ #
    # 5. Score every mode against groundtruth and the other-miner reference
    # ------------------------------------------------------------------ #
    print()
    hdr = (f"{'Field':<22} " + " ".join(f"{m:>10}" for m in MODES) + f" {'GT':>9} {'Wt':>5}")
    print(hdr)
    print("-" * len(hdr))
    totals = {m: 0.0 for m in MODES}
    total_other = 0.0
    for field, w in WEIGHTS.items():
        g = GT[field]
        tol = TOLERANCES[field]
        row_vals = []
        for m in MODES:
            p = mode_fields[m].get(field)
            s = score_field(p, g, tol)
            totals[m] += w * s
            row_vals.append(f"{p:.3f}" if p is not None else "None")
        s_other = score_field(OTHER_MINER.get(field), g, tol)
        total_other += w * s_other
        g_str = f"{g:.3f}" if g is not None else "None"
        print(f"{field:<22} " + " ".join(f"{v:>10}" for v in row_vals) + f" {g_str:>9} {w:>5.2f}")

    print("-" * len(hdr))
    for m in MODES:
        print(f"{'TOTAL ' + m:<32} {totals[m]:.4f}  ({totals[m]*100:.1f}%)")
    print(f"{'TOTAL other miner (reference)':<32} {total_other:.4f}  ({total_other*100:.1f}%)")
    print()

    result["scores"] = {m: totals[m] for m in MODES}
    result["scores"]["other"] = total_other
    return result


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

    scoreable_results = [r for r in results if r["scoreable"]]
    unscoreable_results = [r for r in results if not r["scoreable"]]

    if len(results) > 1:
        print("=" * 100)
        print("SUMMARY")
        print("=" * 100)
        print(f"{'fixture':<10} {'camera':<10} {'valid':<6} {'anchor':<7} {'pts':>5} "
              + " ".join(f"{m:>10}" for m in MODES) + f" {'other':>8}")
        for r in scoreable_results:
            sc = r["scores"]
            print(f"{r['stem']:<10} {r['camera']:<10} {str(r['hom_valid']):<6} "
                  f"{str(r['anchor_calibrated']):<7} {r['traj_pts']:>5} "
                  + " ".join(f"{sc[m]*100:>9.1f}%" for m in MODES)
                  + f" {sc['other']*100:>7.1f}%")
        for r in unscoreable_results:
            print(f"{r['stem']:<10} {r['camera']:<10} {str(r['hom_valid']):<6} "
                  f"{str(r['anchor_calibrated']):<7} {r['traj_pts']:>5}  UNSCOREABLE (no groundtruth)")
        if scoreable_results:
            for m in MODES:
                mean_m = sum(r["scores"][m] for r in scoreable_results) / len(scoreable_results)
                print(f"mean {m} over {len(scoreable_results)} scoreable fixtures: {mean_m*100:.1f}%")
        print("n is far too small to justify switching or not switching.")

    return results


if __name__ == "__main__":
    run(sys.argv[1:] or None)
