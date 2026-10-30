# BOB_PROMPTS — Cricket Miner v4 (paste one session at a time, in order)

Context for every session: you are working in `C:\Users\fapul\Source\repos\ibmbob`
(cricket miner, Bittensor SN44) with the miner code in `cricket/turbovision` on branch
`cricket-miner-v3`. The v4 spec package (requirements.md, design.md, tasks.md, data/,
scripts/) has been placed in the repo root as `bob-spec-cricket-v4/` — read
`bob-spec-cricket-v4/requirements.md` first; its "Measured facts" section is ground
truth and must not be contradicted or re-derived. Hard rules for ALL sessions: never
touch wallet files, mnemonics, or key material; no btcli spend/registration/staking;
no Fly deploy, GHCR push, or on-chain commitment; preserve BLACKLIST_ENABLED=false /
VERIFY_ENABLED=false verbatim in fly.toml; do not modify data/labels.jsonl,
data/split.json, or the published baseline numbers — report disagreements instead.

---

## Session 1 — Harness + data placement
Read bob-spec-cricket-v4/requirements.md (R1) and tasks.md task 1. Copy the package's
data/ files into `cricket/data-training/balltrack/` (labels.jsonl, split.json,
median_baseline.json). Write `cricket/validate_balltrack.py`: it loads labels.jsonl,
takes a predictor name (constants | median | mean) or a predictions JSONL, scores with
the NEW weights (bounce_x/kph/stump_y/stump_z/impact_x = .10; deviation/swing_angle/
release_y/release_z/impact_y = .08; bounce_y/impact_z = .05), the OLD tolerances
(kph 3, bounce_x .25, stump_y .12, stump_z .12, release_y/z .15, bounce_y .15,
impact_x .25, impact_y/z .15, angles 2.0), renormalising per ball over non-null GT
fields, and prints total + per-field scores labelled "approx-tol". Run it for constants
and median on the val split (split.json). Acceptance: constants ≈19% and median ≈25%
(±1.5 pts). If outside that band, STOP, print what you got and your scoring code, and
do not change baselines or tolerances to force a match. Report the exact scores.

## Session 2 — Median-baseline miner
Read requirements.md (R2) and design.md. In cricket/turbovision's private_track, add a
new predictor mode `CRICKET_PREDICTOR_MODE=median` that returns the FLAT envelope
{challenge_id, prediction: {12 canonical fields from
cricket/data-training/balltrack/median_baseline.json}, processing_time} — no type/item
wrapper. Existing modes (constants/physics/auto) must keep working unchanged. The mode
still downloads the challenge clip (proving the path) but the answer is the medians.
Build the Docker image locally, run it on port 8000, and curl /challenge with one
stratified-sample clip URL from labels.jsonl, plus /health. Acceptance transcript:
HTTP 200, all 12 fields present and exactly equal to median_baseline.json,
processing_time < 30 s. Report the transcript and any deviation. No deploy, no push.

## Session 3 — Corpus download (start this, then leave it running)
Read requirements.md (R3). Adapt bob-spec-cricket-v4/scripts/pull_video_sample.py into
`scripts/pull_corpus.py`: fetch order = the 600-clip kph-stratified sample first
(same band logic), then all remaining entries from data/index order in labels.jsonl;
save to `cricket/data-training/balltrack/videos/<hash>.mp4` (git-ignored — add the
ignore rule); skip files already present >100 KB (dedupe is by filename = content
hash); 4 workers, 4 retries with backoff; STOP and report if free disk < 40 GB;
log progress every 100 files (count, GB, rate). Start it in the background, confirm
the log is advancing, then report: log path, stratified count so far, bulk ETA.
Do not wait for the full ~166 GB to finish in this session.

## Session 4 — G1 shot selection (report only, no predictor changes)
Read requirements.md (R4) and the G1 section of
.kiro/specs/cricket-prediction-accuracy/bugfix.md. Using ≥100 clips from the
stratified sample on disk, implement shot selection that finds the delivery shot
WITHOUT assuming it lies at 50–65% of the clip: candidate features are yours to choose
(pitch/stumps visibility, bowler run-up motion, broadcast shot-boundary cuts), but the
55%-frame shortcut is forbidden. Deliver `cricket/data-training/balltrack/g1-report.md`:
per clip — chosen window (frame range, % of clip), features used, confidence; plus
3 saved frames per clip for at least 10 clips under `g1-frames/`. State the base rate:
on how many clips did the chosen window fall outside 50–65%? Do not integrate this
into the predictor and do not claim chain length as success.

## Session 5 — kph + bounce_x prototype + decision gate
Read requirements.md (R5). FIRST, no video: fix the G5 blending defect in
trajectory.py's _select_confident_fields — remove the blend toward defaults for
bounce_x and kph and let every field _analyse_endon/_analyse_sideon computes reach
the output. Prove it with the blending probe: feeding the GT value as the measured
value must return a value scoring 1.0, for bounce_x across 0–12 m and kph across
50–155. If the probe fails, stop and report. THEN run the physics path on ≥100
stratified VAL clips (split.json) restricted to Session 4's shot windows, with
per-field fallback to the medians when a gate fails. Score constants vs median vs
physics-fallback per field with validate_balltrack.py, and add side-conditional
medians (split by release_y sign) as a reference column. Deliver
`cricket/data-training/balltrack/session5-decision-gate.md`: mode × field table,
gate pass rates per field, wall-clock per clip, and a keep/switch recommendation
PER FIELD — including whether stump_z derived from measured bounce_x beats the
median stump_z. No deployment or registration actions. State the exact per-field eff-score formula in the decision-gate report.
