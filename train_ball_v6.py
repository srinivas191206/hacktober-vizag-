import os
import sys
import shutil
import torch
from ultralytics import YOLO

BASE_DIR = "/Users/thaladasrinivas/Downloads/stumps"
WEIGHTS_DIR = os.path.join(BASE_DIR, "weights")
DATA_YAML = os.path.join(BASE_DIR, "ball_dataset", "data.yaml")
RUNS_DIR = os.path.join(BASE_DIR, "runs", "detect")
RUN_NAME = "ball_detector_v6_white_and_red"

def main():
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"Using compute device: {device} (PyTorch {torch.__version__})")

    # Start fine-tuning from our proven v5 checkpoint
    model_base = os.path.join(WEIGHTS_DIR, "ball_best.pt")
    print(f"Loading base checkpoint: {model_base}")
    model = YOLO(model_base)

    print(f"Dataset configuration: {DATA_YAML}")
    print("Dataset now contains 1,252 images (Red balls, White balls, flight deliveries & hard negatives)")
    print("Training parameters: epochs=15, batch=16, imgsz=640, optimizer=AdamW, lr0=0.00015")

    results = model.train(
        data=DATA_YAML,
        epochs=15,
        imgsz=640,
        batch=16,
        device=device,
        project=RUNS_DIR,
        name=RUN_NAME,
        exist_ok=True,
        workers=2,
        optimizer="AdamW",
        lr0=0.00015,
        lrf=0.01,
        patience=8,
        save=True,
        plots=True,
        verbose=True,
        close_mosaic=3,
        hsv_h=0.015,
        hsv_s=0.4,
        hsv_v=0.4,
        degrees=4.0,
        translate=0.08,
        scale=0.25,
        fliplr=0.5,
        mosaic=0.3
    )

    print("\nTraining completed successfully!")

    # Search for best.pt in possible output locations
    candidates = [
        os.path.join(RUNS_DIR, RUN_NAME, "weights", "best.pt"),
        os.path.join(RUNS_DIR, "runs", "detect", RUN_NAME, "weights", "best.pt"),
        os.path.join(BASE_DIR, "runs", "detect", RUN_NAME, "weights", "best.pt")
    ]
    src_best = None
    for cand in candidates:
        if os.path.exists(cand) and os.path.getsize(cand) > 1000000:
            src_best = cand
            break

    dst_v6 = os.path.join(WEIGHTS_DIR, "ball_best_v6.pt")
    dst_prod = os.path.join(WEIGHTS_DIR, "ball_best.pt")
    backup_prod = os.path.join(WEIGHTS_DIR, "ball_best_v5_backup.pt")

    if src_best:
        print(f"Found trained best weights at: {src_best} ({os.path.getsize(src_best)} bytes)")
        if os.path.exists(dst_prod):
            shutil.copy2(dst_prod, backup_prod)
            print(f"Backed up previous model to {backup_prod}")
        shutil.copy2(src_best, dst_v6)
        shutil.copy2(src_best, dst_prod)
        print(f"DEPLOYED NEW v6 UNIFIED (RED + WHITE BALL) MODEL TO: {dst_prod}")
    else:
        print("ERROR: Training finished but best.pt was not located!")

if __name__ == "__main__":
    main()
