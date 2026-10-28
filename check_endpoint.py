#!/usr/bin/env python3
"""Quick diagnostic for cricket miner endpoint status."""
import requests
import bittensor as bt

HOTKEY = "5CyQ9buHwqgCS7158ytsX8BQvT7WSEH8gDMWq7tqUV3Fshsa"
ENDPOINT_IP = "204.10.79.141"
ENDPOINT_PORT = 8000
NETUID = 44

print("=" * 80)
print("ENDPOINT HEALTH CHECK")
print("=" * 80)

# Test endpoint
try:
    url = f"http://{ENDPOINT_IP}:{ENDPOINT_PORT}/challenge"
    payload = {
        "challenge_id": "diagnostic_test",
        "video_url": "https://scoredata.me/cricket/f81d092b6117be1126e0d6be97220b3f9a2870eb.mp4"
    }
    print(f"Testing endpoint: {url}")
    resp = requests.post(url, json=payload, timeout=10)
    print(f"  Status: {resp.status_code}")
    print(f"  Response: {resp.text[:500]}")
except Exception as e:
    print(f"  FAILED: {e}")

print()
print("=" * 80)
print("SUBNET REGISTRATION CHECK")
print("=" * 80)

# Check metagraph
try:
    sub = bt.Subtensor(network="finney")
    meta = sub.metagraph(NETUID)
    
    if HOTKEY in meta.hotkeys:
        idx = meta.hotkeys.index(HOTKEY)
        print(f"✓ Hotkey FOUND in metagraph")
        print(f"  UID: {idx}")
        print(f"  Axon IP: {meta.axons[idx].ip}")
        print(f"  Axon Port: {meta.axons[idx].port}")
        print(f"  Protocol: {meta.axons[idx].protocol}")
        print(f"  Active: {meta.active[idx]}")
        print(f"  Stake τ: {meta.S[idx]}")
        print(f"  Trust: {meta.T[idx]}")
        print(f"  Consensus: {meta.C[idx]}")
        print(f"  Incentive: {meta.I[idx]}")
        print(f"  Dividends: {meta.D[idx]}")
        print(f"  Emission ρ: {meta.E[idx]}")
    else:
        print(f"✗ Hotkey NOT FOUND in metagraph")
        print(f"  Total neurons: {len(meta.hotkeys)}")
        print(f"  Check if registration completed on-chain")
        
except Exception as e:
    print(f"✗ Metagraph check failed: {e}")

print()
print("=" * 80)
