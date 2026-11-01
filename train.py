import os
import torch
from ultralytics import YOLO

def main():
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"Using device: {device}")

    # Use YOLO11 nano (lightweight, state of the art for real-time video inference)
    # If download fails, fallback to yolov8n.pt
    model_name = "yolo11n.pt"
    print(f"Loading base architecture: {model_name}")
    model = YOLO(model_name)

    data_yaml = os.path.abspath("dataset/data.yaml")
    print(f"Training on: {data_yaml}")

    results = model.train(
        data=data_yaml,
        epochs=50,
        imgsz=640,
        batch=8,
        device=device,
        project="runs/detect",
        name="stump_detector",
        exist_ok=True,
        workers=2,
        optimizer="AdamW",
        lr0=0.001,
        patience=15,
        save=True,
        plots=True,
        verbose=True
    )
    print("Training complete!")

if __name__ == '__main__':
    main()
