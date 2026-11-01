import os
import shutil
import torch
from ultralytics import YOLO

BASE_DIR = "/Users/thaladasrinivas/Downloads/stumps"
WEIGHTS_DIR = os.path.join(BASE_DIR, "weights")
DATA_YAML = os.path.join(BASE_DIR, "ball_dataset", "data.yaml")

def main():
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"Using compute device: {device} ({torch.__version__})")

    # Start from current production ball_best.pt
    model_base = os.path.join(WEIGHTS_DIR, "ball_best.pt")
    if not os.path.exists(model_base):
        model_base = os.path.join(BASE_DIR, "yolo11s.pt")
    print(f"Loading checkpoint: {model_base}")
    model = YOLO(model_base)

    print(f"Training on unified dataset: {DATA_YAML}")
    print("Hyperparameters: epochs=25, batch=16, imgsz=640, optimizer=AdamW, lr0=0.0003")

    results = model.train(
        data=DATA_YAML,
        epochs=25,
        imgsz=640,
        batch=16,
        device=device,
        project="runs/detect",
        name="ball_detector_v4_unified",
        exist_ok=True,
        workers=2,
        optimizer="AdamW",
        lr0=0.0003,
        lrf=0.01,
        patience=10,
        save=True,
        plots=True,
        verbose=True,
        hsv_h=0.015,
        hsv_s=0.5,
        hsv_v=0.4,
        degrees=5.0,
        translate=0.1,
        scale=0.3,
        fliplr=0.5,
        mosaic=0.5
    )
    print("Training complete!")

    src_best = os.path.join(BASE_DIR, "runs", "detect", "ball_detector_v4_unified", "weights", "best.pt")
    dst_v4 = os.path.join(WEIGHTS_DIR, "ball_best_v4.pt")
    dst_prod = os.path.join(WEIGHTS_DIR, "ball_best.pt")
    backup_prod = os.path.join(WEIGHTS_DIR, "ball_best_prev.pt")

    if os.path.exists(src_best) and os.path.getsize(src_best) > 1000000:
        if os.path.exists(dst_prod):
            shutil.copy2(dst_prod, backup_prod)
            print(f"Backed up previous production model to {backup_prod}")

        shutil.copy2(src_best, dst_v4)
        print(f"Archived new best model to {dst_v4}")

        shutil.copy2(src_best, dst_prod)
        print(f"Deployed new best model to production at {dst_prod}")
    else:
        print(f"Warning: Best weights not found at {src_best}")

if __name__ == '__main__':
    main()
