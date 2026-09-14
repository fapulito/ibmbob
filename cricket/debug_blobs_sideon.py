"""Debug blob detection for side-on camera"""
import cv2
import numpy as np
from pathlib import Path

video_path = Path("be1382745ea10902e8ebb8bc74c3533e4f8f76eb.mp4")
cap = cv2.VideoCapture(str(video_path))
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
fps = cap.get(cv2.CAP_PROP_FPS)

# Side-on search window (assuming fallback calibration)
fw, fh = 1920, 1080
px_m = 13.9
sx, sy = 670.0, 455.0  # fallback stump position

# Search zone from challenge
y_lo = max(0, int(sy - 2.6 * px_m))  # ~2.6m above crease
y_hi = min(fh, int(sy + 0.3 * px_m))  # 0.3m below
x_lo = max(0, int(sx - 1.0 * px_m))  # 1m left of stumps
x_hi = min(fw, int(sx + 21.12 * px_m))  # 21m right

print(f"Search zone: x=[{x_lo},{x_hi}] y=[{y_lo},{y_hi}]")
print(f"Zone size: {x_hi-x_lo}x{y_hi-y_lo} pixels")

# Scan delivery window (46-62% of video)
start = int(total * 0.46)
end = int(total * 0.62)
print(f"Total frames: {total}, fps: {fps}")
print(f"Scanning frames {start}-{end} ({end-start+1} frames)")

cap.set(cv2.CAP_PROP_POS_FRAMES, start)
prev_gray = None
blob_counts = []

for fn in range(start, end + 1):
    ret, frame = cap.read()
    if not ret:
        break
    
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    
    # White ball detection
    wm = cv2.inRange(hsv, (0, 0, 200), (180, 40, 255))
    
    # Motion filter
    if prev_gray is not None:
        diff = cv2.absdiff(gray, prev_gray)
        _, mot = cv2.threshold(diff, 12, 255, cv2.THRESH_BINARY)
        mot = cv2.dilate(mot, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
        mask = cv2.bitwise_and(wm, mot)
    else:
        mask = wm
    
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE,
                            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    in_zone = []
    for c in cnts:
        a = cv2.contourArea(c)
        if not (4 <= a <= 800):
            continue
        x, y, bw, bh = cv2.boundingRect(c)
        if bw == 0 or bh == 0:
            continue
        asp = bw / bh
        if asp < 0.25 or asp > 4.0:
            continue
        p = cv2.arcLength(c, True)
        if p == 0:
            continue
        if 4 * np.pi * a / (p * p) < 0.25:
            continue
        cx, cy = x + bw / 2.0, y + bh / 2.0
        if x_lo <= cx <= x_hi and y_lo <= cy <= y_hi:
            in_zone.append((cx, cy, a))
    
    blob_counts.append((fn, len(in_zone)))
    if in_zone and fn % 10 == 0:
        print(f"  Frame {fn}: {len(in_zone)} blobs in zone")
    
    prev_gray = gray

cap.release()

print(f"\nBlob count summary:")
if blob_counts:
    print(f"  Frames with 0 blobs: {sum(1 for f,c in blob_counts if c == 0)}")
    print(f"  Frames with 1-3 blobs: {sum(1 for f,c in blob_counts if 1 <= c <= 3)}")
    print(f"  Frames with 4+ blobs: {sum(1 for f,c in blob_counts if c >= 4)}")
    print(f"  Max blobs in one frame: {max(c for f,c in blob_counts)}")
else:
    print("  No frames scanned")
