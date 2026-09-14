# Bugfix Requirements Document

## Introduction

The cricket delivery miner (subnet 44, UID 207, Fly app `cricket-delivery-miner`) has been
deployed since v2.5 and answers requests on `https://cricket-delivery-miner.fly.dev`, but has
never received a single validator challenge. The miner therefore earns zero incentive despite
a model that scores 92.8% against local ground truth.

The root cause is not the model and not a discovery delay. The miner is simultaneously
**invisible** to the validator's private-track registry and **unreachable** at the network
level. Three independent defects each individually prevent traffic; fixing any one or two of
them changes nothing observable. A fourth defect (authentication disabled) is not blocking
today but becomes an exposure the moment reachability is fixed.

Impact: total loss of subnet 44 private-track earnings for UID 207, plus deregistration risk
once immunity (7500 blocks, ~25h) lapses with zero incentive.

Scope boundary: this bugfix changes **reachability, registration, and packaging only**. Model
accuracy is explicitly out of scope — `trajectory.py` prediction constants are not touched.

## Bug Analysis

### Current Behavior (Defect)

Observable state of the deployed v2.5 miner. Each clause below was confirmed against the
validator source in this repository.

**Blocker A — invisible to the registry (no axon)**

1.1 WHEN the validator enumerates metagraph hotkeys AND the axon record for UID 207 has
`ip = 0.0.0.0` or `port = 0` THEN the system drops UID 207 at `registry.py:92`
(`if not axon.ip or not axon.port: continue`) and emits no log line, so the miner is silently
absent from the registered-miner list.

1.2 WHEN no code path publishes an axon THEN the system leaves the axon record unpublished
indefinitely — `serve_axon` and `serve_extrinsic` appear nowhere in `scorevision`, so the
miner server does not publish its own endpoint at startup.

1.3 WHEN a miner follows `MINER.md:21` (`btcli axon set --netuid 44 --ip <public_ip> --port 8000`)
THEN the system provides no working publication path, because that subcommand does not exist in
bittensor-cli 9.x, and `btcli subnet metagraph` does not display axon records so the failure is
not observable from CLI output.

1.4 WHEN an axon is published with `ip_type = 6` THEN the validator constructs
`f"http://{miner.ip}:{miner.port}/challenge"` (`miners.py:27`) without bracket notation,
producing a malformed URL that cannot be requested.

**Blocker B — invisible to the registry (wrong commitment)**

1.5 WHEN the on-chain commitment was written by `sv commit_recover` THEN the system stores
`{"role": "miner_recover", "element_id": ..., "hotkey": ...}`
(`bittensor_helpers.py:243`, `RECOVERY_COMMIT_ROLE = "miner_recover"` at
`commit_recovery.py:19`), which has no `track` key and no image coordinates.

1.6 WHEN `_pick_latest_private_commit_for_element` evaluates that payload THEN the system
rejects it three separate times: `obj.get("track") != "private"` (key absent, so `None`),
`obj.get("role") not in (None, "miner")` (`"miner_recover"`), and
`if not image_repo or not image_tag` at `registry.py:121`.

1.7 WHEN a commitment carries only an `element_id` and no `image_repo`/`image_tag` THEN the
system discards it regardless of how long it has been on chain, because the image coordinates
are a hard requirement for spot-check.

1.8 WHEN a commitment is written with plain `set_commitment` rather than
`set_reveal_commitment(..., blocks_until_reveal=1)` THEN the system never surfaces it, because
the registry reads exclusively via `get_all_revealed_commitments`.

1.9 WHEN the committed `element_id` string differs from the manifest string by even a separator
(`manako/DetectCricketDelivery` vs `manako_DetectCricketDelivery`) THEN the system drops the
miner on the exact-string comparison with no log line.

**Blocker C — unreachable endpoint**

1.10 WHEN the validator issues `POST http://<axon_ip>:8000/challenge` — plain HTTP, raw IP, no
`Host` header, no TLS — THEN the system returns no response at all (`curl` exit status `000`),
because `fly.toml` uses `[http_service]` with `internal_port = 8000`, which publishes only edge
ports 80 and 443 and never exposes port 8000 externally.

1.11 WHEN a request arrives at the app's **shared** Fly IPv4 without TLS SNI or an HTTP `Host`
header THEN the system drops the connection at Fly's edge, because shared IPs route solely by
Host/SNI.

1.12 WHEN a plain-HTTP request does reach the edge THEN the system responds `301` rather than
serving the challenge, because `force_https = true`.

**Item D — no authentication, and no usable health probe**

1.13 WHEN the miner starts with `BLACKLIST_ENABLED = "false"` and `VERIFY_ENABLED = "false"` in
`[env]` THEN the system accepts challenge requests from any caller with no stake gating and no
signature verification, overriding the `security.py` defaults which are both `true` when unset.

1.14 WHEN any client requests `GET /health` THEN the system returns `404`, because `server.py`
registers only `/challenge`.

1.15 WHEN a health probe falls back to `GET /challenge` THEN the system returns `500` and logs
an error, because the GET branch builds a `ChallengeRequest` with `video_url = None` which
`predict_cricket_delivery` cannot process — so every probe looks like a genuine failure in
`fly logs`.

1.16 WHEN the image is built from the current `Dockerfile` THEN the system installs `libgl1`
(pulling mesa, libdrm and X libraries that `opencv-python-headless` never loads) and
`cryptography==41.0.7` (imported by nothing in the miner), inflating the image the validator
must pull for spot-check by an estimated 70–90 MB.

### Expected Behavior (Correct)

**Blocker A**

2.1 WHEN the validator enumerates metagraph hotkeys THEN the system SHALL present a published
axon for UID 207 with a non-zero IPv4 address and `port = 8000`, so that the `registry.py:92`
guard passes.

2.2 WHEN the axon needs publishing THEN the system SHALL publish it via the version-stable
Bittensor SDK (`serve_extrinsic`, or `subtensor.serve_axon` as fallback) rather than a `btcli`
subcommand, and SHALL treat a successful extrinsic as provisional until read back.

2.3 WHEN publication completes THEN the system SHALL be verifiable by
`subtensor.neuron_for_uid(207, netuid=44).axon_info` reporting the dedicated IPv4,
`port = 8000`, and `ip_type = 4`.

2.4 WHEN choosing an address family THEN the system SHALL publish IPv4 only. IPv6 is a hard
exclusion, not a preference, because `miners.py:27` cannot express a bracketed IPv6 host.

**Blocker B**

2.5 WHEN committing on-chain THEN the system SHALL write the full private-track payload —
`role: "miner"`, `track: "private"`, non-empty `image_repo`, non-empty `image_tag`,
`image_digest`, `element_id`, `hotkey` — matching `cli/private_track_miner.py:commit_on_chain`.

2.6 WHEN committing THEN the system SHALL use `sv -v deploy-pt-miner --tag v3.0.0`, which
builds, pushes and commits together, so image coordinates cannot drift from the pushed image.

2.7 WHEN selecting the `element_id` THEN the system SHALL take it from the live manifest prompt
rather than typing it, because the registry comparison is exact and local artefacts disagree on
the separator.

2.8 WHEN the commitment is written THEN the system SHALL use
`set_reveal_commitment(..., blocks_until_reveal=1)` so it appears in
`get_all_revealed_commitments`.

2.9 WHEN the image is pushed to GHCR THEN the system SHALL grant `DataAndMike` **Read** access
on the package, so spot-check can pull it. Without this the miner scores 0 and risks
blacklisting even after passing challenges.

2.10 WHEN a bad commitment needs correcting THEN the system SHALL commit again rather than
attempt an undo, because `_pick_latest_private_commit_for_element` selects the highest block.

**Blocker C**

2.11 WHEN the validator issues `POST http://<dedicated_ipv4>:8000/challenge` THEN the system
SHALL accept the connection and return an HTTP status code — never `000`.

2.12 WHEN configuring Fly THEN the system SHALL replace `[http_service]` with a `[[services]]`
block that publishes raw port 8000 alongside 443 and 80, so the validator's plain-HTTP path
works without breaking the `.fly.dev` hostname.

2.13 WHEN allocating an address THEN the system SHALL allocate a **dedicated** IPv4
(`fly ips allocate-v4`) and SHALL confirm via `fly ips list` that it is not reported as shared,
because a shared IP cannot route a request that carries neither `Host` nor SNI.

2.14 WHEN a plain-HTTP request arrives on port 8000 THEN the system SHALL serve it rather than
redirect, i.e. `force_https` SHALL NOT apply to that port.

2.15 WHEN `fly.toml` is edited THEN the system SHALL be validated with `fly config validate`
before deploy, because `auto_stop_machines` and siblings have moved between `[http_service]`
and `[[services]]` across fly.toml revisions.

**Item D**

2.16 WHEN a request arrives without all of `validator_hotkey`, `signature`, `miner_hotkey` and
`nonce` headers THEN the system SHALL reject it, and WHEN `miner_hotkey` does not equal our own
hotkey THEN the system SHALL reject it — a zero-dependency gate that filters untargeted
internet traffic at negligible CPU cost on a 1-vCPU machine.

2.17 WHEN v3 defines `[env]` THEN the system SHALL omit `BLACKLIST_ENABLED` and
`VERIFY_ENABLED` entirely rather than setting them `false`. Full `fiber` sr25519 verification
remains deferred to v3.1 because `fiber` reverses the image-size work; the header gate SHALL be
documented as a noise filter, not authentication.

2.18 WHEN `GET /health` is requested THEN the system SHALL return `200` without invoking the
predictor, and SHALL be exempt from the header gate so Fly's health checks pass.

2.19 WHEN the v3 image is built THEN the system SHALL omit `libgl1` and `cryptography`, retain
`libglib2.0-0`, and set `PYTHONDONTWRITEBYTECODE=1` and `PYTHONUNBUFFERED=1` so `fly logs`
shows the first validator request without buffering delay.

2.20 WHEN the v3 image is built THEN the system SHALL be proven to satisfy
`python -c "import cv2, numpy"` inside the container before deploy, and any missing shared
object SHALL be resolved by adding only the specific library named in the error — not by
reinstating `libgl1`.

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a human requests `https://cricket-delivery-miner.fly.dev/challenge` THEN the system
SHALL CONTINUE TO serve it over TLS on port 443, so manual testing against the hostname keeps
working after `[http_service]` is replaced.

3.2 WHEN `MINER_MODE = "cricket_delivery"` THEN the system SHALL CONTINUE TO route challenges
to `predict_cricket_delivery` and return `PredictionPayload(type="cricket_delivery", item=...)`
exactly as today.

3.3 WHEN the predictor runs THEN the system SHALL CONTINUE TO produce the v2.0 prediction
values — `trajectory.py` constants are unchanged, so the 92.8% local score is preserved.

3.4 WHEN the container starts THEN the system SHALL CONTINUE TO import `cv2` and `numpy`
successfully, since `libglib2.0-0` is retained.

3.5 WHEN no challenge has arrived recently THEN the system SHALL CONTINUE TO keep at least one
machine warm (`auto_stop_machines = false`, `min_machines_running = 1`), because a cold start
consumes seconds of a 30-second budget that already covers video download plus inference.

3.6 WHEN a valid signed challenge arrives THEN the system SHALL CONTINUE TO complete within the
validator's 30-second timeout (`miners.py`, `timeout: float = 30.0`).

3.7 WHEN the fix is applied THEN the system SHALL CONTINUE TO operate as UID 207 on the same
hotkey — no re-registration, no new UID, no change to wallet identity.

3.8 WHEN routes dispatch THEN the system SHALL CONTINUE TO handle the `soccer_action` and TCG
(`image_url`) paths in `routes.py` unmodified, even though this deployment serves cricket only.

3.9 WHEN `POST /challenge` is called with a well-formed body THEN the system SHALL CONTINUE TO
accept it on the same path and shape — the header gate adds a precondition, it does not change
the request contract.

3.10 WHEN a rollback is needed THEN the system SHALL CONTINUE TO be restorable by deploying the
previous `fly.toml` and v2.5 `Dockerfile` from git, and the axon SHALL remain reversible via
`reset_axon` (subject to on-chain serve rate limiting).

### Bug Condition and Properties

**Bug Condition** — identifies the states in which the miner receives no validator traffic:

```pascal
FUNCTION isBugCondition(X)
  INPUT: X of type MinerDeploymentState
  OUTPUT: boolean

  // Any one of these three is sufficient to receive zero challenges.
  axonInvisible  ← (X.axon.ip = "0.0.0.0") OR (X.axon.port = 0) OR (X.axon.ip_type ≠ 4)

  commitInvisible ← (X.commit.track ≠ "private")
                    OR (X.commit.role ∉ {NULL, "miner"})
                    OR (X.commit.image_repo = "" OR X.commit.image_tag = "")
                    OR (X.commit.element_id ≠ X.manifest.element_id)
                    OR (NOT X.commit.revealed)

  unreachable     ← curl_status("http://" + X.axon.ip + ":" + X.axon.port + "/health") = 000

  RETURN axonInvisible OR commitInvisible OR unreachable
END FUNCTION
```

**Fix Checking** — for every state that triggers the bug, the fixed deployment must be visible
and reachable:

```pascal
// Property: Fix Checking - validator can discover and reach the miner
FOR ALL X WHERE isBugCondition(X) DO
  X' ← applyV3Fix(X)

  ASSERT X'.axon.ip ≠ "0.0.0.0" AND X'.axon.port = 8000 AND X'.axon.ip_type = 4
  ASSERT X'.commit.track = "private" AND X'.commit.role = "miner"
  ASSERT X'.commit.image_repo ≠ "" AND X'.commit.image_tag ≠ ""
  ASSERT X'.commit.element_id = X'.manifest.element_id AND X'.commit.revealed
  ASSERT curl_status("http://" + X'.axon.ip + ":8000/health") = 200
  ASSERT curl_status("POST http://" + X'.axon.ip + ":8000/challenge") ≠ 000
  ASSERT "Challenge received" APPEARS IN fly_logs(X')
END FOR
```

**Preservation Checking** — for every input that does not trigger the bug, behaviour is
identical before and after the fix:

```pascal
// Property: Preservation Checking
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT F(X) = F'(X)
END FOR

// Concretely, for a well-formed signed cricket challenge C:
ASSERT predict_v2_5(C).prediction.item = predict_v3(C).prediction.item
ASSERT https_status("https://cricket-delivery-miner.fly.dev/challenge", C) unchanged
ASSERT import_cv2(image_v3) = import_cv2(image_v2_5) = SUCCESS
```

**Verification signals** — how each property is checked in practice:

| Signal | Meaning |
|--------|---------|
| `curl` returns `000` on raw port 8000 | Blocker C not fixed |
| `curl` returns any status code on raw port 8000 | Connection reached the app |
| `500` from `POST /challenge` with a fake `video_url` | **Success** — request arrived, was parsed, and failed only on the bogus URL |
| `axon_info` reads back `ip=<dedicated v4>, port=8000, ip_type=4` | Blocker A fixed |
| Commit payload log shows `track=private`, `role=miner`, real `image_repo`/`image_tag` | Blocker B fixed |
| `Challenge received` in `fly logs -a cricket-delivery-miner` | End-to-end fix confirmed |
| `ip=0.0.0.0` or `port=0` in `axon_info` | Blocker A still present; miner remains invisible |
