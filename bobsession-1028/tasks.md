# Cricket Miner v4 — Tasks (tonight, in order)

Sessions map 1:1 to BOB_PROMPTS.md. Sessions 1–2 are sequential. Session 3 runs in
the background once started. Sessions 4–5 need the stratified sample from Session 3
(a partial sample, ≥200 clips, is enough to start Session 4).

- [ ] 1. Harness + data placement
  - Place `data/labels.jsonl`, `data/split.json`, `data/median_baseline.json` from this
    package into the ibmbob repo (suggested: `cricket/data-training/balltrack/`).
  - Extend `cricket/validate.py` (or a sibling `validate_balltrack.py`) per R1:
    new weights, approx-tol label, non-null renormalisation, per-field report.
  - Acceptance: harness reproduces constants ≈19% and median ≈25% on **val** (±1.5 pts)
    and prints per-field scores. If it does not, STOP and report — do not adjust
    baselines or tolerances to force a match.

- [ ] 2. Median-baseline miner
  - Implement the flat-envelope baseline predictor in the turbovision private_track
    (new mode, e.g. `CRICKET_PREDICTOR_MODE=median`, preserving constants/physics/auto).
  - Local docker build + run; POST one stratified-sample clip URL; assert: HTTP 200,
    all 12 canonical fields present, values equal `median_baseline.json` exactly,
    `processing_time` < 30 s, `/health` OK.
  - Acceptance: a transcript of the curl + response + the parity note (live vs image).

- [ ] 3. Corpus download (background)
  - Adapt `scripts/pull_video_sample.py` into a full-corpus downloader per R3:
    stratified 600 first, then the remaining 13,224 in index order; dedupe by filename;
    >100 KB verify; 40 GB free-space guard; progress log every 100 files.
  - Acceptance: downloader running in background with log path reported; stratified 600
    complete (600/600 or every failure named); bulk count/GB at time of report.

- [ ] 4. G1 shot selection (report only)
  - On ≥100 stratified clips: choose the delivery window without the 50–65% assumption;
    save window (frames + % of clip), selection features, and 3 frames/clip for ≥10 clips.
  - Acceptance: report table + spot-check frames; explicit statement of how often the
    chosen window falls outside 50–65% (the G1 base rate on this corpus).

- [ ] 5. kph + bounce_x prototype + decision gate
  - Fix G5 blending (probe: GT-as-measurement must score 1.0 for bounce_x and kph
    across their full ranges) — before running any video.
  - Run physics on ≥100 stratified **val** clips inside Session 4's windows; score
    constants vs median vs physics-with-median-fallback, per field; include
    side-conditional medians as a reference column.
  - Acceptance: decision-gate report (mode × field table, gate pass rates, wall-clock
    per clip) ending with a keep/switch recommendation per field. No deploy actions.

## After tonight (not in scope, listed so nothing is silently dropped)
- v4.1: ball-detector fine-tune if Session 5 indicts the chainer; interception classifier;
  learned confidence gates tuned on val; test-split single evaluation.
- Deployment day (separate go from David): finish v3 tasks 15/16/18 (GHCR push + full
  reveal commitment + DataAndMike grant), dedicated IPv4 check on raw IP:port, then
  registration + stake decision with the immunity window timed to the new model.
