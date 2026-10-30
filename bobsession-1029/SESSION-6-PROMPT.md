# Bob Session 6 — Homography validity autopsy (cricket v4 follow-on)

Paste-ready prompt. Run in the ibmbob repo on the AM5, Agent mode,
auto-approve Read/Edit/Execute/Todo ON; MCP/Skill/Subtask/Subagent/Mode OFF.

Context you need: Session 5's decision gate found physics+fallback scores
14.79% vs median 26.23% on 115 VAL clips, and reported `hom.valid=False`
on essentially all VAL clips, forcing fixed fallback pixel scales for
every measurement. If homography never validates, no downstream tracker
work can be judged. This session finds out WHY, with counts. It changes
no prediction behaviour.

---

SESSION 6 — HOMOGRAPHY VALIDITY AUTOPSY (report + instrumentation only)

Working repo: the ibmbob repo (cricket/turbovision). Hard rules, same as
Sessions 1–5: no wallet files, mnemonics or keys; no btcli anything; no
Fly deploy, no GHCR push, no on-chain commits; preserve
BLACKLIST_ENABLED=false / VERIFY_ENABLED=false verbatim if any config is
touched; candidate is David Anderson; do not modify labels, split.json,
median_baseline.json, validate_balltrack.py, or any published baseline.

DELIVERABLES
1. Instrumentation in pitch_homography.py (or the module that computes
   homography validity): every validity sub-check that can set
   valid=False gets a named reason code, logged/recorded per clip behind
   an env flag HOMOGRAPHY_DEBUG=1. Default behaviour with the flag off
   must be byte-identical predictions to today. No threshold changes, no
   detection changes — observe only.
2. A runner script cricket/homography_autopsy.py that runs the
   instrumented homography over at least 50 VAL-split clips that exist
   on disk in data/videos_sample/ (use the frozen split; state exactly
   how many clips ran and how they were chosen), collecting per-clip:
   valid True/False, the reason code(s) that failed, and the numeric
   value of each sub-check (not just pass/fail).
3. Report at cricket/data-training/balltrack/homography-autopsy.md:
   - n clips, overall valid rate.
   - Reason-code frequency table: how many clips failed each sub-check,
     alone and in combination. Counts must sum consistently with n.
   - For the top 3 reason codes: at least 5 example clips each, with
     the sub-check values AND a saved frame (the exact frame fed to
     homography) per example under
     cricket/data-training/balltrack/homography-frames/<reason>/.
   - Your classification of each top reason: detection failure (lines /
     stumps not found), threshold too strict (values near the boundary —
     show the value distribution vs the threshold), or wrong frame /
     wrong shot (frame shows no usable pitch view).
   - If valid=True occurs on any clip, list those clips and their
     sub-check values too — the contrast is the diagnostic.

ACCEPTANCE
- Flag-off regression: run the Session 5 decision-gate script (or the
  Session 1 harness modes) on at least 20 clips with HOMOGRAPHY_DEBUG
  unset and show totals unchanged from the Session 5 report
  (median 26.23 / physics_fb 14.79 on the 115-clip set, or state the
  exact subset you ran and its previously reported numbers).
- Reason table counts sum to the stated n; every top-3 reason has its
  5 frames on disk.
- Report states the single most common failure reason in its first
  paragraph, with its count and percentage.

STOP CONDITIONS
- If homography validity is not computed in one place (multiple code
  paths), STOP and report the paths you found instead of guessing.
- If fewer than 30 VAL clips are available on disk, report the exact
  count and run what exists; do not download (scoredata.me rate limits).
