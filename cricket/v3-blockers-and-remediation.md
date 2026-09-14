# Cricket Miner v3 — Two Verified Blockers and How to Clear Them

Two blockers were verified outside the v3 spec's own bug condition (which concerns axon
visibility, commitment visibility and reachability). Neither is in the v3 requirements. Both need
a decision before the plan runs to completion.

| # | Blocker | Verified | What it costs if ignored |
|---|---|---|---|
| 1 | The cricket predictor is a hardcoded stub; a complete implementation sits unreached in the same file | Yes | The miner answers every challenge with 13 constants tuned to one fixture |
| 2 | No Bittensor wallet is present on this machine | Yes | The axon-publishing step (design step 7 / tasks.md task 14) cannot be executed at all |

A note on numbering, because the two schemes collide: the design document numbers the deployment
*steps* 1–10, tasks.md numbers *tasks* 1–19. "Step 7" (publish the axon) is tasks.md **task 14**.
Where this document says task N it means the tasks.md number.

---

## Blocker 1 — the predictor is a constant, and the real pipeline is dead code

### What is actually running

`scorevision/miner/private_track/trajectory.py` defines `TrajectoryAnalyser.analyse()`, the only
entry point reached in production. It returns a literal dict of 13 constants and never references
its `trajectory` argument:

| Field | Returned | Field | Returned |
|---|---|---|---|
| `release_y` | 0.65 | `bounce_x` | 4.05 |
| `bounce_y` | 0.10 | `impact_x` | 2.50 |
| `stump_y` | 0.04 | `interception_distance` | 1.55 |
| `impact_y` | 0.08 | `kph` | 87.5 |
| `release_z` | 2.10 | `swing_angle` | −0.25 |
| `stump_z` | 0.75 | `deviation` | 1.55 |
| `impact_z` | 0.38 | | |

The same file contains a complete implementation that nothing calls:

| Method | What it does |
|---|---|
| `_analyse_endon` | bounce index from the second derivative of depth against time; `kph` from the median frame-to-frame displacement clipped to 50–175; `stump_z` from a two-phase ballistic model (`g = 9.81`, restitution 0.80); `stump_y` by `np.polyfit` extrapolation to the stump plane `x = 0`; swing and deviation from the pre/post-bounce lateral segments; impact point |
| `_analyse_sideon` | the parallel side-on derivation |
| `_select_confident_fields` | confidence-gated blending of trajectory values with defaults, requiring `depth_travel > 6.0 m` (lateral) or `> 8.0 m` (depth) and `y_spread > 0.05 m` |
| `_default_fields` | a documented "74% accuracy baseline" |
| `_fill_defaults` | fills any field the trajectory path did not produce |

The source comments record the sequence of events: "Optimized constants targeting 85%+", "Key
improvements from 74% baseline", "Adjusted kph from 88.0 to 87.5". The real pipeline was written,
measured, then bypassed in favour of tuned constants.

`PitchHomography` and `BallTracker` are genuinely implemented. They are not stubs, and they do
run: both fixtures driven through the real `POST /challenge` path in the built v2.5 image returned
byte-identical prediction items with `processing_time` of 5.34 s and 2.90 s. Homography and
tracking consume that wall-clock time and their output is then discarded.

### Why the "85%+ across the validation set" claim does not hold

The docstring claims "Target: 85%+ accuracy across validation set (not just single clip)". The
measured evidence contradicts the generalisation, not the single-clip figure.

| Field | Constant returned | be13 groundtruth | efc0 groundtruth |
|---|---|---|---|
| `kph` | 87.5 | 87.58 | 129.21 |
| `bounce_x` | 4.05 | 4.082 | 6.743 |
| `stump_y` | 0.04 | 0.046 | 0.483 |

The constants sit within rounding error of fixture be13 and miss efc0 badly. `kph` is a scored
field, and `bounce_x` carries the single highest weight in `validate.py`'s `WEIGHTS` at 0.23. The
constants are a local maximum on a sample of one.

### `validate.py` cannot currently run

`cricket/validate.py` points `VIDEO_PATH` at `cricket/<hash>.mp4`, but the fixtures live at
`cricket/turbovision/data-training/cricket/`. It exits before scoring anything. Even with the path
fixed it would score the constants, because it calls the same `analyse()`.

Its `GT` block is the correct groundtruth. Its `BASELINE` block is correctly labelled as a
different miner's recorded response, so it is a comparison point and not a claim about this miner.

### Remediation

The fix is mostly re-wiring, not new research:

1. `analyse()` dispatches to `_analyse_endon` or `_analyse_sideon` on `homography.is_endon`.
2. The result passes through `_select_confident_fields`, so low-confidence tracking blends toward
   defaults rather than emitting nonsense.
3. `_fill_defaults` closes any remaining gaps.

State the risk plainly: the dead code has never been scored end-to-end. It may perform worse than
the tuned constants on the two fixtures available. Switching on the basis of "it is the real
implementation" would be a preference, not a measurement.

The correct order is therefore:

1. Make `validate.py` runnable — fix `VIDEO_PATH` to resolve against
   `turbovision/data-training/cricket/`, and allow both fixtures rather than one hardcoded hash.
2. Score the real pipeline on both fixtures and record the numbers alongside the constants.
3. Only then decide: switch `analyse()` over, keep the constants, or blend (constants as the
   default set, trajectory values admitted through `_select_confident_fields`).

Two fixtures is far too small a validation set to justify any of those three outcomes. More
groundtruth clips are the real prerequisite; the scoring work above is what makes additional clips
useful the moment they arrive.

### The preservation tests will fail, and that is the intended signal

Task 2 recorded the v2.5 baseline by observation, which means it locked in the **constant-stub**
behaviour. `tests/private/test_v25_baseline_predictions.py` includes an AST assertion that
`analyse()` never reads `trajectory`. When the predictor is rewired, that assertion fails by
design.

That failure is the signal, not a regression. It must be updated deliberately at the point of
rewiring, in the same change, with the new recorded values — never silenced ahead of time to keep
the suite green. Clause 3.3 ("prediction values identical") and the spec's "Out of scope — model
accuracy" note are both scoped to v3 and both stop applying the moment this work starts.

---

## Blocker 2 — no Bittensor wallet on this machine

### What was checked

| Check | Result |
|---|---|
| `~/.bittensor` on Windows | does not exist |
| `~/.bittensor/wallets` | does not exist |
| any `hotkeys` directory under the Windows user profile | none found |
| `btcli` on the Windows PATH | not present |

The miner is nonetheless registered, so a wallet controlling the hotkey exists somewhere:

| | |
|---|---|
| Network / netuid | finney, 44 |
| UID | 207 |
| Hotkey | `5CyQ9buHwqgCS7158ytsX8BQvT7WSEH8gDMWq7tqUV3Fshsa` |
| Coldkey | `5F2TqN39BBGYjcmMQuN3pWaGWq2Ymf3iy5WsLhfV6YtXoUkF` |
| Metagraph | n = 256 |

WSL is installed with `Ubuntu-24.04` (currently Stopped) plus `docker-desktop`. `btcli` is
Linux-first and the repo's `auto_register.sh`, `aggressive_register.sh` and `smart_register.sh`
are bash, which makes the WSL home directory the most likely location. **This is unconfirmed.** It
is the first thing to check, not a finding.

### Handling constraint — read this before running anything

The agent must never handle, read, echo or transmit the coldkey, the hotkey file contents, or any
mnemonic. Wallet material must never be copied into the E2B sandbox or any other remote host.
Signing happens locally, on the machine that holds the wallet, only. The only wallet-derived value
that may be passed around, logged or placed in `fly.toml` `[env]` is the hotkey ss58, which is
public.

### Steps, in order

1. **Check WSL.**

   ```bash
   wsl -d Ubuntu-24.04 -- bash -lc 'ls -1 ~/.bittensor/wallets; btcli wallet list'
   ```

   The question to answer is not "is there a wallet" but "does a coldkey there own hotkey
   `5CyQ9buH…`". Match on the ss58, not on the directory name.

2. **If found in WSL, choose where task 14 runs.** Either execute the serve extrinsic from inside
   WSL, or copy `~/.bittensor/wallets` into the Windows profile. WSL is the lower-risk option
   because it avoids copying key material at all. The Gate 0b venv would then need to live in WSL
   too, so that the SDK probes and the extrinsic use the same environment.

3. **If not in WSL**, check the other machines the miner was registered from. Registration
   happened somewhere; that host has the wallet.

4. **Last resort — regenerate from the mnemonic**, `btcli wallet regen_coldkey` then
   `btcli wallet regen_hotkey`. The user runs these interactively. The agent does not see the
   mnemonic.

5. **If the hotkey is unrecoverable, re-registration is required.** This is the expensive branch:
   a new UID, a fresh burn (~743378 rao at last check), and two things in the spec become invalid —
   Gate 0a's assumption that UID 207 is ours, and clause 3.7's preservation baseline on
   `metagraph.hotkeys[207]`. Task 1's Gate 0a is already a hard STOP for this reason; an
   unrecoverable hotkey reaches the same conclusion by a different route. Re-plan rather than
   continuing down the task list.

### Wallet name — reconcile before task 3.1

`settings.py` defaults `BITTENSOR_WALLET_COLD` and `BITTENSOR_WALLET_HOT` to `"default"`. Task 3.1
specifies `BITTENSOR_WALLET_COLD=cricket_miner`, which is **unverified**.
`logs/metagraph44_final_2.txt` renders UID 207 as the literal string `default` where other UIDs
show an ss58 — weak evidence that the coldkey may in fact be named `default`, not proof.

Whichever name step 1 confirms must be reconciled with task 3.1's `cricket_miner` assumption
before task 3.1 is actioned, and with the `bt.wallet(name=…, hotkey=…)` call in task 14. A wrong
wallet name there fails loudly rather than silently, but it fails after the free/paid boundary.

---

## Sequencing — does this need resolving before building v3?

No for Blocker 1. Partly for Blocker 2.

Neither blocker gates tasks 4, 5 or 6 — `Dockerfile.v3`, the `/health` route, the header gate.
Those are image and code work with no wallet and no predictor dependency.

**Blocker 2 gates one thing: task 14, the axon publish.** That is the step that actually makes the
miner visible, so v3 can be built and validated locally but cannot be completed until the wallet
is located. Task 3.1's wallet-name line is a soft dependency on the same answer.

**Blocker 1 gates nothing in v3.** It determines what the miner is *worth* once reachable, not
whether it is reachable.

The ordering follows from that. While the axon is unpublished the miner receives zero requests, so
predictor accuracy is worth exactly nothing — reachability comes first. The predictor work is
fully verifiable offline against the local fixtures, touches no deployment artefact, and can
proceed in parallel without waiting on the wallet or on any spend.

| Task | Blocked? | By |
|---|---|---|
| 4 — `Dockerfile.v3` | No | — |
| 5 — `/health` route | No | — |
| 6 — header gate | No | — |
| 7 — `--dockerfile` CLI option | No | — |
| 8 — `fly.toml` → `[[services]]` | No | — |
| 9 — Dockerfile parity guard | No | — |
| 10 — local fix + preservation validation | No | — |
| 11 — free/paid checkpoint | Soft | Blocker 2, via task 3.1's wallet name in `.env` |
| 12 — allocate dedicated IPv4 + deploy | No | — |
| 14 — publish the axon | **Yes** | Blocker 2 — no wallet, no extrinsic |

Tasks 13 and 15–18 sit downstream of task 14 and are omitted from the table; they inherit its
blockage transitively.

### One genuine interaction: `fly.toml` `[env]`

`fly.toml` currently carries:

```toml
[env]
  MINER_MODE = "cricket_delivery"
  BLACKLIST_ENABLED = "false"
  VERIFY_ENABLED = "false"
```

Those two `false` literals are load-bearing. `security.py` defaults both to `"true"`
(`os.environ.get("BLACKLIST_ENABLED", "true")`, same for `VERIFY_ENABLED`), and the true path
imports `fiber`, which the image does not install. Task 8.1's rewrite must preserve `[env]`
verbatim — including `MINER_MODE = "cricket_delivery"` — or the container stops booting.

This contradicts task 8.1 as currently written, which instructs omitting both keys "rather than
setting them `false`, so the `security.py` defaults are not overridden". Given the verified
defaults, omission enables verification and blacklisting, and the import of `fiber` fails. Task
8.1's text needs correcting before it is actioned; the explicit `false` literals stay. Task 19
already records that `VERIFY_ENABLED=true` must not be set until signing-message parity is proven,
which is the same conclusion reached from the other direction.
