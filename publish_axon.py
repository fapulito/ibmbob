import bittensor_drand
if not hasattr(bittensor_drand, "get_encrypted_commit"):
    bittensor_drand.get_encrypted_commit = bittensor_drand.get_encrypted_commit_v2

import bittensor as bt
from bittensor.core.extrinsics.serving import serve_extrinsic

PUBLIC_IPV4 = "204.10.79.141"
wallet = bt.Wallet(name="cricket_miner", hotkey="default")
sub = bt.Subtensor(network="finney")
ok = serve_extrinsic(subtensor=sub, wallet=wallet, ip=PUBLIC_IPV4, port=8000,
                     protocol=4, netuid=44,
                     wait_for_inclusion=True, wait_for_finalization=True)
print("serve_axon:", ok)
