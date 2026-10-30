# Cricket Miner v4 — Requirements
Element: `manako/DetectCricketDelivery` (Bittensor SN44, private track)
Date: 2026-10-28. Supersedes the *scoring* assumptions in `cricket-miner-v3` and the
single-clip claims in `cricket/VALIDATION_REPORT.md`. The gate diagnosis (G1–G5) in
`.kiro/specs/cricket-prediction-accuracy/` remains in force and is incorporated by reference.

## Measured facts this spec is built on (do not re-derive, do not contradict)
- Training set: **13,824** challenges at `https://manako.scoredata.me/train/index.json`,
  each with a video URL and scored ground truth. All labels are in `data/labels.jsonl`
  (13,824/13,824, verified, 13,824 unique videos).
- **Current scoring (BallTrack starter pack): 12 fields.** Primary 10% each:
  `bounce_x, kph, stump_y, stump_z, impact_x`. Secondary 8% each:
  `deviation, swing_angle, release_y, release_z, impact_y`. `bounce_y, impact_z` 5% each.
  `interception_distance, runs, wickets` and all ID fields are **zero weight**.
  New tolerances are unpublished ("strict tolerance-based decay"); all local scores in
  this package use the OLD tolerances as an approximation and must be labelled as such.
- **Response envelope is FLAT**: `{challenge_id, prediction: {<12 canonical fields>}, processing_time}`.
  No `type`/`item` wrapper. Missing scored field = 0 for that field. Use `null`, never 0,
  for a physical value the model chooses not to claim (see impact rule below).
- Baselines measured on all 13,824 (new weights, approx tolerances):
  v2 constants **19.2%** · global mean 22.9% · **global median 24.8%** ·
  oracle kph-band segmented median (cheating upper bound for priors) **27.9%**.
  Live leader (2026-10-28): **56.0%**. Target 85% (nobody is at target).
- Per-field reality: median field-score for `kph` is 2.9% (tol ~3 vs sd 21.4) and for
  `bounce_x` 3.9% (tol ~0.25 m vs sd 2.70). These two fields (20% of score) require
  *measurement from the video*. `swing_angle`/`deviation`/`release_z` medians already
  harvest ~70%/63%/47% of their fields.
- Correlations: `bounce_x`↔`stump_z` **+0.85**; `release_y`↔`bounce_y` +0.61;
  `release_y` sign splits `bounce_y` median −0.253 (65% of balls) vs +0.200.
- Nulls: `impact_x/y/z` are null in ground truth on ~14.2% of balls (no interception);
  `deviation` null on 435. Baselines are scored only over non-null fields.
- kph distribution is bimodal: 80–100 = 34.3%, 120–135 = 31.8%, ≥135 = 17.0%,
  100–120 = 14.0%, <80 = 3.0%. Median kph **118.82**, median bounce_x **6.144**.
  The v2 constants (kph 87.5, bounce_x 4.05) describe the be13 clip, not this population.
- Frozen split (`data/split.json`, by video-hash bucket): train 10,307 / val 2,109 / test 1,408.
  **Test is touched once, at the end. All tuning claims are on val.**

## Requirements

### R1 — Scoring harness (Session 1)
1. The harness SHALL score any predictor's output against `data/labels.jsonl` using the
   NEW weights above and the old per-field tolerances, labelled "approx-tol" in every report.
2. It SHALL reproduce the published baselines on val: constants ≈19%, median ≈25%
   (±1.5 pts; exact numbers printed and recorded, not assumed).
3. It SHALL score only over non-null ground-truth fields, renormalising weights per ball.
4. It SHALL report per-field scores, not only the total.

### R2 — Median-baseline miner (Session 2)
1. The miner SHALL return the flat envelope with the 12 medians from
   `data/median_baseline.json` for every challenge, with `processing_time` measured.
2. For `impact_x/y/z` the baseline returns the medians (a scored guess beats a null
   where GT exists ~86% of the time); whether to gate impact on an interception
   classifier is a *later, measured* decision — do not invent a gate in this session.
3. It SHALL serve `POST /challenge` and `GET /health` on port 8000 (FastAPI), download
   the clip (to prove the path works) but not depend on tracking for the answer.
4. The Docker image SHALL build from the repo's private-track base and SHALL return
   byte-identical predictions whether run live or from the pulled image (spot-check parity).
5. `BLACKLIST_ENABLED=false` / `VERIFY_ENABLED=false` SHALL be preserved verbatim in
   fly.toml [env] (they are load-bearing for boot; see v3 task 19 — do not "fix" them).

### R3 — Video corpus on the AM5 (Session 3)
1. Downloads SHALL be resumable, deduplicated by video filename (filenames are content
   hashes — same name = same video = skip), and SHALL verify size >100 KB per file.
2. Ordering SHALL be stratified-first: complete the 600-clip kph-stratified sample
   (manifest logic in `scripts/pull_video_sample.py`) before bulk-downloading the rest.
3. A disk guard SHALL stop downloads when free space falls below 40 GB and report.
   Projected full corpus ≈166 GB at the measured 12.0 MB average clip size.
4. The downloader SHALL run as a background job with a progress log (count, GB, ETA)
   and SHALL NOT block Sessions 4–5, which work on the stratified sample.
5. No video file may be committed to git. Corpus lives outside the repo tree or in a
   git-ignored data directory — state which, in the session report.

### R4 — G1 shot selection (Session 4)
1. Shot selection SHALL NOT assume the delivery is at 50–65% of the clip (that assumption
   is G1, a confirmed defect: deliveries measured at 15–35% and 5–15% on known fixtures).
2. The session SHALL deliver a *report*: for each clip in a ≥100-clip stratified subsample,
   the chosen delivery window (frame range + % of clip), the features that chose it, and
   3 sample frames per clip saved for human spot-checking on ≥10 clips.
3. No predictor integration in this session. A longer candidate chain is NOT evidence of
   success (a 12-point chain was previously found inside a close-up).

### R5 — kph + bounce_x measurement prototype (Session 5)
1. The prototype SHALL fix the G5 arithmetic defect first: remove the 0.6/0.4 blending
   toward defaults and let all fields the physics path computes reach the output
   (the blending probe — feed GT as measurement, assert the returned value scores 1.0 —
   must pass before any video is run).
2. It SHALL run the existing physics path (`_analyse_endon/_analyse_sideon` →
   `_select_confident_fields` → `_fill_defaults`) on ≥100 stratified val clips, using
   Session 4's shot windows, and score three modes side by side: constants, median
   baseline, physics-with-median-fallback (per-field: physics where the gate passes,
   median otherwise).
3. The session SHALL end with a decision-gate report in the style of
   `cricket-prediction-accuracy` task 3.7: which mode wins on val, per field, and whether
   `stump_z` derived from measured `bounce_x` (corr +0.85) beats the median stump_z.
4. No deployment, no registration, no commit-to-chain in this session.

## Hard rules (all sessions)
- **Wallet: NEVER handle, read, echo, copy or transmit coldkey/hotkey files, mnemonics,
  or any key material. No `btcli` spend, registration, staking, or axon extrinsics tonight.**
- No Fly deploy, no GHCR push, no on-chain commitment tonight. Local docker only.
- Never write candidate-profile / identity fields anywhere. The candidate is David Anderson.
- Do not modify the frozen split, the labels file, or the published baseline numbers.
  If a run disagrees with them, report the disagreement — do not edit the record to match.
- Preserve everything `cricket-miner-v3` delivered (reachability, /health, header gate,
  Dockerfile/fly.toml parity) — it is preservation surface, not scope.
- Every score claim must name: mode, split, n clips, and "approx-tol" where applicable.
  A score without those four is not a result.
