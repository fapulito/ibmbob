"""Print all blob detections in delivery window for manual inspection."""
import sys, importlib, importlib.util, logging, types
from pathlib import Path

PRIVATE_TRACK = Path(__file__).parent / "turbovision" / "scorevision" / "miner" / "private_track"
_stub = types.ModuleType("scorevision.miner.private_track.logging")
_stub.logger = logging.getLogger("x")
sys.modules["scorevision.miner.private_track.logging"] = _stub

def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec); sys.modules[name] = mod
    spec.loader.exec_module(mod); return mod

bt = _load("scorevision.miner.private_track.ball_tracker", PRIVATE_TRACK / "ball_tracker.py")
BallTracker = bt.BallTracker

import cv2
video = Path(__file__).parent / "be1382745ea10902e8ebb8bc74c3533e4f8f76eb.mp4"
cap = cv2.VideoCapture(str(video))
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
cap.release()

sx, sy, px_d, px_l = 960.0, 450.0, 14.7, 55.0
# Show all blobs in x=[877,1043] (±1.5m) y=[440,788] (0-23m) for frames 460-560
x_lo, x_hi = int(sx - px_l*1.5), int(sx + px_l*1.5)
y_lo, y_hi = int(sy - 10), int(sy + px_d*23)
start, end = 460, 560

tracker = BallTracker()
blobs = tracker._detect_window(video, start, end, x_lo, x_hi, y_lo, y_hi)
print(f"x=[{x_lo},{x_hi}]  y=[{y_lo},{y_hi}]  frames {start}-{end}")
print(f"Frames with blobs: {len(blobs)}")
for fn in sorted(blobs.keys()):
    items = blobs[fn]
    for bx, by, area in items:
        xm = (by - sy) / px_d
        ym = (bx - sx) / px_l
        print(f"  f{fn}  px=({bx:.0f},{by:.0f})  area={area:.0f}  x_m={xm:.2f}  y_m={ym:.2f}")
