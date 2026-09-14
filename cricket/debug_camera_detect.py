"""Debug camera type detection"""
import cv2
import numpy as np
from pathlib import Path

video_path = Path("be1382745ea10902e8ebb8bc74c3533e4f8f76eb.mp4")
if not video_path.exists():
    print(f"Video not found: {video_path.absolute()}")
    exit(1)

cap = cv2.VideoCapture(str(video_path))
if not cap.isOpened():
    print("Failed to open video")
    exit(1)

frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
print(f"Total frames: {frame_count}")
delivery_start = int(frame_count * 0.55)
print(f"Seeking to frame {delivery_start}")
cap.set(cv2.CAP_PROP_POS_FRAMES, delivery_start)
ret, frame = cap.read()
cap.release()

if not ret or frame is None:
    print("Failed to read frame")
    exit(1)

h, w = frame.shape[:2]
print(f"Frame: {w}x{h}")

# Check vertical lines for side-on
gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 50, 150)
lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 60, minLineLength=40, maxLineGap=10)

print(f"\nFound {len(lines) if lines is not None else 0} lines")

if lines is not None:
    vxs = []
    for ln in lines:
        r = ln[0] if ln.ndim == 2 else ln
        x1, y1, x2, y2 = int(r[0]), int(r[1]), int(r[2]), int(r[3])
        ang = abs(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
        if ang > 70:
            vxs.append((x1 + x2) / 2.0)
    
    print(f"Vertical lines: {len(vxs)}")
    if vxs:
        vxs_sorted = sorted(vxs)
        print(f"  X positions: {vxs_sorted[:10]}")
        if len(vxs_sorted) >= 2:
            diffs = np.diff(vxs_sorted)
            max_gap = max(diffs)
            print(f"  Max gap: {max_gap:.1f} ({max_gap/w*100:.1f}% of width)")
            print(f"  Threshold for side-on: {w * 0.20:.1f}")

# Check pitch centering for end-on
y_s = int(h * 0.55)
hsv_row = cv2.cvtColor(frame[y_s:y_s+1, :], cv2.COLOR_BGR2HSV)[0]
brown = cv2.inRange(hsv_row.reshape(1, w, 3),
                    np.array([8, 25, 40], dtype=np.uint8),
                    np.array([32, 210, 230], dtype=np.uint8))[0]
cols = np.where(brown > 0)[0]
print(f"\nPitch detection (y={y_s}):")
print(f"  Brown pixels: {len(cols)}")
if len(cols) > 20:
    centre = (cols.min() + cols.max()) / 2.0
    offset = abs(centre - w / 2.0) / w
    print(f"  Centre: {centre:.1f} (frame centre: {w/2.0:.1f})")
    print(f"  Offset: {offset*100:.1f}%")
    print(f"  Threshold for end-on: <15%")
    print(f"  Would detect as: {'end_on' if offset < 0.15 else 'side_on'}")
