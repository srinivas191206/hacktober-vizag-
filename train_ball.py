import os
import shutil
import torch
from ultralytics import YOLO

def main():
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"Using compute device: {device}")

    model_base = "/Users/thaladasrinivas/Downloads/stumps/yolo11n.pt"
    print(f"Loading base architecture: {model_base}")
    model = YOLO(model_base)

    data_yaml = "/Users/thaladasrinivas/Downloads/stumps/ball_dataset/data.yaml"
    print(f"Training on: {data_yaml}")

    results = model.train(
        data=data_yaml,
        epochs=45,
        imgsz=640,
        batch=8,
        device=device,
        project="runs/detect",
        name="ball_detector",
        exist_ok=True,
        workers=2,
        optimizer="AdamW",
        lr0=0.001,
        patience=15,
        save=True,
        plots=True,
        verbose=True
    )
    print("Training finished!")

    # Copy best weights to weights/ball_best.pt
    src_best = "runs/detect/ball_detector/weights/best.pt"
    dst_best = "weights/ball_best.pt"
    if os.path.exists(src_best):
        shutil.copy2(src_best, dst_best)
        print(f"Copied best model to {dst_best}")
    else:
        print(f"Warning: {src_best} not found")

if __name__ == '__main__':
    main()
