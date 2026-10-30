# Cricket Miner v4 — Design

## Architecture (three layers, in the order they earn their place)

```
POST /challenge {challenge_id, video_url}
        │
        ▼
┌─────────────────┐   Layer 0 — always available, never fails
│ MEDIAN BASELINE │   Returns data/median_baseline.json (12 fields).
│  (24.8% floor)  │   This is the fallback for every field, not just whole-answer.
└────────┬────────┘
         │ per-field override where a measured gate passes
         ▼
┌─────────────────┐   Layer 1 — measurement (Sessions 4–5, then iterated)
│ SHOT SELECT →   │   G1: find the delivery shot anywhere in the 20–30 s clip.
│ TRACK → PHYSICS │   G2/G3: honest camera class + calibration or explicit failure.
│                 │   Derive: kph (frame displacement × scale / time),
│                 │   bounce_x (trajectory depth at bounce), then stump_z from
│                 │   bounce_x via the two-phase ballistic model (NOT one parabola
│                 │   across the bounce — known error in bob-talk.md), impact_*
│                 │   only when an interception is detected in the clip.
└────────┬────────┘
         │ per-field confidence gate (learned on val, not hand thresholds)
         ▼
   FLAT ENVELOPE {challenge_id, prediction:{12 fields}, processing_time}
```

Why this order: the audit proves priors cap at ~28% and the two highest-value
unmeasured fields (kph, bounce_x — 20%) are pure measurement problems, while
stump_z (10%) is mostly a *derivation* from bounce_x (r=+0.85). Angles and
release_z stay on medians until a measurement beats the median on val — measured,
field by field, never by preference.

## Key design decisions
1. **Per-field fallback, not per-answer.** The v2/v3 code chose constants *or* physics
   for the whole answer. v4 composes per field: each field is the measurement if its
   gate passes, else the median. This is what makes partial CV progress worth points
   immediately (e.g. measuring only kph well is worth up to ~9.7 pts).
2. **The gate is data, not constants.** Hand thresholds (depth travel >6/8 m, chain ≥8)
   are replaced over time by thresholds chosen on val to maximise the approx-tol score;
   Session 5 keeps the existing gates but *reports* their pass rates per field so the
   tuning has something to stand on.
3. **Interception is a classification, later.** ~14.2% of balls have no interception.
   Returning impact medians blindly earns on the other ~86%; a "was there contact?"
   classifier is a separate measured improvement, queued after kph/bounce.
4. **Arm-side is a cheap feature.** release_y sign (65/35 split) strongly conditions
   bounce_y (+0.61 corr). When shot selection identifies the bowler's arm/crease side,
   lateral fields should use side-conditional medians as their fallback, not global ones.
   (Session 5 report should include side-conditional median scores as a reference column.)
5. **Corpus layout (AM5):** `data/train-videos/<hash>.mp4` outside git; labels and split
   are small and versioned. Dedupe is by filename (content hash). Stratified 600 first.
6. **Container:** same private-track template as v3 (FastAPI :8000, /health, header gate,
   Dockerfile/fly.toml parity, dedicated-IPv4 [[services]] when deployment day comes).
   Model artefacts baked in; no runtime downloads except the challenge clip itself.
   30 s budget: baseline answers in <1 s after download; measurement path must report
   its wall-clock per clip in every harness run.

## What v4 is NOT
- Not a detector training run (no YOLO/RT-DETR fine-tune tonight — that is v4.1, scoped
  only if Session 5 shows the blob-chainer, not the gates, is the binding constraint).
- Not a deployment. No registration, stake, axon, GHCR push, or Fly deploy tonight.
- Not a re-tune of constants on val/test. Medians come from the full labelled set's
  published values in `data/median_baseline.json` and are frozen for these sessions.
