import os
import sys
import shutil
import torch
from ultralytics import YOLO

BASE_DIR = "/Users/thaladasrinivas/Downloads/stumps"
WEIGHTS_DIR = os.path.join(BASE_DIR, "weights")
DATA_YAML = os.path.join(BASE_DIR, "ball_dataset", "data.yaml")
RUNS_DIR = os.path.join(BASE_DIR, "runs", "detect")
RUN_NAME = "ball_detector_v8_expanded"

def main():
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"Using compute device: {device} (PyTorch {torch.__version__})")

    # 1. Backup current ball_best.pt to ball_best_v7_backup.pt
    model_base = os.path.join(WEIGHTS_DIR, "ball_best.pt")
    backup_path = os.path.join(WEIGHTS_DIR, "ball_best_v7_backup.pt")
    if os.path.exists(model_base):
        shutil.copy2(model_base, backup_path)
        print(f"Backed up v7 weights to {backup_path}")

    print(f"Loading base checkpoint: {model_base}")
    model = YOLO(model_base)

    print(f"Dataset configuration: {DATA_YAML}")
    print("Dataset contains: 1,641 Train + 235 Val + 83 Test = 1,959 Total Images")
    print("Training parameters: epochs=10, batch=24, imgsz=640, cache=True, optimizer=AdamW, lr0=0.00015")

    # 2. Fine-tune on updated dataset
    results = model.train(
        data=DATA_YAML,
        epochs=10,
        imgsz=640,
        batch=24,
        device=device,
        project=RUNS_DIR,
        name=RUN_NAME,
        exist_ok=True,
        workers=4,
        cache=True,
        optimizer="AdamW",
        lr0=0.00015,
        lrf=0.01,
        patience=6,
        save=True,
        plots=True,
        verbose=True,
        close_mosaic=2,
        hsv_h=0.015,
        hsv_s=0.4,
        hsv_v=0.4,
        degrees=5.0,
        translate=0.08,
        scale=0.25,
        fliplr=0.5,
        mosaic=0.3
    )

    print("\nTraining completed successfully!")

    # Search for best.pt in output locations
    candidates = [
        os.path.join(RUNS_DIR, RUN_NAME, "weights", "best.pt"),
        os.path.join(RUNS_DIR, "runs", "detect", RUN_NAME, "weights", "best.pt"),
        os.path.join(BASE_DIR, "runs", "detect", RUN_NAME, "weights", "best.pt")
    ]
    best_pt = None
    for c in candidates:
        if os.path.exists(c):
            best_pt = c
            break

    if best_pt:
        v8_path = os.path.join(WEIGHTS_DIR, "ball_best_v8.pt")
        target_path = os.path.join(WEIGHTS_DIR, "ball_best.pt")
        shutil.copy2(best_pt, v8_path)
        shutil.copy2(best_pt, target_path)
        print(f"Saved new weights to: {v8_path}")
        print(f"Deployed new weights to: {target_path}")

        # Validate final model
        print("\n--- Running Final Validation ---")
        val_model = YOLO(target_path)
        metrics = val_model.val(data=DATA_YAML, imgsz=640, device=device, split="val")
        print("\n================== V8 VALIDATION METRICS ==================")
        print(f"Precision (P):    {metrics.results_dict.get('metrics/precision(B)', 0):.4f}")
        print(f"Recall (R):       {metrics.results_dict.get('metrics/recall(B)', 0):.4f}")
        print(f"mAP@50:           {metrics.results_dict.get('metrics/mAP50(B)', 0):.4f}")
        print(f"mAP@50-95:        {metrics.results_dict.get('metrics/mAP50-95(B)', 0):.4f}")
        print("===========================================================")
    else:
        print("Error: Could not locate best.pt in runs directory!")

if __name__ == "__main__":
    main()
