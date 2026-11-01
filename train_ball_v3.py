import os
import shutil
import torch
from ultralytics import YOLO

def main():
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"Using compute device: {device}")

    # Start from ball_best.pt checkpoint
    model_base = "/Users/thaladasrinivas/Downloads/stumps/weights/ball_best.pt"
    if not os.path.exists(model_base):
        model_base = "/Users/thaladasrinivas/Downloads/stumps/yolo11n.pt"
    print(f"Loading checkpoint: {model_base}")
    model = YOLO(model_base)

    data_yaml = "/Users/thaladasrinivas/Downloads/stumps/ball_dataset_v2/data.yaml"
    print(f"Training on: {data_yaml}")

    results = model.train(
        data=data_yaml,
        epochs=20,
        imgsz=640,
        batch=16,
        device=device,
        project="runs/detect",
        name="ball_detector_v3",
        exist_ok=True,
        workers=2,
        optimizer="AdamW",
        lr0=0.0003,
        lrf=0.01,
        patience=10,
        save=True,
        plots=True,
        verbose=True
    )
    print("Training finished!")

    src_best = "runs/detect/ball_detector_v3/weights/best.pt"
    dst_v3 = "weights/ball_best_v3.pt"
    dst_prod = "weights/ball_best.pt"
    backup_prod = "weights/ball_best_v2_backup.pt"

    if os.path.exists(src_best):
        # Backup current prod
        if os.path.exists(dst_prod):
            shutil.copy2(dst_prod, backup_prod)
            print(f"Backed up current model to {backup_prod}")

        shutil.copy2(src_best, dst_v3)
        print(f"Saved new best model to {dst_v3}")

        shutil.copy2(src_best, dst_prod)
        print(f"Updated production model at {dst_prod}")
    else:
        print(f"Warning: {src_best} not found")

if __name__ == '__main__':
    main()
