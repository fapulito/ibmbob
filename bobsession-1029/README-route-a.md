# Cricket Route A — fix the classical physics path

Route A of the 2026-10-29 competitiveness assessment
(`../COMPETITIVE-ASSESSMENT-2026-10-29.md`): diagnose why homography
never validates, fix that one thing, then re-judge the tracker with the
Session 5 decision gate. Route B (learned regression) is separate and
waits for the AM5 cleanup this weekend.

## Where things stand (measured, approx-tol)

- Median baseline: 26.23% on 115 VAL clips; 25.09% on full val (2,109).
- Physics + fallback: 14.79% on the same 115 — worse than median on all
  12 fields (Session 5 decision gate, verified).
- Bob-reported root cause: `hom.valid=False` on essentially all VAL
  clips → every measurement ran on fixed fallback pixel scales.
  This claim is NOT yet in a written report Ziggy has verified.
  Session 6 verifies or refutes it with counts.
- Session 4: the content-based shot selector finds windows fine
  (98.3%); 55% of deliveries sit outside the old 50–65% band.
- G5 blending: fixed and probe-proven (Session 5).

## Sessions

- **Session 6 — Homography validity autopsy** (in BOB_PROMPTS.md,
  paste-ready). Instrumentation + measurement only. Changes no
  prediction behaviour. GATE: Ziggy reviews the autopsy report before
  any fix session is written.
- **Session 7 — the fix** (NOT written yet, deliberately). Its shape
  depends on the autopsy's top failure reason:
  - Threshold too strict → recalibrate validity thresholds from the
    value distributions, tuned on TRAIN clips only, judged on VAL.
  - Detection failure → improve pitch line/stump detection feeding the
    homography, judged per-clip with frames before any aggregate run.
  - Wrong frame → feed homography the Session 4 selector's delivery
    shot instead of the current frame choice.
- **Session 8 — decision gate re-run** (after a fix): Session 5's gate
  script, same 115 VAL clips, physics vs median per field. Physics is
  adopted per-field only where it beats the median on VAL. Same totals
  must be reported with mode, split, n, approx-tol.

## Standing hard rules (all Route A sessions)

- No wallet files, mnemonics, or keys. No btcli. No Fly deploy, no GHCR
  push, no on-chain commits. Registration/stake is David's, later,
  separately.
- Preserve `BLACKLIST_ENABLED=false` / `VERIFY_ENABLED=false` verbatim.
- Never modify labels, `split.json`, `median_baseline.json`,
  `validate_balltrack.py`, or any published baseline number. If your
  numbers disagree with a published one, report it — do not adjust
  anything to force a match.
- Every score claim names: mode, split, n clips, and "approx-tol".
- Test split is touched once, at the very end of the whole project.
  Route A tuning happens on train, judging on val.
