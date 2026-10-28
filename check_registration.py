#!/usr/bin/env python3
import bittensor as bt

wallet = bt.Wallet(name="cricket_miner", hotkey="default")
print(f"Wallet hotkey: {wallet.hotkey.ss58_address}")

sub = bt.Subtensor(network="finney")
is_registered = sub.is_hotkey_registered(netuid=44, hotkey_ss58=wallet.hotkey.ss58_address)
print(f"Registered on subnet 44: {is_registered}")

if is_registered:
    uid = sub.get_uid_for_hotkey_on_subnet(hotkey_ss58=wallet.hotkey.ss58_address, netuid=44)
    print(f"UID: {uid}")
else:
    print("You need to register this hotkey to subnet 44")
    print("Cost check in progress...")
    burn = sub.get_burn_cost(netuid=44)
    print(f"Current burn cost (registration): {burn} τ")
