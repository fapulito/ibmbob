# Memory Snapshot: ibmbob Projects

## Tools & environment
- The user operates on Windows with PowerShell and uses WSL (Windows Subsystem for Linux) for running Linux commands and Python environments.
- The user works with Bittensor blockchain infrastructure, specifically subnet 44 (Score subnet for video analysis).
- The user maintains Python virtual environments (`.venv-sv`, `.venv-bt`) for different project components.
- The user has a Bittensor wallet named `cricket_miner` with multiple hotkeys: `default`, `miner2`, and `miner3`.
- The user's workspace root is `c:\Users\fapul\Source\repos\ibmbob`.
- The user uses GitHub for version control with username `fapulito`.
- The user has E2B API access for Linux VM provisioning (API key present in `.env` files).

## Ongoing projects

### Cricket Miner (Bittensor Subnet 44)
- The user is running a miner on Bittensor subnet 44 that performs cricket video analysis and event detection.
- The primary project is located at `cricket/turbovision/` within the ibmbob directory.
- The miner endpoint is deployed at IP `204.10.79.141` on port `8000`.
- The user's default hotkey is `5CyQ9buHwqgCS7158ytsX8BQvT7WSEH8gDMWq7tqUV3Fshsa`.
- As of the last check, all three of the user's hotkeys (default, miner2, miner3) are deregistered from subnet 44.
- The miner uses Fiber protocol for authentication requiring validator-hotkey, signature, miner-hotkey, and nonce headers.
- The registration burn cost for subnet 44 is approximately 0.74 τ (743,378 Rao).
- The user had working miners previously but they were pushed out when subnet 44 reached capacity (256/256 neurons) due to having zero stake and low immunity.
- The miner repository has a GitHub Container Registry (GHCR) setup for Docker image distribution with repo name `cricket-miner`.

### Cricket Video Analysis Implementation
- The project involves detecting cricket events from video including ball tracking, player detection, and action recognition.
- The user has ground truth data files (`groundtruth-8b97.json`) for validation and testing.
- There are debug scripts for blob detection, camera detection, and tracking (`debug_blobs.py`, `debug_camera_detect.py`, `debug_tracking.py`).
- The user has frame extraction at specific percentages of video progress stored in `cricket/frames/`.
- The user maintains metagraph logs tracking subnet 44 state in `logs/metagraph44_*.txt` files.

### Football Action Recognition (Secondary)
- The user has documentation and ground truth data for football event detection in `data-training/detect-football-ev/`.
- This appears to be an extension or related project to the cricket analysis system (inferred).

### Deployment Infrastructure
- The user has deployment documentation (`DEPLOYMENT.md`) and Docker configuration (`.dockerignore`, Dockerfile implied).
- There are registration automation scripts (`smart_register.sh`, `auto_register.sh`, `aggressive_register.sh`) for managing Bittensor subnet registration.
- The user uses environment variables for configuration including GitHub tokens, Bittensor endpoints, and network settings.

## Working style & values
- The user expects direct, accurate answers about blockchain and subnet state without filler or over-explanation.
- The user values understanding root causes when systems fail rather than just symptomatic fixes.
- The user questions inconsistencies and expects explanations that make technical sense.
- The user works with production cryptocurrency infrastructure where incorrect information has financial consequences.

## Communication preferences
- The user prefers technical accuracy and will challenge statements that don't align with observed behavior.
- The user expects concise responses but thorough investigation when troubleshooting.
- The user responds to casual tone and uses informal language ("b4" for "before").

## Profession & work
- The user works with machine learning models for computer vision, specifically video event detection.
- The user operates cryptocurrency mining infrastructure on the Bittensor network.
- The user works with Docker containerization, GitHub Actions for CI/CD, and cloud deployment.
- The user has experience with blockchain concepts including stake, immunity, registration burns, and metagraph queries.

## Anything else durable
- The subnet 44 owner hotkey is `5FsREvyUXSZWYRqVyQLDdpYmZZPnkhZyW6HjooozKP1nQkwu` with coldkey `5CaCekuxb9pKQyLoxh3jbkEXig8fxjkeS4AQ6UmZa12xfQ9H`.
- Subnet 44 has an immunity period of 7,500 blocks (approximately 25 hours) before miners can be deregistered.
- The user has multiple spec documents in `.kiro/specs/` for cricket-miner-v3 and cricket-prediction-accuracy improvements.
- The user maintains analysis documents including `cmfo-cart-analysis.md` and `bob-talk.md` for project notes.
- The user has a `betcli-stake.txt` file tracking staking operations (contents unknown).