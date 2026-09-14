"""
Debug ball tracking to understand what's being detected.
"""
import sys
from pathlib import Path

# Add the turbovision package to path
sys.path.insert(0, str(Path(__file__).parent / "turbovision"))

import cv2
import numpy as np
from scorevision.miner.private_track.pitch_homography import PitchHomography
from scorevision.miner.private_track.ball_tracker import BallTracker

VIDEO_PATH = Path(__file__).parent / "be1382745ea10902e8ebb8bc74c3533e4f8f76eb.mp4"

def main():
    # Load video
    cap = cv2.VideoCapture(str(VIDEO_PATH))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    delivery_start = int(frame_count * 0.55)
    cap.set(cv2.CAP_PROP_POS_FRAMES, delivery_start)
    ret, ref_frame = cap.read()
    cap.release()
    
    print(f"Video: {frame_count} frames @ {fps} fps")
    print(f"Delivery start frame: {delivery_start}")
    
    # Build homography
    hom = PitchHomography(ref_frame if ret else None)
    print(f"Camera type: {getattr(hom, 'camera_type', 'unknown')}")
    print(f"Is end-on: {getattr(hom, 'is_endon', False)}")
    if hom.is_endon:
        print(f"Stump pixel position: {hom._stump_px_endon}")
        print(f"Pixels per metre (depth): {hom._px_per_m_depth:.2f}")
        print(f"Pixels per metre (lateral): {hom._px_per_m_lat:.2f}")
    
    # Track ball
    tracker = BallTracker(model_path=None)
    traj = tracker.track(VIDEO_PATH, homography=hom)
    
    print(f"\nTrajectory: {len(traj)} points")
    if len(traj) > 0:
        print("\nFrame | Pixel X | Pixel Y | Metres X | Metres Y")
        print("-" * 55)
        for fn, px, py in traj:
            x_m, y_m = hom.pixel_to_metres(px, py)
            print(f"{fn:5d} | {px:7.1f} | {py:7.1f} | {x_m:8.3f} | {y_m:8.3f}")
        
        # Show trajectory stats
        first_fn, first_px, first_py = traj[0]
        last_fn, last_px, last_py = traj[-1]
        
        x_first, y_first = hom.pixel_to_metres(first_px, first_py)
        x_last, y_last = hom.pixel_to_metres(last_px, last_py)
        
        print(f"\nTrajectory span:")
        print(f"  Frames: {first_fn} → {last_fn} ({last_fn - first_fn} frames, {(last_fn - first_fn)/fps:.3f}s)")
        print(f"  Pixel X: {first_px:.1f} → {last_px:.1f} (Δ={last_px - first_px:.1f} px)")
        print(f"  Pixel Y: {first_py:.1f} → {last_py:.1f} (Δ={last_py - first_py:.1f} px)")
        print(f"  Depth (x_m): {x_first:.3f} → {x_last:.3f} (Δ={x_first - x_last:.3f} m)")
        print(f"  Lateral (y_m): {y_first:.3f} → {y_last:.3f} (Δ={abs(y_last - y_first):.3f} m)")

if __name__ == "__main__":
    main()
