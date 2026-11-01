
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

    # Start from current production model weights
    model_base = os.path.join(WEIGHTS_DIR, "ball_best.pt")
    print(f"Loading checkpoint: {model_base}")
    model = YOLO(model_base)

    print(f"Fine-tuning on unified dataset + hard negatives: {DATA_YAML}")
    print("Hyperparameters: epochs=15, batch=16, imgsz=640, optimizer=AdamW, lr0=0.00015")

    results = model.train(
        data=DATA_YAML,
        epochs=15,
        imgsz=640,
        batch=16,
        device=device,
        project="runs/detect",
        name="ball_detector_v5_hard_negatives",
        exist_ok=True,
        workers=2,
        optimizer="AdamW",
        lr0=0.00015,
        lrf=0.01,
        patience=8,
        save=True,
        plots=True,
        verbose=True,
        hsv_h=0.015,
        hsv_s=0.5,
        hsv_v=0.4,
        degrees=4.0,
        translate=0.08,
        scale=0.25,
        fliplr=0.5,
        mosaic=0.3
    )
    print("Training complete!")

    src_best = os.path.join(BASE_DIR, "runs", "detect", "ball_detector_v5_hard_negatives", "weights", "best.pt")
    dst_v5 = os.path.join(WEIGHTS_DIR, "ball_best_v5.pt")
    dst_prod = os.path.join(WEIGHTS_DIR, "ball_best.pt")
    backup_prod = os.path.join(WEIGHTS_DIR, "ball_best_v4_backup.pt")

    if os.path.exists(src_best) and os.path.getsize(src_best) > 1000000:
        if os.path.exists(dst_prod):
            shutil.copy2(dst_prod, backup_prod)
            print(f"Backed up v4 production model to {backup_prod}")
        shutil.copy2(src_best, dst_v5)
        shutil.copy2(src_best, dst_prod)
        print(f"DEPLOYED NEW v5 HARD-NEGATIVE TRAINED WEIGHTS TO: {dst_prod}")
    else:
        print("ERROR: Training finished but best.pt not found or corrupted!")

if __name__ == "__main__":
    main()
