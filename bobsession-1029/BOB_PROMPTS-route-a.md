# BOB PROMPTS — Cricket Route A

Bob settings (David's settled setup): Agent mode; auto-approve
Read / Edit / Execute / Todo ON; MCP / Skill / Subtask / Subagent /
Mode OFF. One session per Bob task; permissions are per-task, so
re-check the four boxes when starting.

Run sessions in order. Send each report back to Ziggy for verification
before starting the next session. Session 7 is not written yet — it is
gated on Ziggy's review of the Session 6 report (see README.md).

---

## Session 6 — Homography validity autopsy

```
SESSION 6 — HOMOGRAPHY VALIDITY AUTOPSY (instrumentation + report only; changes NO prediction behaviour)

PREFLIGHT — do this first and STOP if it fails:
Your working directory must be the ibmbob repo root
(C:\Users\fapul\Source\repos\ibmbob, or /mnt/c/Users/fapul/Source/repos/ibmbob in WSL).
Print the working directory and verify ALL of these exist:
  cricket/turbovision/scorevision/miner/private_track/pitch_homography.py
  cricket/turbovision/scorevision/miner/private_track/trajectory.py
  cricket/turbovision/scorevision/miner/private_track/predictor.py
  cricket/data-training/balltrack/labels.jsonl
  cricket/data-training/balltrack/split.json
  cricket/session5_decision_gate.py
If any is missing, STOP and report exactly what you see. Do not work in
any other folder.
Then record the pristine state in your report: output of
`git rev-parse HEAD` and `git status --porcelain` (repo, branch, and
whether the tree is clean) BEFORE you edit anything.

CONTEXT
Session 5's decision gate: physics+fallback 14.79% vs median 26.23% on
115 VAL clips (approx-tol). Your Session 5 summary reported
hom.valid=False on essentially all VAL clips, forcing fixed fallback
pixel scales for every measurement. That claim is not yet backed by a
written report. This session verifies or refutes it, with counts, and
finds WHICH validity sub-checks fail and by how much. Nothing else.

HARD RULES
- No wallet files, mnemonics, or keys. No btcli. No Fly deploy, no GHCR
  push, no on-chain commits.
- Preserve BLACKLIST_ENABLED=false / VERIFY_ENABLED=false verbatim.
- Do not modify labels, split.json, median_baseline.json,
  validate_balltrack.py, or any published baseline.
- Do not download anything from scoredata.me (rate limits). Use only
  clips already on disk.
- Candidate is David Anderson.

ALLOWED CHANGES (exact paths; everything else is read-only)
- EDIT: cricket/turbovision/scorevision/miner/private_track/pitch_homography.py
  — ONLY to add per-sub-check recording behind the env flag
  HOMOGRAPHY_DEBUG=1. No threshold changes, no detection changes, no
  logic changes. With the flag unset, behaviour and outputs must be
  identical to today.
- CREATE: cricket/homography_autopsy.py (runner script).
- CREATE outputs under cricket/data-training/balltrack/:
  homography_autopsy.jsonl, homography-autopsy.md,
  homography-frames/<reason-code>/ (frames).
- READ-ONLY: trajectory.py, ball_tracker.py, predictor.py,
  shot_selection.py, routes.py, session5_decision_gate.py,
  validate_balltrack.py.

TASKS
1. Read pitch_homography.py and enumerate EVERY check that can make the
   returned homography invalid (valid=False), including checks inherited
   from anything it calls. Give each a short reason code
   (e.g. NO_LINES, SCALE_OUT_OF_RANGE). List them in the report.
   STOP CONDITION: if validity is decided in more than one code path,
   STOP and report the paths instead of instrumenting a guess.
2. Instrument: with HOMOGRAPHY_DEBUG=1, every homography computation
   records, per clip: valid True/False, ALL sub-check values (numbers,
   not just pass/fail), and the reason code(s) that failed.
3. Runner: run the instrumented homography over at least 50 clips from
   the VAL split (per split.json) that exist on disk in
   data/videos_sample/. Use exactly the frames the production predictor
   path feeds to homography — trace that call path and say in the
   report which frame(s) you used and why they are the production ones.
   State how many VAL clips were on disk, how many you ran, and how you
   chose them.
4. Regression proof: with HOMOGRAPHY_DEBUG unset, re-run
   cricket/session5_decision_gate.py on its usual 115 VAL clips (or the
   largest on-disk subset of them; state n) and show the totals match
   the Session 5 report (median 26.23, physics_fb 14.79 on n=115;
   if your n differs, recompute those two modes on your subset with
   the un-instrumented code path and show instrumented == un-instrumented).

REPORT — write cricket/data-training/balltrack/homography-autopsy.md
and paste it in your reply:
- FIRST PARAGRAPH: the single most common failure reason, its count
  and percentage, and the overall valid rate (n stated).
- Preflight block: working directory, git HEAD, branch, clean/dirty.
- The full list of validity sub-checks with reason codes.
- Reason-frequency table: clips failing each sub-check, alone and in
  combination. Counts must sum consistently with n.
- For the top 3 reason codes: the distribution of the failing value vs
  its threshold (min / median / max, and how many clips fall within
  10% of the threshold), at least 5 example clips each, and one saved
  frame per example (the exact frame fed to homography) in
  homography-frames/<reason-code>/.
- For every clip where valid=True (if any): clip id and all sub-check
  values — the contrast is the diagnostic.
- Your classification of each top reason, one of: DETECTION_FAILURE
  (lines/stumps not found), THRESHOLD_TOO_STRICT (values cluster near
  the boundary), WRONG_FRAME (frame shows no usable pitch view) —
  with the evidence for the classification.
- Per-clip raw data in homography_autopsy.jsonl (one JSON object per
  clip: clip id, valid, all sub-check values, failed reason codes).

ACCEPTANCE (all required)
- Flag-off totals match Session 5 (task 4) — instrumentation changed
  nothing.
- Reason table sums to the stated n.
- Top-3 reasons each have >= 5 frames on disk at the stated paths.
- Commit the instrumentation + runner + report to the cricket-miner-v3
  branch with message: "Session 6: HOMOGRAPHY_DEBUG instrumentation and
  validity autopsy (no behaviour change)". Report the commit hash.
```
