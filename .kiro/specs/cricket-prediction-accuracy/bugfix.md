# Bugfix Requirements Document

## Introduction

The cricket delivery miner (subnet 44, UID 207, Fly app `cricket-delivery-miner`) is now
reachable and answering. `cricket-miner-v3` fixed that and is done. This spec is about a
different bug condition: the answers score near zero.

Live validator challenge 65705 was received and answered successfully — HTTP 200 in 5.4 s,
inside the 30 s budget — and scored **2.9%**. The competitive field on comparable challenges
sits at 55.7%–73.5% (read manually from the console dashboard for
`manako/DetectCricketDelivery`; the page is JS-rendered and cannot be scraped).

Fly logs for 65705, verbatim:

```
04:04:17 | INFO    | Challenge received: 65705
04:04:17 | INFO    | Downloading video: https://scoredata.me/cricket/a97a57a1bbd41eb3b27b60d3b39bce2daa68da44.mp4
04:04:20 | WARNING | BallTracker end-on: short chain (0), widening window
04:04:22 | INFO    | BallTracker end-on: chain=0 pts
04:04:22 | INFO    | mode=auto → constants (homography valid=False)
04:04:22 | INFO    | Cricket challenge completed: 65705, time: 5.4s
```

The scoring function is a weighted sum over 13 numeric fields with per-field
`score = max(0, 1 - err/tol)` and a hard zero once `err >= tol`
(`scorevision/validator/central/private_track/scoring.py`,
`_CRICKET_FIELD_WEIGHTS` / `_CRICKET_FIELD_TOLERANCES` / `_score_numeric_match`; the weights
sum to exactly 1.0). `bounce_x` (0.23, tol 0.25 m) and `stump_y` (0.18, tol 0.12 m) are 41% of
the score between them. Neither can be earned by a fixed constant across videos, which is the
quantitative reason a constant answer floors out.

**The pipeline is a chain of five gates, and on any given video at least one of them closes.
Which one closes varies by video.** That is the core finding of the investigation behind this
document, and it is why fixing any single component in isolation produces no measurable change:

| Gate | Where | Closes when |
|------|-------|-------------|
| G1 shot selection | `predictor.py` 55% frame, `ball_tracker._WIN_START/_WIN_END` | the delivery is not at 50–65% of the clip |
| G2 camera classification | `pitch_homography._detect_camera_type` | a behind-the-arm clip is called `side_on` |
| G3 depth calibration | `pitch_homography._measure_depth_scale` → `valid` | the popping crease is not found |
| G4 chain formation | `ball_tracker._MIN_CHAIN`, `_ENDON_SEED_MIN_PY_OFFSET`, `_ENDON_MIN_DEPTH_PX` | fewer than 8 chained blobs with enough depth travel |
| G5 confidence gates | `trajectory._select_confident_fields` | fewer than 8 world points, or depth travel under 6/8 m |

Beyond the gates there is a sixth defect that no amount of tracker or calibration work can
reach: even with all five gates open, `_select_confident_fields` can only override 6 of the 13
fields, and it blends the two it cares most about back toward hardcoded defaults hard enough
that a *perfect* measurement scores zero over most of the plausible input range (clauses 1.22,
1.23).

Impact: near-total loss of subnet 44 private-track incentive for UID 207 despite a working,
reachable, in-budget miner.

Scope boundary: this bugfix changes **prediction accuracy only** — shot selection, camera
classification, calibration, tracking, field derivation, and the offline measurement harness.
Everything `cricket-miner-v3` delivered (reachability, axon, on-chain commitment, `/health`,
header gate, Dockerfile/fly.toml parity, the `POST /challenge` contract) is preservation
surface, not scope.

## Bug Analysis

Every clause below was confirmed against the code in this repository. Clauses tagged
**MEASURED** were confirmed by running the real pipeline modules against the local fixtures on
2026-XX (Windows host, `cv2` 5.0.0, `CRICKET_PREDICTOR_MODE` unset); the run is reproducible by
loading `pitch_homography.py`, `ball_tracker.py` and `trajectory.py` by file path the way
`cricket/validate.py` does.

Reference observations, all four local fixtures, unfixed code:

| fixture | res / fps / frames | camera_type | `valid` | `anchor_calibrated` | chain | resolved mode |
|---------|--------------------|-------------|---------|---------------------|-------|---------------|
| 8b97 | 1920x1080 / 25 / 510 | `side_on` | **True** | False | **0** | `physics` |
| be13 | 1920x1080 / 25 / 942 | `end_on` | False | True | 19 | `constants` |
| efc0 | 1280x720 / 30 / 1213 | `end_on` | False | True | 26 | `constants` |
| f81d | 1920x1080 / 25 / 813 | `side_on` | **True** | False | 21 | `physics` |
| live 65705 | not downloaded | `end_on` | False | unknown | **0** | `constants` |

### Current Behavior (Defect)

**G1 — the delivery shot is assumed to be at 50–65% of the clip**

1.1 WHEN `predict_cricket_delivery` picks its calibration frame THEN the system reads frame
`int(frame_count * 0.55)` unconditionally, with no check that the frame contains a pitch, so on
a clip whose 55% mark is a broadcast close-up the homography is calibrated from a frame with no
stumps, no crease and no pitch in it.

1.2 WHEN `BallTracker.track` searches for the delivery THEN the system scans only frames
`0.50 * total` to `0.65 * total` (`_WIN_START`, `_WIN_END`), so on a clip whose delivery lies
outside that band it is detecting blobs in the wrong shot entirely.

1.3 **MEASURED** WHEN the local fixtures are frame-sampled THEN the delivery is outside the
50–65% window on 2 of 4: **8b97's delivery is at roughly 15–35%** and everything from 45%
onward is batter/bowler close-ups (its 55% frame is a head-and-shoulders shot of a batter, and
its 95% frame is from a different match entirely); **f81d's delivery is at roughly 5–15%** with
close-ups from 45% on. be13 and efc0 — the two fixtures the constants were tuned on — do have
their delivery at 55–65%, which is why the assumption was never caught.

1.4 WHEN the first window yields fewer than `_MIN_CHAIN` points THEN the system rescans frames
`0` to `total - 1` with the same detection zone and the same chaining rules, so every shot in
the clip — close-ups, replays, crowd, sponsor bumpers, a different match — is treated as a
candidate delivery with no shot-boundary awareness.

1.5 **MEASURED** WHEN 8b97 is forced onto the end-on path THEN the widening rescan returns a
12-point chain at frames 316–329, which is 62–65% of the clip and therefore inside a close-up
shot, not the delivery. Those 12 points yield `bounce_x=11.283`, `kph=73.2`,
`stump_y=-0.581` — physics fitted to noise. **A longer chain is therefore not evidence of
progress**, and any success criterion phrased as "chain length ≥ N" is invalid.

**G2 — behind-the-arm clips are misclassified as side-on, and `valid` lies on that path**

1.6 WHEN `_detect_camera_type` finds any two adjacent vertical-edge column clusters separated by
more than 25% of the frame width THEN the system classifies the clip `side_on` and returns
immediately, so hoardings, sightscreen edges, a helmet grille or a close-up's background
furniture are enough to trigger it.

1.7 **MEASURED** WHEN 8b97 and f81d are classified THEN the system reports `side_on` for both,
although both are behind-the-arm broadcast clips of the same geometry as be13 and efc0. In
8b97's case the classification is made from a close-up of a batter's head.

1.8 WHEN the camera is classified `side_on` THEN `_try_calibrate_sideon` sets `self._valid =
True` on **every** exit path, including all four of its failure branches ("no lines",
"insufficient vertical lines", "insufficient clusters", "span too small"), so `hom.valid`
reports True whether or not anything was actually calibrated.

1.9 **MEASURED** WHEN `resolve_mode()` runs in `auto` against a side-on-classified clip THEN the
system resolves to `physics` unconditionally — 8b97 reports `camera=side_on valid=True
mode=physics` while using the resolution-scaled `_FALLBACK_SIDEON_*` constants for every world
coordinate. So `auto` does not mean "physics only when calibrated"; it means that only on the
end-on path.

1.10 **MEASURED** WHEN a behind-the-arm clip is tracked through `_track_sideon` THEN the search
zone is wrong for the geometry and the system returns 0 points: 8b97 chain=0 through the side-on
path, versus 12 points for the same clip and the same frame forced onto the end-on path.

**G3 — the end-on depth axis is never measured, so `auto` discards good tracking**

1.11 **MEASURED** WHEN `_try_calibrate_endon` finds a wicket but `_measure_depth_scale` finds no
popping-crease segment THEN `valid` stays False and `_px_per_m_depth` stays derived from
`_ENDON_DEPTH_PER_TRANSVERSE = 0.094`. be13 reports `anchor_calibrated=True valid=False`
(wicket found at cx=1019, base=598, px/m_lat=225.0, 3 bars, `depth_measured=False`); efc0
likewise (cx=649, base=442, px/m_lat=144.1, 2 bars); live 65705 logged `valid=False`. No
fixture has ever produced `valid=True` on the end-on path.

1.12 **MEASURED** WHEN `valid` is False in `auto` mode THEN `analyse()` returns
`_tuned_constant_fields()` and never reads its trajectory argument, so a successfully tracked
chain is discarded: be13's 19 points and efc0's 26 points are both thrown away.

1.13 WHEN the depth scale is derived rather than measured THEN every depth-dependent field is a
restatement of two constants fitted on two clips — `_ENDON_DEPTH_PER_TRANSVERSE` (mean of 0.101
and 0.087, a 15% spread) and `_ENDON_CAMERA_DISTANCE_M = 90.0` (not measurable from those clips
at all) — which is not a per-video measurement of `bounce_x`, the highest-weighted field.

1.14 WHEN `pitch_homography.py`'s module docstring is read THEN it states that `valid` means
"the wicket was found and its transverse scale corroborated", which contradicts both the
`valid` entry in the class docstring and `_try_calibrate_endon`'s actual behaviour ("the DEPTH
axis was measured"). The docs disagree with the code about the meaning of the flag that gates
the entire physics path.

**G4 — tracker thresholds are resolution-absolute, stale-commented, and partly dead**

1.15 WHEN `_track_endon` applies `_ENDON_SEED_MIN_PY_OFFSET = 200` and `_ENDON_MIN_DEPTH_PX =
147` THEN the system uses absolute pixel counts while every homography scale is
resolution-relative, so the same constants demand different physical distances per clip: with
the fallback scales, a 200 px seed offset is ≈7.7 m of depth at 1920 wide and ≈11.1 m at 1280
wide. This is the same defect class the `_REFERENCE_FRAME_WIDTH` comment in
`pitch_homography.py` records as already fixed there — the tracker was not fixed with it.

1.16 WHEN the comments on those constants are read THEN they contradict each other and the code:
line 37 says `stump_base + 200px ≈ x>13m`, line 91 says the same constant means "at least 50px
below stump base (≈3.4m)", and `_ENDON_MIN_DEPTH_PX`'s comment assumes 14.7 px/m depth when the
actual fallback depth scale is ≈23.8 px/m at 1920 wide and ≈15.9 px/m at 1280 wide.

1.17 WHEN `_ENDON_MAX_LATERAL_PX = 110` is looked up THEN it is referenced nowhere — dead code.
The lateral zone is actually `±1.5 * _px_per_m_lat`, not the ±2.0 m the comment claims.

1.18 WHEN `_MIN_CHAIN = 8` is applied THEN the system requires 8 chained detections within the
frames the ball spends inside the seed-constrained depth zone, so the chain either has 8+ points
or exactly 0 — there is no partial result and no diagnostic for "5 points found, rejected".

**G5 — the confidence gates admit noise, cover fewer than half the fields, and blend away the
accuracy of the ones they do cover**

1.19 WHEN `_select_confident_fields` receives fewer than 8 world points THEN the system returns
`{}` and `_physics_fields` falls through to `_default_fields()`. This is a second, stricter gate
than `analyse()`'s 3-point check, and it fires after `_analyse_endon`'s
`x_m`/`y_m` range filter has already dropped out-of-range points, so a chain of 8+ pixels can
still land under 8 world points.

1.20 WHEN `analyse()` degrades in `physics` mode THEN the system returns `_default_fields()`,
which is a **different** 13-value set from `_tuned_constant_fields()`. Two distinct
near-zero-scoring failure modes therefore produce two different answers, and a log line reading
`mode=physics` does not tell you which.

1.21 WHEN `_select_confident_fields` succeeds THEN only 6 of the 13 fields can ever be
overridden — `release_y`, `bounce_y`, `stump_y`, `impact_y`, `bounce_x`, `kph`. The other 7 —
`release_z`, `impact_x`, `impact_z`, `interception_distance`, `stump_z`, `swing_angle`,
`deviation`, carrying **0.46 of the total weight** — are returned as `_default_fields()`
constants on every single call, even on a perfectly tracked delivery. `_analyse_endon` computes
all of them and `_select_confident_fields` discards them unconditionally.

1.22 WHEN `bounce_x` passes its gate THEN the system returns `measured * 0.6 + 4.0 * 0.4`. With
tolerance 0.25 m, a **perfect** measurement scores non-zero only when the true value lies in
3.375–4.625 m. Local groundtruths: be13 4.082 (inside), efc0 6.743 (outside), 8b97 5.622
(outside). So the blend alone zeroes the highest-weighted field on 2 of 3 labelled fixtures
regardless of tracker quality.

1.23 WHEN `kph` passes its gate THEN the system returns `measured * 0.6 + 88.0 * 0.4`. With
tolerance 3.0 kph, a perfect measurement scores non-zero only when the truth lies in
80.5–95.5 kph. Local groundtruths: be13 87.58 (inside), 8b97 95.32 (just inside, scoring 0.024
of a possible 1.0), efc0 129.21 (outside).

1.24 **MEASURED** WHEN `_select_confident_fields` is handed the 12-point noise chain from clause
1.5 THEN it passes the gates and emits overrides `{release_y, bounce_y, stump_y, impact_y,
bounce_x: 8.37, kph: 79.12}`. The gates do not distinguish a tracked delivery from blobs on a
close-up.

**The constants floor — why the fallback paths cannot score**

1.25 **MEASURED** WHEN `_tuned_constant_fields()` is scored against the 8b97 groundtruth with
the validator's weights and tolerances THEN the total is **10.4%**, with `bounce_x`,
`deviation`, `kph`, `release_y`, `bounce_y`, `impact_x`, `impact_y`, `impact_z` and
`interception_distance` all scoring exactly 0 — 9 of 13 fields, 0.74 of the weight, zeroed.
Only `stump_z` (0.0458), `swing_angle` (0.0542), `stump_y` (0.0030) and `release_z` (0.0012)
contribute anything.

1.26 **MEASURED** WHEN `_default_fields()` is scored against the same groundtruth THEN the total
is **21.1%** — the fallback that `physics` mode degrades to outscores the tuned constants on
this fixture. The two constant sets are not interchangeable and neither is a floor.

1.27 WHEN a fixed constant is used for `bounce_x` (0.23 weight, 0.25 m tolerance) and `stump_y`
(0.18, 0.12 m) THEN the system cannot score on 41% of the total across a varied field, because
those tolerances are narrower than the between-delivery variation. Recorded evidence: be13's
groundtruth sits within rounding of the tuned constants (hence its 92.8% local score) while
efc0's and 8b97's do not, and live traffic scored 2.9%.

1.28 **MEASURED** WHEN the reference miner's recorded answer in `groundtruth-8b97.json` is
scored against that file's own `groundtruth` block THEN it totals **≈79.7%**. The groundtruth is
therefore attainable from the video by a CV pipeline; this is not an unlabelable problem.

**The measurement loop is broken**

1.29 WHEN `cricket/validate.py` is run THEN it prints "video not found" for both fixtures,
because `FIXTURE_DIR` is `turbovision/data-training/cricket` while `be1382745e….mp4` and
`efc05ed4ef….mp4` now live in that directory's `foundation/` subdirectory.

1.30 WHEN `validate.py`'s `FIXTURES` dict is read THEN the `8b97` pair — the only fixture whose
groundtruth is a real delivery not already fitted by the constants — is not registered, and
`f81d092b6117….mp4` has no `groundtruth-*.json` at all, so it can be probed but not scored.

1.31 WHEN `tests/private/v25_recorded_baseline.py` resolves `CRICKET_FIXTURES = REPO_ROOT /
"data-training" / "cricket"` and `V25_FIXTURE_VIDEOS` names the be13/efc0 files directly in it
THEN `test_cricket_fixtures_are_present`,
`test_fixture_groundtruth_matches_what_was_recorded` and
`test_fixture_miner_response_block_is_not_the_groundtruth` all reference paths that no longer
exist. Verified by path inspection, not by a test run: the Windows `.venv` cannot collect the
suite (`tests/fixtures/key_fixtures.py` imports `nacl`, absent) and the project venvs
(`.venv-sv`, `.venv-bt`) are POSIX/WSL.

1.32 WHEN `validate.py`'s `real_pipeline()` is read THEN it re-composes the physics path in the
harness (`_analyse_endon` → `_select_confident_fields` → `_fill_defaults`) as though production
did not, but `trajectory.py` now has `_physics_fields` doing exactly that. Harness and
production can silently diverge, and the harness's "stub"/"real" vocabulary predates the
`constants`/`physics`/`auto` modes.

1.33 WHEN the challenge-65705 video is needed for reproduction THEN the system cannot score it:
the video is fetchable from `https://scoredata.me/cricket/<hash>.mp4` without auth, but the
protocol withholds per-challenge groundtruth from miners, so 65705 can only be reproduced as
observable pipeline behaviour (`chain=0`, `valid=False`, resolved mode), never as a score.

**Latency**

1.34 WHEN the first tracking window fails THEN the system rescans the entire clip, which is the
dominant cost in the pipeline. Wall-clock on the investigation host (not the container): 8b97
6.9 s, f81d 8.7 s — both took the full rescan — versus be13 1.8 s and efc0 1.1 s, which did not.
The live 65705 run completed in 5.4 s total including download, so the headroom under the 30 s
budget is real but finite, and any change that examines more shots or more frames spends it.

### Expected Behavior (Correct)

**G1 — shot selection**

2.1 WHEN the pipeline chooses a calibration frame THEN the system SHALL select it from a frame
in which the pitch geometry is actually present, rather than from a fixed 55% offset, and SHALL
report which frame was chosen so the choice is auditable in `fly logs`.

2.2 WHEN the pipeline chooses which frames to track THEN the system SHALL locate the delivery
shot from the video content rather than assume a fixed 50–65% band, and SHALL work on clips
whose delivery is early (8b97 ≈15–35%, f81d ≈5–15%) as well as those where it is at 55–65%
(be13, efc0).

2.3 WHEN a clip contains multiple shots THEN the system SHALL be shot-boundary aware to the
extent that a chain is never assembled from blobs spanning a cut, so the 12-point close-up
chain of clause 1.5 cannot be produced.

2.4 WHEN shot selection fails THEN the system SHALL say so distinguishably in the log — "no
delivery shot found" SHALL NOT be reported as "chain=0", because those have different fixes.

**G2 — camera classification and honest validity**

2.5 WHEN a behind-the-arm broadcast clip is classified THEN the system SHALL classify it
`end_on`, and SHALL classify 8b97 and f81d `end_on`.

2.6 WHEN `_try_calibrate_sideon` fails to calibrate THEN the system SHALL leave `valid` False.
`valid` SHALL mean the same thing on both camera paths: the axis that the physics depends on was
measured from the frame. It SHALL NOT be set on a failure branch.

2.7 WHEN `resolve_mode()` returns `physics` in `auto` THEN the system SHALL have measured the
calibration it is about to rely on, on whichever camera path it took.

2.8 WHEN camera classification is uncertain THEN the system SHALL log the evidence it decided on
(cluster count, separation, chosen type) so a misclassification is diagnosable from `fly logs`
without re-running locally.

**G3 — depth calibration**

2.9 WHEN an end-on frame is calibrated THEN the system SHALL measure the depth axis from the
frame on clips where a depth landmark is present, and SHALL report `valid=True` only then.

2.10 WHEN no depth landmark is found THEN the system SHALL still make the derived depth scale
available to the tracker (as `anchor_calibrated` already does) rather than discarding the
calibration entirely, so tracking is not penalised for a calibration gap.

2.11 WHEN `pitch_homography.py`'s docstrings describe `valid` THEN the system SHALL state one
meaning consistently, matching the code.

**G4 — tracker thresholds**

2.12 WHEN the tracker applies a seed-depth or depth-travel threshold THEN the system SHALL
express it in metres and convert through the homography's own scales, so the same threshold
means the same physical distance at 1280x720 and 1920x1080.

2.13 WHEN the tracker rejects a candidate chain THEN the system SHALL log which constraint
rejected it and the value that failed, so `chain=0` is never the only diagnostic.

2.14 WHEN `_ENDON_MAX_LATERAL_PX` is unreferenced THEN the system SHALL either apply it or
remove it. Dead thresholds SHALL NOT sit next to live ones with contradictory comments.

2.15 WHEN a comment states a constant's physical meaning THEN the system SHALL make it agree
with the constant's actual effect under the homography's real scales.

**G5 — field derivation**

2.16 WHEN the physics path produces a field that `_analyse_endon` computed THEN the system SHALL
be capable of returning it. The 7 fields carrying 0.46 of the weight SHALL NOT be
unconditionally replaced by defaults.

2.17 WHEN a measured field is returned THEN the system SHALL NOT blend it toward a hardcoded
default in a way that pushes a correct measurement outside the validator's tolerance. Any
blending that survives SHALL be justified against a measurement, not against plausibility.

2.18 WHEN the confidence gates accept a trajectory THEN the system SHALL have evidence the
trajectory is a delivery, not merely that it has 8+ points and 6 m of apparent depth travel.

2.19 WHEN the pipeline falls back THEN the system SHALL log which constant set it returned
(`_tuned_constant_fields` or `_default_fields`) and why, so the two near-zero modes of clause
1.20 are distinguishable from logs alone.

**The measurement loop**

2.20 WHEN `cricket/validate.py` is run THEN the system SHALL locate every labelled fixture at
its real path, including those under `foundation/`, and SHALL register the `8b97` pair.

2.21 WHEN a fixture has a video but no groundtruth (`f81d`) THEN the system SHALL still run it
as a behaviour probe (camera type, `valid`, chain length, resolved mode, selected shot) and
SHALL report it as unscoreable rather than omit it or score it against nothing.

2.22 WHEN the harness reads a groundtruth file THEN the system SHALL continue to take truth from
the `groundtruth` block and treat `miner_response.prediction` as a reference column only, never
as truth — every local `groundtruth-*.json` carries a foreign `miner_hotkey`
(`5DZQt68U…`, `5CABFE9t…`, `5FhFQpKA…`), none of them ours.

2.23 WHEN the harness scores a field THEN the system SHALL use the validator's own weights,
tolerances and comparison semantics, and SHALL be verified against
`scorevision/validator/central/private_track/scoring.py` rather than against a copy that can
drift.

2.24 WHEN the harness reports physics THEN the system SHALL call production's
`_physics_fields`/`analyse` rather than re-composing the pipeline in the harness, so harness and
production cannot diverge.

2.25 WHEN the harness reports a result THEN the system SHALL report per-gate diagnostics
(selected shot, camera type, `valid`, `anchor_calibrated`, chain length, world-point count,
depth travel, y-spread, which fields passed the gates) alongside the score, because the score
alone does not identify which gate closed.

2.26 WHEN a claim about score improvement is made THEN the system SHALL trace it to a harness
run over the labelled fixtures. **No target percentage is stated in this spec**, because
physics has never been measured with a genuinely calibrated depth axis on any fixture and its
real ceiling is not knowable from what is on disk today.

**Reproduction of the live failure**

2.27 WHEN the live failure is reproduced THEN the system SHALL be reproduced as observable
pipeline behaviour — a fixture on which the unfixed pipeline yields `chain=0` and/or
`valid=False` and/or a misclassified camera — because per-challenge groundtruth is withheld and
challenge 65705 cannot be scored offline (clause 1.33).

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a validator challenge arrives THEN the system SHALL CONTINUE TO answer `POST
/challenge` on the same path with the same request and response contract, returning
`PredictionPayload(type="cricket_delivery", item=...)` with all 13 fields present as finite
floats and none `None` (`TRAJECTORY_FIELDS`, `_coerce_contract`).

3.2 WHEN any input reaches `analyse()` THEN the system SHALL CONTINUE TO degrade rather than
raise — empty, `None`, 1-point, 2-point, stationary and out-of-frame trajectories, and a
homography whose `pixel_to_metres` throws, SHALL all still return a complete field set, because
`routes.py`'s blanket `except Exception` turns anything else into a 500 and a 500 scores 0.

3.3 WHEN a challenge is answered THEN the system SHALL CONTINUE TO complete inside the
validator's 30 s timeout, and SHALL NOT regress the observed 5.4 s live budget to the point
where the margin is unclear. Any change that scans more shots or more frames SHALL be measured
for wall-clock, not assumed cheap.

3.4 WHEN `CRICKET_PREDICTOR_MODE=constants` is set THEN the system SHALL CONTINUE TO return
exactly the v2.5 tuned constants recorded in
`tests/private/v25_recorded_baseline.V25_CONSTANT_PREDICTION_ITEM`, so the rollback path stays
intact and `tests/private/test_v25_baseline_predictions.py` keeps passing.

3.5 WHEN the default mode is resolved THEN the system SHALL CONTINUE TO default to `auto`, and
SHALL NOT be switched to `physics` until physics is measured better than the constants on a
working harness across multiple labelled fixtures. The previous decision to keep `auto` was
evidence-based and stands until new evidence replaces it.

3.6 WHEN the miner is deployed THEN the system SHALL CONTINUE TO be reachable and discoverable
exactly as `cricket-miner-v3` left it: dedicated IPv4 axon on port 8000 with `ip_type=4`, the
private-track on-chain commitment, `GET /health` returning 200 without invoking the predictor,
the header gate on `/challenge`, and `Dockerfile.v3`/`fly.toml` parity.

3.7 WHEN the container starts THEN the system SHALL CONTINUE TO import `cv2` and `numpy` under
the image's pinned `opencv-python-headless`, with no new native dependency added and no
reinstatement of `libgl1`.

3.8 WHEN the miner runs THEN the system SHALL CONTINUE TO operate as UID 207 on hotkey
`5CyQ9buHwqgCS7158ytsX8BQvT7WSEH8gDMWq7tqUV3Fshsa` — no re-registration, no new axon extrinsic,
no new on-chain commitment, no additional paid or rate-limited chain writes.

3.9 WHEN routes dispatch THEN the system SHALL CONTINUE TO handle the `soccer_action` and TCG
(`image_url`) paths unmodified.

3.10 WHEN the side-on physics path is exercised THEN the system SHALL CONTINUE TO satisfy the
13-field contract, because `_analyse_sideon` remains reachable for genuinely side-on clips.

3.11 WHEN `.env` is involved THEN the system SHALL CONTINUE TO be left untouched by the agent,
and no wallet secret SHALL be read or logged.

3.12 WHEN code changes land THEN the system SHALL CONTINUE TO place them in
`fapulito/scoreturbo` branch `cricket-miner-v3` under `cricket/turbovision`, with the spec in
`fapulito/ibmbob` under `.kiro/specs/`.

### Bug Condition and Properties

**Bug Condition** — identifies the videos on which the miner emits an answer that is not derived
from the video:

```pascal
FUNCTION isBugCondition(X)
  INPUT: X of type CricketChallengeVideo
  OUTPUT: boolean

  ref        ← frame(X, round(0.55 * frameCount(X)))
  hom        ← PitchHomography(ref)
  chain      ← BallTracker.track(X, hom)
  mode       ← resolveMode(hom)          // auto → physics iff hom.valid

  // G1: the frames the pipeline looked at do not contain the delivery
  wrongShot     ← NOT deliveryVisibleIn(ref)
                  OR NOT deliveryWithin(X, 0.50, 0.65)

  // G2: behind-the-arm geometry classified side-on, or validity asserted
  //     without a measurement behind it
  misclassified ← isBehindTheArm(X) AND hom.camera_type = "side_on"
  falseValid    ← hom.valid AND NOT hom.depthAxisMeasuredFromFrame

  // G3: end-on depth axis never measured, so auto discards the trajectory
  noDepthAxis   ← hom.camera_type = "end_on" AND hom.valid = FALSE

  // G4: no chain at all, or a chain assembled from the wrong shot
  noChain       ← |chain| = 0
  noiseChain    ← |chain| ≥ 8 AND NOT chainLiesInDeliveryShot(chain, X)

  // G5: the answer that reaches the wire is a constant set
  constantAnswer ← (mode = "constants")
                   OR (mode = "physics" AND worldPointCount(chain, hom) < 8)

  RETURN wrongShot OR misclassified OR falseValid OR noDepthAxis
         OR noChain OR noiseChain OR constantAnswer
END FUNCTION
```

All four local fixtures and the live challenge satisfy `isBugCondition` today, by different
disjuncts — which is the point. The disjunction is not a modelling convenience; it is why no
single fix is independently verifiable end-to-end.

**Fix Checking** — for every video that triggers the bug, the fixed pipeline must produce an
answer derived from that video:

```pascal
// Property: Fix Checking — the answer is measured, not asserted
FOR ALL X WHERE isBugCondition(X) DO
  shot   ← selectDeliveryShot'(X)
  hom    ← PitchHomography'(referenceFrame'(X, shot))
  chain  ← BallTracker'.track(X, hom, shot)
  fields ← TrajectoryAnalyser'(hom).analyse(chain)

  ASSERT deliveryVisibleIn(referenceFrame'(X, shot))
  ASSERT isBehindTheArm(X) IMPLIES hom.camera_type = "end_on"
  ASSERT hom.valid IMPLIES hom.depthAxisMeasuredFromFrame
  ASSERT chainLiesInDeliveryShot(chain, X)
  ASSERT fields ≠ tunedConstantFields() AND fields ≠ defaultFields()
  ASSERT |fields| = 13 AND all finite AND none NULL
  ASSERT wallClock(X) < 30 s

  // Scored only where a groundtruth exists (be13, efc0, 8b97 — not f81d,
  // not challenge 65705).
  IF hasGroundtruth(X) THEN
    ASSERT validatorScore(fields, groundtruth(X))
           > validatorScore(unfixedAnswer(X), groundtruth(X))
  END IF
END FOR
```

The final assertion is deliberately a strict improvement over the *measured* unfixed baseline
per fixture, not a threshold. Recorded unfixed baselines to beat: 8b97 — 10.4% via
`_tuned_constant_fields`, 21.1% via `_default_fields` (its actual production path today).
be13 and efc0 baselines must be re-measured on a working harness before they are quoted, because
the numbers in `trajectory.py`'s module comment (constants 92.8%/19.4%, physics 43.2%/22.1%)
were taken while `valid=False` on both, i.e. physics on fallback calibration, and the harness
that produced them no longer runs.

**Preservation Checking** — for every input that does not trigger the bug, behaviour is
identical before and after:

```pascal
// Property: Preservation Checking
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT F(X) = F'(X)
END FOR

// Concretely, on the axes that must not move:
ASSERT analyse'(any, mode="constants") = V25_CONSTANT_PREDICTION_ITEM fields
ASSERT resolveMode'(no env var) uses default "auto"
ASSERT FOR ALL degenerate t IN {[], NULL, 1-pt, 2-pt, stationary, out-of-frame}:
         analyse'(t) returns 13 finite floats AND does not raise
ASSERT httpContract'(POST /challenge) = httpContract(POST /challenge)
ASSERT status'(GET /health) = 200 AND predictorInvoked' = FALSE
ASSERT axonInfo' = axonInfo AND onChainCommitment' = onChainCommitment
ASSERT importCv2(image') = SUCCESS
ASSERT wallClock'(X) < 30 s FOR ALL X
```

**What is not knowable offline** — stated explicitly so no task is written against it:

| Unknown | Why | Consequence for this spec |
|---------|-----|---------------------------|
| Physics' real accuracy ceiling | `valid=True` has never occurred on any end-on fixture, so physics has never run on a measured depth axis | No target score. Success is "strictly better than the measured unfixed baseline, per fixture" |
| Groundtruth for challenge 65705 | The protocol withholds pseudo-groundtruth from miners; the video is downloadable, the labels are not | 65705 is reproduced as behaviour (`chain=0`, `valid=False`), never as a score |
| Groundtruth for `f81d` | No `groundtruth-*.json` shipped | Behaviour probe only; unscoreable, and reported as such |
| Whether live validator scoring matches the local harness exactly | The weights, tolerances and `max(0, 1-err/tol)` semantics were read from `scoring.py` and match `validate.py`; the deployed validator version was not inspected | Harness parity is a task, asserted against `scoring.py`, not assumed |
| How representative the 4 local fixtures are | n=4, of which 1 is fitted by the constants and 1 is unlabelled | Any conclusion drawn from the mean of 2–3 fixtures is provisional and must say so |
