#!/usr/bin/env python3
import bittensor as bt

sub = bt.Subtensor(network="finney")
meta = sub.metagraph(44)

print("Checking UIDs 9 and 127:")
print()

for uid in [9, 127]:
    if uid < len(meta.hotkeys):
        hotkey = meta.hotkeys[uid]
        stake = meta.S[uid]
        active = meta.active[uid]
        print(f"UID {uid}:")
        print(f"  Hotkey: {hotkey}")
        print(f"  Stake: {stake} τ")
        print(f"  Active: {active}")
        print()
