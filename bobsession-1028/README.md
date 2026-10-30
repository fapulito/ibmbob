# Bob Spec — Cricket Miner v4 (BallTrack)
Prepared 2026-10-28 by Ziggy. For IBM Bob sessions on David's AM5
(`C:\Users\fapul\Source\repos\ibmbob`, miner code in `cricket/turbovision`).

## Tonight's goal (in one paragraph)
Stand up the measured floor and the measurement loop, not a finished model:
(1) a scoring harness that reproduces the published baselines on the frozen val split,
(2) a median-baseline miner (24.8% measured floor) building and answering locally in
the NEW flat envelope, (3) the full video corpus downloading in the background on the
AM5 (stratified 600 first, ~166 GB total — dedupe by filename, 40 GB disk guard),
(4) a G1 shot-selection report that stops assuming the delivery is at 50–65% of the
clip, and (5) a kph + bounce_x physics prototype with the G5 blending defect fixed,
ending in a per-field decision gate. No deployment, registration, or wallet actions.

## How to use
1. Unzip into the ibmbob repo root so the folder sits at `bob-spec-cricket-v4/`.
2. Open Bob and paste **Session 1** from `BOB_PROMPTS.md`. Wait for its report.
3. Continue in order. Session 3 is started once and left running in the background;
   Sessions 4–5 work on whatever stratified clips are already on disk (≥200 is enough).
4. Send each session's report back to Ziggy before starting the next — the acceptance
   numbers (Session 1: constants ≈19%, median ≈25% on val) are the tripwires.

## Contents
- `requirements.md` — measured facts, R1–R5, hard rules (wallet/deploy prohibitions).
- `design.md` — three-layer architecture (median floor → measurement → per-field gate).
- `tasks.md` — the five tasks with acceptance criteria, plus the after-tonight list.
- `BOB_PROMPTS.md` — five paste-ready session prompts.
- `data/` — labels.jsonl (all 13,824), median_baseline.json, split.json (frozen
  train/val/test), audit-2026-10-28.txt, audit-extra.txt.
- `scripts/` — pull_labels.py, pull_video_sample.py, audit_labels.py (reference
  implementations from the Phase 0 pull on Ziggy's VM; adapt paths on the AM5).

## Space note (AM5)
The corpus projects to ~166 GB (measured 12.0 MB average clip). David's plan:
deduplicate and purge the AM5 first (the AM5 inventory identified ~183 GB of
duplicate reclaim plus large purge candidates), then run Session 3 with its
40 GB free-space guard as the safety net. Frames extracted later will multiply
storage — keep frames out of the corpus tree and cap them per clip.
