# Cricket Miner v3 Bugfix Design

## Overview

The cricket delivery miner (subnet 44, UID 207, Fly app `cricket-delivery-miner`) has never
received a validator challenge. It is simultaneously **invisible** to the validator's
private-track registry and **unreachable** at the network level. Three independent defects each
individually reduce challenge volume to zero, so fixing any one or two of them produces no
observable change. A fourth defect (authentication disabled, no health probe, oversized image)
is not blocking today but becomes an exposure the moment reachability is fixed.

The fix is a chained sequence, not a set of parallel workstreams:

```
Pre-flight (UID 207 alive? SDK installed? .env for GHCR? cost accepted?)
   ↓
Build + verify Dockerfile.v3 locally          ── reversible, no spend
   ↓
Add --dockerfile to sv deploy-pt-miner        ── additive CLI change, no spend
   ↓
Migrate fly.toml to [[services]] + /health    ── reversible, no spend
   ↓
Allocate dedicated IPv4 + deploy              ── first spend (~$2/mo)
   ↓
curl raw http://<v4>:8000/health  ≠ 000       ── GATE: confirms the IP before it is committed
   ↓
Publish axon via SDK serve_extrinsic          ── RATE LIMITED on-chain; one shot
   ↓
Push image to GHCR + commit full payload      ── append-only
   ↓
Grant DataAndMike Read on the GHCR package
   ↓
"Challenge received" in fly logs              ── end-to-end confirmation
```

The ordering is load-bearing in two places. The dedicated IPv4 must exist **and be proven
reachable** before the serve extrinsic is submitted, because on-chain serving is rate limited and
a wrong IP costs a wait before retry. The image must be pushed before the commitment can
reference it, because the commitment carries `image_repo`/`image_tag` that must resolve to a real
image or spot-check pulls fail.

Strategy is minimal and targeted: no change to prediction logic, no re-registration, no new UID.

## Glossary

- **Bug_Condition (C)**: The deployment state in which the miner receives no validator
  challenges — axon unpublished, commitment unreadable by the private registry, or the raw
  `http://<ip>:8000` path unreachable.
- **Property (P)**: The desired end state — the miner is discoverable in
  `get_registered_miners`, reachable over plain HTTP on port 8000, and logs
  `Challenge received`.
- **Preservation**: Prediction outputs, the `.fly.dev` HTTPS path, `cv2`/`numpy` imports, the
  warm-machine guarantee, and UID/hotkey identity must all be unchanged by the fix.
- **F / F'**: The v2.5 deployment (original) and the v3 deployment (fixed).
- **Axon**: The on-chain `(ip, port, ip_type)` record the validator reads from
  `metagraph.axons[uid]`. Not published automatically by anything in `scorevision`.
- **Registered miner**: A hotkey that survives every filter in
  `validator/central/private_track/registry.py:get_registered_miners`.
- **Revealed commitment**: A commitment written with
  `set_reveal_commitment(..., blocks_until_reveal=1)`, the only kind visible to
  `get_all_revealed_commitments`.
- **Element ID**: The manifest string the registry matches by exact comparison
  (`manako/DetectCricketDelivery` vs `manako_DetectCricketDelivery` are different miners).
- **Header gate**: A zero-dependency FastAPI dependency requiring the four validator headers to
  be present. A noise filter, **not** authentication.
- **Spot-check**: The validator pulls the committed GHCR image, runs it, and compares its output
  to the live endpoint. Divergence scores 0 and risks blacklisting.
- **Dockerfile parity invariant**: `fly.toml`'s `[build].dockerfile` and the `--dockerfile`
  argument passed to `sv deploy-pt-miner` MUST name the same file. Divergence means Fly runs one
  image and GHCR holds another, which is precisely the spot-check failure condition above.

## Bug Details

### Bug Condition

The miner receives zero challenges when **any** of three independent conditions holds. This is a
disjunction, which is why partial fixes are invisible: `axonInvisible` drops the miner at
`registry.py:92`, `commitInvisible` drops it at `registry.py:47-52` and `:121`, and `unreachable`
means the validator's `httpx.post` never completes.

**Formal Specification:**

```
FUNCTION isBugCondition(X)
  INPUT: X of type MinerDeploymentState
  OUTPUT: boolean

  axonInvisible   ← (X.axon.ip = "0.0.0.0") OR (X.axon.port = 0) OR (X.axon.ip_type ≠ 4)

  commitInvisible ← (X.commit.track ≠ "private")
                    OR (X.commit.role ∉ {NULL, "miner"})
                    OR (X.commit.image_repo = "") OR (X.commit.image_tag = "")
                    OR (X.commit.element_id ≠ X.manifest.element_id)
                    OR (NOT X.commit.revealed)
                    OR (X.commit.netuid ≠ 44) OR (X.commit.network ≠ "finney")

  unreachable     ← curl_status("http://" + X.axon.ip + ":" + X.axon.port + "/health") = 000

  RETURN axonInvisible OR commitInvisible OR unreachable
END FUNCTION
```

`X.commit.netuid`/`X.commit.network` are additions to the requirements-phase definition. See
drift finding **D3** — `env.example` ships `SCOREVISION_NETUID=423` and
`BITTENSOR_SUBTENSOR_ENDPOINT=test`, so a commitment can be structurally perfect and still land
on the wrong chain.

_Covers clauses 1.1–1.12._

### Examples

| Input | Expected | Actual (v2.5) |
|---|---|---|
| `registry.get_registered_miners` enumerates UID 207 | UID 207 appears in the returned list | dropped at `registry.py:92`, **no log line** (clause 1.1) |
| `sv commit_recover --element-id manako/DetectCricketDelivery` | private-track commitment | `{"role":"miner_recover","element_id":...,"hotkey":...}` — no `track` key, fails the first filter immediately (clauses 1.5, 1.6) |
| `curl http://66.241.124.34:8000/challenge` | HTTP status | `000` — no response; port 8000 never published (clause 1.10) |
| `curl http://66.241.124.34/challenge` (no Host header) | HTTP status | `000` — shared IPv4 routes only by Host/SNI (clause 1.11) |
| `curl http://66.241.124.34/challenge -H "Host: ..."` | 200 | `301` — `force_https = true` (clause 1.12) |
| `curl https://cricket-delivery-miner.fly.dev/challenge` | 200 | `500` — app alive, GET path has no `video_url` (clause 1.15) |
| `GET /health` | 200 | `404` — only `/challenge` is registered (clause 1.14) |
| `btcli axon set --netuid 44 ...` per `MINER.md:21` | axon published | subcommand absent in bittensor-cli 9.x (clause 1.3) |
| Axon published with `ip_type=6` | validator reaches miner | malformed URL — `miners.py:27` does not bracket IPv6 (clause 1.4) |

**Correction to specv3.md (drift D5):** specv3.md states a bare `GET /challenge` "constructs an
invalid `ChallengeRequest`". It does not. `server.py` registers
`methods=["GET","POST"]` and builds a **valid** `ChallengeRequest` with `video_url=None`. The
500 originates downstream in `routes.py`, where `predict_cricket_delivery(request)` raises on the
missing URL and the `except Exception` handler converts it to `HTTPException(500)`. Observable
behaviour is identical, so clause 1.15 stands unchanged; the mechanism description does not.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**

- `https://cricket-delivery-miner.fly.dev/challenge` continues to serve over TLS on 443 (3.1)
- `MINER_MODE = "cricket_delivery"` continues to route to `predict_cricket_delivery` and return
  `PredictionPayload(type="cricket_delivery", item=...)` (3.2)
- Prediction values are bit-identical — `trajectory.py` constants untouched, 92.8% local score
  preserved (3.3)
- `import cv2` and `import numpy` continue to succeed — `libglib2.0-0` retained (3.4)
- At least one machine stays warm: `auto_stop_machines = false`, `min_machines_running = 1` (3.5).
  **These already exist in the current `fly.toml`; migrating to `[[services]]` must carry them
  over, not introduce them.**
- Responses continue to complete inside the validator's 30 s timeout (3.6)
- UID 207 on the same hotkey — no re-registration, no new UID (3.7)
- `soccer_action` and TCG (`image_url`) branches in `routes.py` unmodified (3.8)
- `POST /challenge` keeps the same path and body contract; the header gate adds a precondition,
  it does not change the request shape (3.9)
- Image and `fly.toml` remain restorable from git; the axon remains reversible via `reset_axon`
  (3.10)
- **`sv deploy-pt-miner` behaves identically when `--dockerfile` is omitted (3.11).** The new
  option defaults to `None`, and `build_miner_image` resolves `None` to the current hardcoded
  `repo_root / "scorevision/miner/private_track/Dockerfile"`. Every existing invocation — and any
  other track or script that calls `build_miner_image` — must build exactly the file it builds
  today. The task MUST locate every caller of `build_miner_image` and confirm it is unaffected.
  A repo-wide search at design time found exactly one caller, `deploy_miner` at
  `private_track_miner.py:217`, but this is shared CLI code other agents may be editing, so the
  search must be repeated at implementation time.

**Scope:**

Every input that does not involve the three blockers is untouched. Specifically out of the blast
radius: the predictor and its constants, the response schema, the `soccer_action`/TCG code paths,
the wallet and hotkey identity, and the `.fly.dev` hostname.

The actual expected correct behaviour is defined in Correctness Properties (Property 1).

## Hypothesized Root Cause

Unlike a typical bugfix, root cause here is **confirmed rather than hypothesised** — each
blocker was read directly from the validator source in this repository. What remains genuinely
uncertain is the current *state* of two things that cannot be checked offline (see Pre-Flight
Gates and Open Questions).

1. **No code path publishes an axon.** `serve_axon` and `serve_extrinsic` appear nowhere in
   `scorevision`. The miner server does not publish its own endpoint at startup, so unless it was
   done manually, UID 207's axon record has never been written. `registry.py:92`
   (`if not axon.ip or not axon.port: continue`) then drops it with no log line. Confidence:
   high on the mechanism, unverified on the current value of `axon_info`.

2. **The documented publication path does not exist.** `MINER.md:21` instructs
   `btcli axon set`, absent from bittensor-cli 9.x, whose groups are wallet / stake / subnets /
   sudo / root / weights / utils / view / config. Newer Bittensor docs list an `axon` group, but
   that belongs to a different CLI generation built around `btcli query`/`btcli tx`. Compounding
   it, `btcli subnet metagraph` does not display axon records, so the failure is invisible from
   CLI output — confirmed against `logs/metagraph44_final_2.txt`, where the UID 207 block shows
   only emission/incentive/dividends and `updated 314b ago`.

3. **The wrong commitment command was run.** `sv commit_recover` writes
   `RECOVERY_COMMIT_ROLE = "miner_recover"` and exists to restore *public*-track commitments from
   signed score shards — `as_miner_commitment()` returns HuggingFace `model`/`revision`
   coordinates. The payload has no `track` key at all, so
   `_pick_latest_private_commit_for_element` rejects it on the very first filter, then would
   reject it twice more on `role` and on missing `image_repo`/`image_tag`. No amount of waiting
   changes this.

4. **Fly's edge never exposes port 8000.** `[http_service]` with `internal_port = 8000` publishes
   only 80 and 443 at the edge. A **shared** IPv4 compounds it: shared IPs route solely by TLS
   SNI or HTTP `Host`, and `miners.py:27` builds `f"http://{miner.ip}:{miner.port}/challenge"`
   with neither. `force_https = true` would 301 anything that did arrive.

5. **Security is disabled and cannot simply be re-enabled.** `[env]` sets
   `BLACKLIST_ENABLED`/`VERIFY_ENABLED` to `"false"`, overriding `security.py` defaults that are
   both `true` when unset. Turning them on pulls in `fiber` — and, per the v3.1 parity risk
   below, may 401 every legitimate request.

## Correctness Properties

Property 1: Bug Condition — Validator Can Discover And Reach The Miner

_For any_ deployment state where the bug condition holds (`isBugCondition` returns true), the
fixed deployment SHALL present a published IPv4 axon on port 8000, a revealed private-track
commitment carrying `role: "miner"`, `track: "private"`, non-empty `image_repo`/`image_tag` and
an `element_id` exactly matching the manifest, and SHALL answer a plain-HTTP request on
`http://<dedicated_ipv4>:8000/health` with `200` — such that `get_registered_miners` includes
UID 207 and `fly logs` shows `Challenge received`.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11, 2.12, 2.13, 2.14, 2.15**

Property 2: Preservation — Non-Blocker Inputs Behave Identically

_For any_ input where the bug condition does NOT hold (`isBugCondition` returns false), the fixed
deployment SHALL produce the same result as the original, preserving prediction values, the
`.fly.dev` HTTPS path, `cv2`/`numpy` importability, the warm-machine guarantee, the
`soccer_action`/TCG code paths, and UID/hotkey identity.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10**

Property 3: Prediction Equivalence Across Images

_For any_ well-formed cricket `ChallengeRequest`, the v3 image SHALL return a
`CricketDeliveryPrediction` equal to the v2.5 image's, because `predictor.py` and
`trajectory.py` are unmodified and the dropped packages (`libgl1`, `cryptography`) are imported
by nothing on the prediction path.

**Validates: Requirements 3.2, 3.3, 3.4**

Property 4: Header Gate Admits Exactly The Validator's Header Set

_For any_ request carrying all four of `validator_hotkey`, `signature`, `miner_hotkey`, `nonce`
with `miner_hotkey` equal to our own hotkey, the gate SHALL allow it through unchanged; _for any_
request missing one or more of those headers, or carrying a foreign `miner_hotkey`, the gate
SHALL reject it before the predictor runs; and `GET /health` SHALL be exempt.

**Validates: Requirements 2.16, 2.17, 2.18, 3.9**

Property 5: Preservation — `--dockerfile` Is Additive And Backward Compatible

_For any_ invocation of `sv deploy-pt-miner` that omits `--dockerfile`, the build SHALL use
exactly the same Dockerfile path as before the option existed
(`repo_root / "scorevision/miner/private_track/Dockerfile"`), and _for any_ invocation that
supplies it, the build SHALL use that path resolved against `repo_root` — raising rather than
silently falling back when the resolved path does not exist, since a silent fallback recreates
the two-image divergence the option exists to prevent.

**Validates: Requirements 3.11**

## Fix Implementation

### Pre-Flight Gates — before any spend or on-chain action

These gates precede step 1. Each can invalidate the plan, and two of them cost money or
rate-limited on-chain actions if skipped.

**Gate 0a — Does UID 207 still exist, on our hotkey?**

Immunity is 7500 blocks (~25 h) and a UID with zero incentive is deregistration-eligible once
immunity lapses. `logs/metagraph44_final_2.txt` shows UID 207 active with `updated 314b ago`, but
that is a snapshot of unknown age. If the UID is gone the entire plan changes: re-registration
first, at a burn of ~743378 rao (~τ0.000743), and a new UID to publish against.

```python
import bittensor as bt
sub = bt.subtensor(network="finney")
mg  = sub.metagraph(netuid=44)
print(mg.hotkeys[207] if len(mg.hotkeys) > 207 else "UID 207 does not exist")
# must equal our hotkey ss58 — a different hotkey means we were deregistered and replaced
```

Success criterion: `mg.hotkeys[207]` equals our hotkey ss58. **STOP and re-plan if not.**

**Gate 0b — Bittensor SDK available.**

Neither `btcli` nor the `bittensor` SDK is installed in either local venv, so Gates 0a/0c and
step 5 cannot run as-is. Install into a venv (`pip install bittensor`) or locate one that already
has it. This is a prerequisite for three separate steps, so resolve it first.

Success criterion: `python -c "import bittensor; print(bittensor.__version__)"` succeeds. Use the
same venv for Gate 0d's `get_settings()` print and for `sv`, so all three see one environment.

**Gate 0c — Current axon state recorded.**

```python
print(sub.neuron_for_uid(207, netuid=44).axon_info)
```

Success criterion: the value is written down. `ip=0.0.0.0` or `port=0` confirms Blocker A is
real. A correct IPv4 already present means Blocker A is already resolved and step 5 can be
skipped — worth knowing before spending a rate-limited extrinsic.

**Gate 0d — Commit target chain: currently correct, and the risk runs the other way.**

There is **no `.env` file** anywhere in `cricket/turbovision` — verified with
`Get-ChildItem -Force -Filter ".env*"`, zero results. `get_settings()` calls a bare
`load_dotenv()` and then constructs `Settings(...)` where every field is
`getenv("NAME", <default>)`, with no required-without-default fields, so a missing `.env` does not
raise. The confirmed code defaults are `SCOREVISION_NETUID=int(getenv("SCOREVISION_NETUID", 44))`
(`settings.py:348`) and `BITTENSOR_SUBTENSOR_ENDPOINT=getenv("BITTENSOR_SUBTENSOR_ENDPOINT",
"finney")` (`settings.py:261`).

**So the chain target is already netuid 44 on finney, and that is correct.** This inverts the
gate. The danger is not that `.env` says the wrong thing — it is that creating a `.env` can
*undo* a currently-correct configuration. `env.example` ships:

```
SCOREVISION_NETUID=423
BITTENSOR_SUBTENSOR_ENDPOINT=test
BITTENSOR_SUBTENSOR_FALLBACK=wss://test.finney.opentensor.ai:443
```

Copying `env.example` to `.env` verbatim would silently move the commitment to **testnet netuid
423**, where it is structurally perfect and permanently invisible to the finney netuid-44
registry — indistinguishable from success, since `commit_on_chain` also swallows exceptions
(drift D2). The gate is therefore: *if you create a `.env`, you MUST override the testnet values
`env.example` ships.*

Two further mechanics matter:

- Bare `load_dotenv()` searches from the **current working directory upward**, so which directory
  `sv` is invoked from determines which `.env` is found. **All `sv` commands in this plan MUST be
  run from `cricket/turbovision`.**
- `.gitignore:30` is `.env*`, so a created `.env` is never committed. `env.example` does not match
  that pattern and is tracked — which is why the design does not modify it (see Open Questions).

Positive confirmation, printing effective values rather than trusting the file:

```python
from scorevision.utils.settings import get_settings
s = get_settings()
print(s.SCOREVISION_NETUID, s.BITTENSOR_SUBTENSOR_ENDPOINT)   # must be: 44 finney
```

Success criterion: the print emits `44 finney`, run from `cricket/turbovision`. Run it twice — once
now, to establish the baseline, and again after Gate 0e, since creating a `.env` is the only thing
that can change the answer.

**Gate 0e — Create the minimal `.env` for GHCR credentials (USER ACTION).**

A `.env` is now genuinely required, but only for the GHCR credentials. `get_miner_config` and
`get_ghcr_credentials` (`private_track_miner.py:17-35`) read `os.environ` directly and raise
`ConfigError` when unset:

```python
username = os.environ.get("GITHUB_USERNAME")   # ConfigError if missing
token    = os.environ.get("GITHUB_TOKEN")      # ConfigError if missing
repo_name = os.environ.get("GHCR_REPO", "pt-solution")
```

So the push in step 8 fails fast without them. That is the one thing actually blocked by having
no `.env` — the chain target is not.

**Workspace rules forbid the agent from creating or editing `.env` or any environment file. You
must write this file yourself, at `cricket/turbovision/.env`:**

```
GITHUB_USERNAME=fapulito
GITHUB_TOKEN=<ghcr PAT with write:packages>
GHCR_REPO=pt-solution

BITTENSOR_WALLET_COLD=cricket_miner
BITTENSOR_WALLET_HOT=default

SCOREVISION_NETUID=44
BITTENSOR_SUBTENSOR_ENDPOINT=finney
BITTENSOR_SUBTENSOR_FALLBACK=wss://entrypoint-finney.opentensor.ai:443
```

Deliberately narrow. Rationale for each block:

- **GHCR** — the only genuinely required values. `GHCR_REPO` defaults to `pt-solution` and
  determines both the package name used in the step 9 access grant and the `image_repo` written
  into the commitment, so pinning it keeps those two consistent.
- **Wallet** — `commit_on_chain` builds `Wallet(name=settings.BITTENSOR_WALLET_COLD,
  hotkey=settings.BITTENSOR_WALLET_HOT)`, and the code defaults are `default`/`default`, not our
  cricket wallet.
- **netuid / endpoint / fallback** — redundant with the code defaults, included **deliberately as
  explicit pins** so a later copy-paste from `env.example` cannot silently flip the target back
  to testnet 423. Note the fallback here is the *finney* entrypoint, matching `settings.py:264`,
  not the testnet one in `env.example`.

`GITHUB_TOKEN` is a secret. It lives only in the gitignored `.env`; it must never be echoed into
logs or command output, never committed, and must **not** go into `fly.toml` `[env]` — that file
is tracked. The container does not need it: it is used only by `login_ghcr` on the build host.

Success criterion: `cricket/turbovision/.env` exists with those keys, and Gate 0d's print emits
`44 finney`.

**Gate 0f — Cost decision, made knowingly.**

A dedicated IPv4 is a paid Fly add-on at roughly **$2/month**, on top of current spend of roughly
**$5–8/month** for the 1 GB shared-CPU machine held warm. It is not optional — a shared IP cannot
route a request that carries neither `Host` nor SNI, so there is no free path to fixing Blocker C.

Earnings remain **unknown**, because no validator request has ever arrived. This is a decision
point, not a hidden line item: proceeding commits ~$2/mo against unquantified return.

Success criterion: you have explicitly accepted the added cost.

### Step-by-step Implementation

#### Step 1 — `Dockerfile.v3` (new file, live image untouched)

**File**: `cricket/turbovision/scorevision/miner/private_track/Dockerfile.v3` — **new**. The v2.5
`Dockerfile` is left in place, untouched and never overwritten, so the running deployment is
unaffected until v3 is verified and so rollback is a one-line `fly.toml` edit. `Dockerfile.v3`
stays a genuinely new file because step 3b teaches `sv deploy-pt-miner` to build an explicit path
(drift D1, resolved).

Changes from v2.5:

| Change | Reason | Est. saving |
|---|---|---|
| Drop `libgl1` | `opencv-python-headless` exists precisely to avoid GL/GUI linkage; `libgl1` drags in mesa, libdrm and X libraries never loaded | ~50–80 MB |
| Drop `cryptography==41.0.7` | Nothing on the miner path imports it. `security.py` imports only `os` and `fastapi` at module level, and `fiber` lazily inside `verify_request`. Also removes `cffi`/`pycparser` | ~10 MB |
| Keep `libglib2.0-0` | Some `opencv-python-headless` builds still link it. Removing it is the one change that could break `import cv2` | — |
| `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUNBUFFERED=1` | Smaller layers; unbuffered logs so `fly logs` shows the first validator request without delay | small |

```dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

RUN pip install --no-cache-dir \
    fastapi==0.104.1 \
    uvicorn==0.24.0 \
    httpx==0.25.2 \
    pydantic==2.5.2 \
    opencv-python-headless==4.8.1.78 \
    numpy==1.26.2

COPY scorevision/miner/private_track/*.py ./scorevision/miner/private_track/
COPY scorevision/utils/logging.py scorevision/utils/schemas.py ./scorevision/utils/
RUN echo "" > scorevision/__init__.py && \
    echo "" > scorevision/miner/__init__.py && \
    echo "" > scorevision/utils/__init__.py

EXPOSE 8000

CMD ["uvicorn", "scorevision.miner.private_track.server:app", \
     "--host", "0.0.0.0", "--port", "8000"]
```

**Constraint on new code (clause 2.19/2.20 interaction):** the image copies only
`miner/private_track/*.py` plus `utils/logging.py` and `utils/schemas.py`. The `/health` route
and the header gate must therefore import nothing outside that set — stdlib and `fastapi` only.

Gate: `python -c "import cv2, numpy"` must succeed **inside the built container** before deploy.
If a shared object is missing, add back only the library named in the error. Do **not** reinstate
`libgl1` reflexively (clause 2.20).

#### Step 2 — `/health` endpoint

**File**: `scorevision/miner/private_track/server.py`

Add a route that returns 200 without invoking the predictor and **without** the security
dependencies, so Fly's health check and the reachability curl both pass (clause 2.18):

```python
@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "mode": os.getenv("MINER_MODE", "soccer_action")}
```

Registered separately from `/challenge`, so it inherits neither `get_security_dependencies()`
nor the new header gate. This is what makes `curl http://<v4>:8000/health` a clean reachability
probe: a `200` isolates network reachability from predictor behaviour, and the existing
`/challenge` 500 stops looking like a genuine failure in `fly logs` (clauses 1.14, 1.15).

#### Step 3 — Header gate

**File**: `scorevision/miner/private_track/security.py`

`build_signed_headers` sends **both** prefixed and bare variants —
`X-Validator-Hotkey`/`Validator-Hotkey`, `X-Nonce`/`Nonce`, `X-Signature`/`Signature`,
`X-Miner-Hotkey`/`Miner-Hotkey`. FastAPI's `Header(...)` converts parameter underscores to
hyphens and matches case-insensitively, so `validator_hotkey: str = Header(...)` binds the bare
`Validator-Hotkey`. The existing `verify_request` already relies on this, so the gate can use
identical parameter names.

```python
HEADER_GATE_ENABLED = os.environ.get("HEADER_GATE_ENABLED", "true").lower() in ("true", "1", "yes")
MINER_HOTKEY_SS58 = os.environ.get("MINER_HOTKEY_SS58", "")


async def require_validator_headers(
    validator_hotkey: str = Header(...),
    signature: str = Header(...),
    miner_hotkey: str = Header(...),
    nonce: str = Header(...),
):
    """Noise filter, NOT authentication. Rejects untargeted internet traffic only.

    Any caller who reads this source can forge these headers. Real cryptographic
    verification is verify_request / VERIFY_ENABLED, deferred to v3.1.
    """
    if MINER_HOTKEY_SS58 and miner_hotkey != MINER_HOTKEY_SS58:
        raise HTTPException(status_code=403, detail="Challenge not addressed to this miner")


def get_security_dependencies() -> list:
    deps = []
    if HEADER_GATE_ENABLED and not VERIFY_ENABLED:
        deps.append(Depends(require_validator_headers))
    if BLACKLIST_ENABLED:
        from fiber.miner.dependencies import blacklist_low_stake
        deps.append(Depends(blacklist_low_stake))
    if VERIFY_ENABLED:
        deps.append(Depends(verify_request))
    return deps
```

Notes:

- Header **presence** is enforced by `Header(...)` itself — a missing header yields FastAPI's
  422 before the body is read, which is the cheap rejection clause 2.16 asks for on a 1-vCPU
  machine.
- `miner_hotkey` equality needs our ss58 **without** the Bittensor SDK, because the Fly container
  has neither the SDK nor a mounted wallet. It comes from a new `MINER_HOTKEY_SS58` in fly.toml
  `[env]`. An ss58 address is public, not a secret. If unset, the gate degrades to presence-only
  rather than failing closed — an unset value must not lock the validator out. **Drift D4.**
- The gate is skipped when `VERIFY_ENABLED` is true, since real verification subsumes it.
- Extend `log_startup_config()` in `logging.py` to log gate status alongside blacklist/verify, so
  `fly logs` shows the effective security posture at startup (**drift D9**).

`[env]` in v3 **omits** `BLACKLIST_ENABLED` and `VERIFY_ENABLED` entirely rather than setting
them `false`, so the `security.py` defaults (both `true`) are not overridden by a stale literal
(clause 2.17). Since v3 does not mount a wallet, this means: keep them out of `[env]`, and note
that the effective posture is gate-only until v3.1.

#### Step 3b — Add `--dockerfile` to `deploy-pt-miner` (drift D1 resolution)

**Files**: `scorevision/cli/private_track_miner.py`, `scorevision/__init__.py`

`build_miner_image` hardcodes the Dockerfile path and `deploy-pt-miner` exposes no way to change
it, so today Fly and GHCR cannot be pointed at the same non-default file. The chosen resolution is
to add the option to the shared CLI. **This edits shared CLI code other agents may be touching, so
the change is strictly additive: no signature is broken, no default behaviour changes.**

```python
def build_miner_image(image: DockerImage, dockerfile: str | None = None) -> None:
    repo_root = Path(__file__).resolve().parents[2]

    if dockerfile is None:
        dockerfile_path = repo_root / "scorevision/miner/private_track/Dockerfile"
    else:
        candidate = Path(dockerfile)
        # Resolve relative values against repo_root, not CWD, so the option behaves
        # identically regardless of where `sv` was invoked from.
        dockerfile_path = candidate if candidate.is_absolute() else repo_root / candidate

    if not dockerfile_path.is_file():
        raise ConfigError(f"Dockerfile not found: {dockerfile_path}")

    console.info(f"Building {image.full_name} from {dockerfile_path}")
    if not build_image(str(dockerfile_path), str(repo_root), image):
        raise DockerBuildError("Docker build failed")
    console.success("Build complete\n")
```

Threaded through `deploy_miner`, which gains a trailing keyword argument and passes it on:

```python
async def deploy_miner(
    tag: str, no_push: bool, no_commit: bool, no_start: bool,
    element_id: str | None, dockerfile: str | None = None,
) -> None:
    ...
    build_miner_image(image, dockerfile=dockerfile)
```

And registered in `scorevision/__init__.py` alongside the existing options:

```python
@click.option(
    "--dockerfile",
    default=None,
    help="Path to the Dockerfile to build, relative to the repo root "
         "(default: scorevision/miner/private_track/Dockerfile).",
)
def pt_deploy_miner_cmd(tag, no_push, no_commit, no_start, element_id, dockerfile):
    ...
    run(deploy_miner(tag, no_push, no_commit, no_start, element_id, dockerfile))
```

Design decisions, each load-bearing:

- **`default=None` resolving to the current hardcoded path** is what makes clause 3.11 hold. Every
  existing invocation builds the same file it builds today.
- **Relative paths resolve against `repo_root`, not CWD.** `build_image` already receives
  `repo_root` as the build context, so resolving the Dockerfile anywhere else would let the two
  disagree depending on the caller's working directory.
- **A missing path raises `ConfigError` rather than falling back to the default.** A silent
  fallback is the worst possible failure here: it would build v2.5 while `fly.toml` runs v3 and
  report success, recreating the exact divergence this option exists to prevent. `ConfigError` is
  already caught in `deploy_miner` and exits non-zero with a message.
- **The default path is named in the help text** so the option is discoverable without reading the
  source.
- **`--dockerfile` is documented in `MINER.md`** if that file already documents the other
  `deploy-pt-miner` options; otherwise skip, since `MINER.md` is unreliable elsewhere (clause 1.3).

Verify no other caller is affected before editing — at design time a repo-wide search found
exactly one, `deploy_miner` at `private_track_miner.py:217`, but repeat it at implementation time.

#### Step 4 — `fly.toml` migration

**File**: `cricket/turbovision/fly.toml`

```toml
app = "cricket-delivery-miner"
primary_region = "iad"

[build]
  # PARITY INVARIANT: this path and the --dockerfile argument in step 8 MUST match.
  dockerfile = "scorevision/miner/private_track/Dockerfile.v3"

[env]
  MINER_MODE = "cricket_delivery"
  MINER_HOTKEY_SS58 = "<our hotkey ss58>"
  # BLACKLIST_ENABLED / VERIFY_ENABLED deliberately omitted (clause 2.17)

[[services]]
  internal_port = 8000
  protocol = "tcp"
  auto_stop_machines = false      # carried over from [http_service] — clause 3.5
  auto_start_machines = true
  min_machines_running = 1        # carried over from [http_service] — clause 3.5
  processes = ["app"]

  [[services.ports]]              # what the validator actually uses
    port = 8000
    handlers = ["http"]

  [[services.ports]]              # keeps .fly.dev usable for manual testing — clause 3.1
    port = 443
    handlers = ["tls", "http"]

  [[services.ports]]
    port = 80
    handlers = ["http"]

  [[services.http_checks]]
    interval = "30s"
    timeout = "5s"
    grace_period = "20s"
    method = "get"
    path = "/health"

[[vm]]
  memory = "1gb"
  cpu_kind = "shared"
  cpus = 1
```

Decisions:

- **`force_https` is dropped**, not moved. Retaining it would 301 the validator's plain-HTTP
  request on 8000 (clause 2.14).
- **443 and 80 are kept alongside 8000.** Dropping `[http_service]` outright would kill
  `https://cricket-delivery-miner.fly.dev`, the only convenient manual test path (clause 3.1).
- **`handlers = ["http"]` on 8000** is correct on a dedicated IP, where Fly routes by IP alone.
  Raw TCP passthrough (`handlers = []`) also works; the HTTP handler is preferred because it
  preserves `X-Forwarded-For` for logging.
- **`auto_stop_machines = false` / `min_machines_running = 1` are carried over, not introduced.**
  They are already in the current file. A cold start costs seconds against a 30 s budget that
  already covers video download plus inference, so a sleeping machine times out and scores 0.
- **`PORT = "8000"` is dropped** — the `CMD` hardcodes `--port 8000`, so the variable was inert
  (**drift D7**). `[build.args] DOCKER_BUILDKIT = "1"` is likewise dropped as inert.
- **`[build].dockerfile` now names `Dockerfile.v3`, and this is half of a standing invariant.**
  The other half is the `--dockerfile` argument in step 8. If the two ever name different files,
  Fly runs one image and GHCR holds another, and spot-check scores the miner 0. Treat the pairing
  as a single edit: never change one without the other.
- **`fly config validate` is mandatory before deploy** (clause 2.15). `auto_stop_machines` and
  siblings have moved between `[http_service]` and `[[services]]` across fly.toml revisions, and
  the schema the installed CLI expects is **unverified**. If validation rejects the autostop keys
  inside `[[services]]`, they belong at top level for that CLI version — fix and re-validate
  rather than deploying and hoping.

#### Step 5 — Dedicated IPv4 and deploy

```bash
fly config validate
fly ips list -a cricket-delivery-miner                # record whether the existing v4 is shared
fly ips allocate-v4 -a cricket-delivery-miner         # dedicated, paid (~$2/mo)
fly ips list -a cricket-delivery-miner                # confirm NOT reported as shared
fly deploy -a cricket-delivery-miner
```

The existing IPv6 (`2a09:8280:1::18b:d679:0`) is **not** a fallback. `miners.py:27` builds
`f"http://{miner.ip}:{miner.port}/challenge"` with no bracketing, and a bare IPv6 host produces a
malformed URL. IPv4-only is a hard exclusion (clause 2.4), not a preference.

#### Step 6 — Reachability gate (must pass before step 7)

```bash
V4=$(fly ips list -a cricket-delivery-miner | awk '/v4/{print $2}')

curl -s -o /dev/null -w "%{http_code}\n" http://$V4:8000/health

curl -s -X POST http://$V4:8000/challenge \
  -H "Content-Type: application/json" \
  -H "Validator-Hotkey: 5xxx" -H "Signature: 0xdeadbeef" \
  -H "Miner-Hotkey: <our hotkey ss58>" -H "Nonce: 1" \
  -d '{"challenge_id":"reach-1","video_url":"https://example.com/x.mp4"}' \
  -o /dev/null -w "%{http_code}\n"
```

`000` means no response and Blocker C is not fixed. `200` on `/health` is the pass. A **`500`**
from the second call is **success**: it proves the request arrived, passed the header gate, was
parsed, and failed only on the fake video URL. Note the header gate now makes the four headers
mandatory, so this curl must send them or it returns 422 — which is also a valid reachability
signal, just a less informative one.

This is the gate that protects the rate-limited extrinsic in step 7. Do not proceed until
`/health` returns 200 on the raw v4.

#### Step 7 — Publish the axon (rate limited — one shot)

**On-chain serving is rate limited.** Re-publishing too soon fails outright, so a wrong IP costs a
wait before retry. This is why step 6 is a hard gate rather than a suggestion: the IP is proven
reachable *before* it is committed to chain.

Preferred, version-stable path:

```python
import bittensor as bt
from bittensor.core.extrinsics.serving import serve_extrinsic

PUBLIC_IPV4 = "<dedicated fly ipv4, verified reachable in step 6>"
PORT = 8000

wallet = bt.wallet(name="cricket_miner", hotkey="default")
sub = bt.subtensor(network="finney")

ok = serve_extrinsic(
    subtensor=sub, wallet=wallet,
    ip=PUBLIC_IPV4, port=PORT, protocol=4, netuid=44,
    wait_for_inclusion=True, wait_for_finalization=True,
)
print("serve_axon:", ok)
```

Fallback if that import path has moved in the installed version:

```python
sub.serve_axon(netuid=44, axon=bt.axon(
    wallet=wallet, ip=PUBLIC_IPV4, port=PORT,
    external_ip=PUBLIC_IPV4, external_port=PORT,
))
```

`btcli axon set` is **not** used — it does not exist in bittensor-cli 9.x and `MINER.md:21` is
unreliable here (clause 2.2). If the installed `btcli` turns out to have an `axon` group it is a
shorter path, but the SDK route works either way.

**Verification is the read-back, not the extrinsic's return value** (clause 2.3):

```python
print(sub.neuron_for_uid(207, netuid=44).axon_info)
# expect ip=<dedicated v4>, port=8000, ip_type=4
```

A `True` return with `ip=0.0.0.0` on read-back means not published. Treat success as provisional
until the read-back agrees.

Reversal: `reset_axon` republishes a placeholder (`ip 0, port 1, protocol 4`), subject to the same
rate limit.

#### Step 8 — Push image and commit the full payload

Run from `cricket/turbovision`, so bare `load_dotenv()` finds the `.env` from Gate 0e:

```bash
sv -v deploy-pt-miner --tag v3.0.0 --no-start \
   --dockerfile scorevision/miner/private_track/Dockerfile.v3
```

`--no-start` because the container runs on Fly, not locally; without it
`start_miner_container` tries to start a local container with a mounted wallet (**drift D8**).

`--dockerfile` is the step 3b option, and its value MUST equal `fly.toml`'s `[build].dockerfile`.
Rather than relying on discipline, check it mechanically before running the deploy — a three-line
guard beats a silent 0 at spot-check:

```bash
# Run from cricket/turbovision. Compares fly.toml's [build].dockerfile to the intended argument.
DF="scorevision/miner/private_track/Dockerfile.v3"
grep -E '^\s*dockerfile\s*=' fly.toml | grep -q "\"$DF\"" \
  && echo "parity OK: $DF" \
  || { echo "PARITY MISMATCH — fly.toml and --dockerfile disagree"; exit 1; }
```

This single command builds, pushes and commits together, so image coordinates cannot drift from
the pushed image (clause 2.6). It writes (`cli/private_track_miner.py:commit_on_chain`):

```json
{
  "role": "miner", "track": "private",
  "image_repo": "ghcr.io/<user>/pt-solution", "image_tag": "v3.0.0",
  "image_digest": "sha256:...",
  "element_id": "<from manifest prompt>",
  "hotkey": "5..."
}
```

via `set_reveal_commitment(..., blocks_until_reveal=1)`, which is the only kind
`get_all_revealed_commitments` returns (clause 2.8). A plain `set_commitment` never appears there.

**The `element_id` MUST be selected from the live manifest prompt, never typed** (clause 2.7).
Omit `--element-id` so `_resolve_private_element_id_from_manifest` prompts.
`_pick_latest_private_commit_for_element` compares exact strings, and local artefacts disagree on
the separator — `cricket/indexprivate.json` uses `manako_DetectCricketDelivery` while other
references use `manako/DetectCricketDelivery`. A wrong separator drops the miner with no log line.

**`commit_on_chain` swallows exceptions** (**drift D2**): it catches `Exception`, logs an error,
prints `console.warn`, and execution continues to `console.done()`. A failed commit therefore
looks like a successful run. Do not treat exit status as confirmation — require the
`Commit payload: {...}` line at INFO (hence `-v`) **and** no `On-chain commit failed` warning.

Correction is append-only: commit again, since
`_pick_latest_private_commit_for_element` selects the highest block (clause 2.10). There is no
undo.

#### Step 9 — Grant GHCR read access

1. `https://github.com/users/<GITHUB_USERNAME>/packages/container/pt-solution/settings`
2. Manage access → Invite teams or people
3. Add `DataAndMike` with **Read**

Without this the validator cannot pull the image for spot-check. The miner then passes challenges
and is still scored 0, with blacklisting risk (clause 2.9).

### Drift found between specv3.md and repo reality

Recorded because two of these change the plan.

**D1 — `sv deploy-pt-miner` could not build `Dockerfile.v3`. RESOLVED: `--dockerfile` added to the
shared CLI (step 3b).**

The defect: `cli/private_track_miner.py:build_miner_image` hardcodes the path

```python
dockerfile = repo_root / "scorevision/miner/private_track/Dockerfile"
```

and `deploy-pt-miner` exposes only `--tag`, `--no-push`, `--no-commit`, `--no-start`,
`--element-id`. So specv3.md's plan — point `fly.toml` at `Dockerfile.v3` *and* run
`sv deploy-pt-miner` — would produce two different images: Fly runs v3, GHCR holds v2.5.
Spot-check compares the pulled image against the live endpoint, so that divergence is exactly the
condition that scores 0 and risks blacklisting.

**Resolution (chosen): add a `--dockerfile` option**, threaded from `__init__.py` through
`deploy_miner` into `build_miner_image`, defaulting to `None` and resolving `None` to the existing
hardcoded path. Designed in step 3b; backward compatibility is clause 3.11 and Property 5.

Consequences of this choice:

- `Dockerfile.v3` remains a **genuinely new file**. The live v2.5 `Dockerfile` is never
  overwritten, so rollback is a one-line `fly.toml` revert rather than a file restore.
- `fly.toml` points at `Dockerfile.v3` and step 8 passes the same path. The pairing is the
  **Dockerfile parity invariant**, guarded mechanically in step 8 rather than by discipline.
- It edits shared CLI code, so the change must be additive only, and every caller of
  `build_miner_image` must be located and confirmed unaffected (one at design time).

Rejected alternatives, recorded: *promoting* `Dockerfile.v3` over `Dockerfile` needs no code change
but mutates the live image path and makes rollback a file operation; *building and pushing manually*
reintroduces exactly the coordinate drift `deploy-pt-miner` exists to prevent. Under every option,
**Fly and GHCR must build from the same Dockerfile.**

**D2 — `commit_on_chain` swallows exceptions.** Covered in step 8. Exit status is not a success
signal.

**D3 — `.env` chain trap, inverted.** There is **no `.env`**, and since code defaults are
44/finney, the chain target is currently **correct**. `env.example` ships
`SCOREVISION_NETUID=423`, `BITTENSOR_SUBTENSOR_ENDPOINT=test` and a testnet fallback, and
`MINER.md`'s env block says 44 but keeps `test`. So the risk is not a wrong `.env` — it is that
creating one from `env.example` *breaks* a working configuration, invisibly and
indistinguishably from success. A `.env` is still required, but only for the GHCR credentials.
Gates 0d and 0e.

**D4 — the header gate needs our ss58 without the SDK.** Clause 2.16 requires
`miner_hotkey == our own hotkey`, but the Fly container has neither `bittensor` nor a mounted
wallet. Resolved with `MINER_HOTKEY_SS58` in `[env]`, degrading to presence-only when unset.

**D5 — the `/challenge` 500 mechanism.** Corrected under Bug Details. Requirement unaffected.

**D6 — a second v3.1 parity risk, on the payload bytes.** See below.

**D7 — inert config.** `PORT = "8000"` (CMD hardcodes the port) and
`[build.args] DOCKER_BUILDKIT = "1"`. Both dropped in v3.

**D8 — `--no-start` is required.** `start_miner_container` starts a local container and mounts
`BITTENSOR_WALLET_PATH`; not wanted for a Fly deployment.

**D9 — startup logging.** `log_startup_config()` reports only blacklist/verify. Extend it to
report the header gate so the effective posture is visible in `fly logs`.

### v3.1 blocking prerequisite — signing-message parity

**This must be proven before `VERIFY_ENABLED=true` is ever set.** It is not a nice-to-have
investigation; if the constructions disagree, enabling verification 401s every legitimate
validator request and takes the miner from "no traffic" to "no traffic, plus rejecting the traffic
it finally has".

Two independent mismatches, neither resolvable offline because `fiber` is not installed:

**Mismatch 1 — message construction.** Validator (`utils/request_signing.py`) signs:

```python
message = f"{nonce}{hashlib.blake2b(payload_bytes, digest_size=32).hexdigest()}"
```

Miner (`security.py:verify_request`) verifies:

```python
payload_hash = signatures.get_hash(body)                       # fiber's hash, algorithm unknown
message = utils.construct_header_signing_message(
    nonce=nonce, miner_hotkey=miner_hotkey, payload_hash=payload_hash,
)
```

The validator's message omits `miner_hotkey` entirely and uses blake2b-hex directly. Unless
`construct_header_signing_message` happens to produce `f"{nonce}{payload_hash}"` and
`get_hash` happens to be blake2b-32-hex, these are different strings over different digests.

**Mismatch 2 — the signed bytes may not be the bytes on the wire (drift D6).** `miners.py` signs
`request.model_dump_json(exclude=...).encode()` but sends `json=request.model_dump(exclude=...)`,
letting httpx serialise. Pydantic's `model_dump_json` and httpx's JSON encoder need not agree on
separators, key ordering or float representation, and **httpx is unpinned in the validator's
`pyproject.toml`** (`"httpx"`, no version bound) while the miner image pins `httpx==0.25.2`.
httpx's JSON separator behaviour has changed across releases. If the byte streams differ, the
miner's `get_hash(body)` cannot reproduce the signed hash regardless of Mismatch 1.

Prerequisites for v3.1, in order: install `fiber` and print
`construct_header_signing_message` / `get_hash` for a known input; capture the exact bytes httpx
puts on the wire and compare to `model_dump_json().encode()`; only then enable
`VERIFY_ENABLED=true`, behind a rollback.

This is also why the v3 header gate is justified on **correctness** grounds, not only image size:
it is the only guard that cannot lock the validator out.

### Out of scope — stated explicitly

- **Model accuracy.** `trajectory.py` and `predictor.py` constants are untouched. The 92.8% local
  score is preserved by construction, not by testing. This bugfix is entirely about being
  reachable and registered.
- **Full signature verification.** Deferred to v3.1, gated on the parity work above.
- **Whether the fix earns anything.** Unknowable until traffic arrives.

## Testing Strategy

### Validation Approach

Two phases. First, surface counterexamples on **unfixed** code to confirm or refute the root
cause analysis — and if refuted, re-hypothesise before spending money or a rate-limited
extrinsic. Then verify the fix works and preserves existing behaviour.

The split that matters most here is **local versus live**:

| Testable locally, no spend | Requires live infra / on-chain spend |
|---|---|
| `Dockerfile.v3` builds; `import cv2, numpy` inside the container | Dedicated IPv4 allocation and `fly ips list` |
| Image size delta vs v2.5 | Raw `curl http://<v4>:8000/health` |
| `/health` returns 200 without invoking the predictor | Axon publication and `axon_info` read-back |
| Header gate unit tests (present / missing / foreign `miner_hotkey`) | GHCR push and commitment |
| Prediction equivalence v2.5 vs v3 on the same input | `get_registered_miners` including UID 207 |
| `--dockerfile` unit tests (default / explicit / missing / relative) | — |
| Dockerfile parity check against `fly.toml` | — |
| `get_settings()` prints `44 finney` | — |
| `fly config validate` | `Challenge received` in `fly logs` |

Everything in the left column should pass before anything in the right column is attempted.

### Exploratory Bug Condition Checking

**Goal**: produce counterexamples on unfixed code, and confirm which blockers are actually real.
Two of the four hypotheses are *state* claims that have never been observed.

**Test Plan**: run read-only probes against the current deployment and current chain state before
changing anything.

**Test Cases**:

1. **Axon state probe** — `sub.neuron_for_uid(207, netuid=44).axon_info`. Expect
   `ip=0.0.0.0`/`port=0`, confirming Blocker A. *A populated correct IPv4 refutes Blocker A* and
   step 7 should be skipped.
2. **Raw port probe** — `curl http://<current_v4>:8000/health`. Expect `000` (will fail on
   unfixed code — `/health` does not exist *and* the port is closed, so this cannot distinguish
   the two causes; the `/challenge` probe below separates them).
3. **Shared-IP probe** — `curl http://<current_v4>/challenge` with and without a `Host` header.
   Expect `000` without, `301` with, confirming Blockers C and clause 1.12.
4. **Hostname probe** — `curl https://cricket-delivery-miner.fly.dev/challenge`. Expect `500`,
   confirming the app is alive so the failure is purely edge routing.
5. **Health 404 probe** — `curl https://cricket-delivery-miner.fly.dev/health`. Expect `404`,
   confirming clause 1.14.
6. **Commitment probe** — read `get_all_revealed_commitments` for our hotkey and assert the
   payload fails `track != "private"`. Expect the `miner_recover` payload, confirming Blocker B.
7. **Registry probe** — run `get_registered_miners` against finney netuid 44 and assert UID 207
   is absent.

**Expected Counterexamples**:

- `axon_info` shows an unpublished record → miner filtered at `registry.py:92` with no log line
- Raw port 8000 returns `000` → the validator's `httpx.post` can never complete
- The on-chain payload has no `track` key → rejected on the first filter, permanently
- Possible causes if a probe *disagrees*: axon published manually at some point; Fly IP already
  dedicated; a later commitment we are unaware of. Any disagreement means re-hypothesise before
  spending.

### Fix Checking

**Goal**: for all inputs where the bug condition holds, the fixed deployment produces the
expected behaviour.

```
FOR ALL X WHERE isBugCondition(X) DO
  X' := applyV3Fix(X)

  ASSERT X'.axon.ip ≠ "0.0.0.0" AND X'.axon.port = 8000 AND X'.axon.ip_type = 4
  ASSERT X'.commit.track = "private" AND X'.commit.role = "miner"
  ASSERT X'.commit.image_repo ≠ "" AND X'.commit.image_tag ≠ ""
  ASSERT X'.commit.element_id = X'.manifest.element_id AND X'.commit.revealed
  ASSERT X'.commit.netuid = 44 AND X'.commit.network = "finney"
  ASSERT curl_status("http://" + X'.axon.ip + ":8000/health") = 200
  ASSERT curl_status("POST http://" + X'.axon.ip + ":8000/challenge") ≠ 000
  ASSERT "Challenge received" APPEARS IN fly_logs(X')
END FOR
```

The input domain here is a handful of real deployment states, not a generated space, so this is
exercised as a checklist against live infrastructure rather than as a property-based test.
Property 4 (the header gate) is the one part of Fix Checking that *is* generatable locally.

### Preservation Checking

**Goal**: for all inputs where the bug condition does not hold, the fixed deployment produces the
same result as the original.

```
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT F(X) = F'(X)
END FOR

// Concretely, for a well-formed cricket challenge C:
ASSERT predict_v2_5(C).prediction.item = predict_v3(C).prediction.item
ASSERT https_status("https://cricket-delivery-miner.fly.dev/challenge", C) unchanged
ASSERT import_cv2(image_v3) = import_cv2(image_v2_5) = SUCCESS
```

**Testing Approach**: property-based testing is the right tool for the prediction-equivalence and
header-gate properties, because both have large generatable input domains and the guarantee we
want is "for all inputs, unchanged" rather than "for these three examples, unchanged". Run both
containers side by side and compare outputs.

**Test Plan**: observe behaviour on **unfixed** code first — record v2.5 predictions for a set of
inputs and the current `.fly.dev` responses — then write tests asserting v3 reproduces them.

**Test Cases**:

1. **Prediction equivalence** — observe v2.5 predictions for the local cricket fixtures
   (`data-training/cricket/*.mp4` with `groundtruth-*.json`), then assert v3 returns identical
   `kph`, `bounce_x`, `stump_y`. Property 3.
2. **`cv2`/`numpy` importability** — observe both import cleanly in v2.5, assert the same in v3
   after `libgl1` is dropped. Clause 3.4. This is the single highest-risk preservation item,
   because it is the one change that could break the container outright.
3. **`.fly.dev` HTTPS path** — observe current status codes on 443, assert unchanged after
   `[http_service]` → `[[services]]`. Clause 3.1.
4. **Warm machine** — assert `fly status` still reports a running machine with no autostop after
   the migration. Clause 3.5.
5. **Other code paths** — assert the `soccer_action` and TCG (`image_url`) branches in
   `routes.py` are byte-identical to v2.5. Clause 3.8.
6. **Request contract** — assert `POST /challenge` with a well-formed body and the four headers
   returns the same response shape as v2.5. The gate adds a precondition only. Clause 3.9.
7. **UID identity** — assert `metagraph.hotkeys[207]` is unchanged before and after. Clause 3.7.
8. **CLI default path** — observe which Dockerfile `sv deploy-pt-miner` builds today, then assert
   an invocation omitting `--dockerfile` builds that same path after the option is added. Clause
   3.11, Property 5. Also confirm `build_miner_image` has no callers other than `deploy_miner`,
   since shared CLI code may have moved under another agent's edits.

### Unit Tests

- `/health` returns 200 and does **not** invoke the predictor (assert via a patched predictor that
  raises if called)
- Header gate: all four headers present with matching `miner_hotkey` → pass
- Header gate: each header missing in turn → 422 before the body is read
- Header gate: foreign `miner_hotkey` → 403
- Header gate: `MINER_HOTKEY_SS58` unset → presence-only, does not lock the validator out
- Header gate: bare header names (`Validator-Hotkey`, `Nonce`, ...) bind correctly, confirming the
  FastAPI underscore/hyphen mapping the design relies on
- `get_security_dependencies()` returns the gate when `VERIFY_ENABLED` is false and omits it when
  true
- `routes.py` cricket branch still returns `PredictionPayload(type="cricket_delivery", item=...)`
- `build_miner_image(image)` with `--dockerfile` omitted builds
  `repo_root / "scorevision/miner/private_track/Dockerfile"` — the exact pre-change path
  (Property 5, clause 3.11). Assert on the path handed to a patched `build_image`.
- `build_miner_image(image, dockerfile="scorevision/miner/private_track/Dockerfile.v3")` builds
  that file, not the default
- `build_miner_image(image, dockerfile="does/not/exist")` raises `ConfigError` and **never** calls
  `build_image` — no silent fallback to the default
- A relative `--dockerfile` resolves against `repo_root`, not CWD: same resolved path when the test
  runs with CWD set to a subdirectory and to the repo root
- An absolute `--dockerfile` is used as given
- `deploy_miner(...)` forwards `dockerfile` to `build_miner_image`, and calling it with the old
  five positional arguments still works (additive signature)
- Dockerfile parity: `fly.toml`'s `[build].dockerfile` equals the path the deploy command passes —
  cheap enough to assert in CI, and the one check that catches the spot-check-zero condition

### Property-Based Tests

- **Property 3** — generate `ChallengeRequest` instances across the local cricket fixtures and
  assert v2.5 and v3 predictions are equal
- **Property 4** — generate arbitrary header subsets and `miner_hotkey` values, assert the gate
  admits exactly the complete-and-matching set and rejects everything else before the predictor
  runs
- Generate malformed and oversized bodies, assert the gate rejects on headers before body
  parsing, so a 1-vCPU machine cannot be made to do work by an unauthenticated caller

### Integration Tests

- Full local flow: build v3, run the container, `GET /health` → 200, `POST /challenge` with valid
  headers and a real fixture URL → correct cricket payload
- Fly flow: `fly config validate` → `fly deploy` → `curl http://<v4>:8000/health` → 200, and
  `curl -X POST .../challenge` with a fake `video_url` → 500 (**success signal**: arrived, gated,
  parsed, failed only on the bogus URL)
- Chain flow: `axon_info` read-back matches the dedicated v4 / 8000 / `ip_type=4`; commit payload
  logged with `track=private`, `role=miner` and real image coordinates; `get_registered_miners`
  includes UID 207
- End-to-end: `fly logs -a cricket-delivery-miner` shows `Challenge received` from a real
  validator request

### Verification Signals

| Signal | Meaning |
|---|---|
| `curl` returns `000` on raw port 8000 | Blocker C not fixed |
| `curl` returns any status code on raw port 8000 | Connection reached the app |
| `200` from `GET /health` on the raw v4 | Reachability confirmed, predictor not involved |
| `500` from `POST /challenge` with a fake `video_url` | **Success** — arrived, gated, parsed, failed only on the bogus URL |
| `422` from `POST /challenge` with no headers | Header gate working |
| `axon_info` reads back `ip=<dedicated v4>, port=8000, ip_type=4` | Blocker A fixed |
| `ip=0.0.0.0` or `port=0` in `axon_info` | Blocker A still present; miner remains invisible |
| `Commit payload: {...}` at INFO with `track=private`, `role=miner`, real `image_repo`/`image_tag` | Blocker B fixed |
| `On-chain commit failed` warning present | Commit failed **despite a zero exit status** (drift D2) |
| `get_registered_miners` includes UID 207 | Registry filters all passed |
| `Challenge received` in `fly logs -a cricket-delivery-miner` | End-to-end fix confirmed |

## Execution Order and Success Criteria

| Step | Action | Success criterion | Reversible? |
|---|---|---|---|
| 0a | Confirm UID 207 exists on our hotkey | `metagraph.hotkeys[207]` == our ss58 | n/a — **STOP if it fails** |
| 0b | Bittensor SDK installed in a venv | `import bittensor` succeeds | yes |
| 0c | Record current `axon_info` | value written down; `0.0.0.0` confirms Blocker A | n/a |
| 0d | Confirm effective chain target (no `.env` = already 44/finney) | `get_settings()` prints `44 finney`, run from `cricket/turbovision` | n/a |
| 0e | **You** create `cricket/turbovision/.env` with GHCR + wallet + pinned mainnet values | file exists; Gate 0d still prints `44 finney` | yes (gitignored) |
| 0f | Accept ~$2/mo for a dedicated IPv4 | explicit acceptance | n/a |
| 1 | Build `Dockerfile.v3` (new file, v2.5 untouched); verify `import cv2, numpy`; compare size | builds, imports succeed, 70–90 MB smaller | yes (git) |
| 2 | Add `/health` to `server.py` | local `GET /health` → 200, predictor not called | yes (git) |
| 3 | Add header gate to `security.py`; extend startup logging | unit tests pass; startup logs gate status | yes (git) |
| 3b | Add `--dockerfile` to `deploy-pt-miner` (drift D1) | unit tests pass; omitting the option builds the pre-change path; no other caller of `build_miner_image` | yes (git) |
| 4 | Migrate `fly.toml`; point `[build].dockerfile` at `Dockerfile.v3` | `fly config validate` clean; parity check matches step 8's argument | yes (git) |
| 5 | `fly ips allocate-v4`; `fly deploy` | `fly ips list` shows a **dedicated** v4; deploy succeeds | IP releasable |
| 6 | **GATE**: `curl http://<v4>:8000/health` | `200`, not `000` | n/a |
| 7 | Publish axon via `serve_extrinsic` (**rate limited — one shot**) | `axon_info` reads back v4 / 8000 / `ip_type=4` | `reset_axon`, rate limited |
| 8 | From `cricket/turbovision`: `sv -v deploy-pt-miner --tag v3.0.0 --no-start --dockerfile scorevision/miner/private_track/Dockerfile.v3`, element ID from the manifest prompt | parity check passes; `Commit payload` logged with `track=private`, `role=miner`, real coordinates; **no** `On-chain commit failed` | append-only |
| 9 | Grant `DataAndMike` Read on the GHCR package | package settings show the grant | yes |
| 10 | Watch `fly logs -a cricket-delivery-miner` | `Challenge received` | n/a |

Step 6 exists solely to protect step 7's rate-limited extrinsic. Step 5's IP is a prerequisite for
steps 6 and 7. Step 8's push is a prerequisite for step 9 and for spot-check. Step 3b is a
prerequisite for step 8: without `--dockerfile`, GHCR would receive the v2.5 image while Fly runs
v3. Gate 0e is a prerequisite for step 8's push, since `get_ghcr_credentials` raises `ConfigError`
without `GITHUB_USERNAME`/`GITHUB_TOKEN`.

## Rollback

- **Steps 1–4 (image, `/health`, gate, CLI option, `fly.toml`)** — fully reversible from git. The
  v2.5 `Dockerfile` is never overwritten, so reverting to it is a one-line `fly.toml` edit
  (`[build].dockerfile` back to `.../Dockerfile`) plus `fly deploy` — no file restore, nothing
  deleted. `Dockerfile.v3` can stay in the tree while unused.
- **Step 3b (`--dockerfile`)** — additive, so it needs no rollback: omitting the option restores
  the pre-change behaviour exactly (clause 3.11). If it must be reverted anyway, revert both
  `private_track_miner.py` and `__init__.py` together, and coordinate first since this is shared
  CLI code.
- **Gate 0e (`.env`)** — gitignored, so deleting or editing it affects nothing tracked. Note that
  removing it does **not** break the chain target (code defaults are 44/finney) but does break the
  GHCR push.
- **Step 5 (IP)** — the dedicated IPv4 can be released, though releasing it re-breaks Blocker C.
- **Step 7 (axon)** — reversible via `reset_axon`, which republishes a placeholder
  (`ip 0, port 1, protocol 4`), **subject to the same on-chain rate limit**. Plan on not needing
  it rather than on it being available immediately.
- **Step 8 (commitment)** — **not** reversible. Append-only: a bad commitment is corrected by
  committing again, because `_pick_latest_private_commit_for_element` takes the highest block.
- **Step 9 (GHCR grant)** — revocable at any time.

## Open Questions

1. **Is an axon currently published for UID 207?** Unverifiable offline — neither `btcli` nor the
   `bittensor` SDK is installed in either local venv, and `btcli subnet metagraph` does not
   display axon records. Gate 0c answers it and determines whether Blocker A is real or already
   resolved.
2. **Does the installed `btcli` have an `axon` command group?** If yes it is a shorter path than
   the SDK script. The SDK route works either way, so this is an optimisation, not a dependency.
3. **What was in v2.3?** No `Dockerfile` variant by that name exists in the repo, so "small like
   v2.3" has no baseline to diff against. The 70–90 MB estimate is measured against v2.5, not
   against a known floor.
4. **Is the current Fly IPv4 shared or dedicated?** Not checkable offline. Step 5's first
   `fly ips list` answers it — if it is already dedicated, the add-on cost may not apply.
5. **Does `fiber`'s signing-message construction match the validator's?** Blocks v3.1, and now
   has a second dimension (the httpx-vs-pydantic payload bytes, drift D6). `fiber` is not
   installed in the workspace.
6. **Does `fly config validate` accept `auto_stop_machines` inside `[[services]]` on the installed
   CLI?** The keys have moved across fly.toml revisions. Step 4's validation answers it.
7. **Should `env.example` be updated to document the mainnet values?** It currently ships
   `SCOREVISION_NETUID=423`, `BITTENSOR_SUBTENSOR_ENDPOINT=test` and a testnet fallback, so anyone
   copying it verbatim lands a commitment on testnet netuid 423 — invisible and indistinguishable
   from success. Adding a comment naming the finney values would remove that trap for the next
   person. **Raised rather than done:** `env.example` is a tracked environment file, so the design
   does not modify it, and other agents may rely on the testnet defaults for their own work. Your
   call.

Answered since the requirements phase, recorded so they are not reopened: the drift-D1 resolution
is `--dockerfile` on the shared CLI (step 3b), and the absence of `.env` is now a verified fact
rather than an unknown — it means the chain target is already correct, and the file is needed only
for GHCR credentials (Gates 0d and 0e).
