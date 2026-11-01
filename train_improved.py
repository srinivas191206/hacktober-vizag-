import os
import torch
from ultralytics import YOLO

def main():
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"Training on device: {device} (Apple M4)")

    # Load YOLO11n
    model = YOLO("yolo11n.pt")

    data_yaml = os.path.abspath("dataset/data.yaml")
    print(f"Data config: {data_yaml}")

    # Train with 333 training images across all 3 datasets
    results = model.train(
        data=data_yaml,
        epochs=60,
        imgsz=640,
        batch=16,
        device=device,
        project="runs/detect",
        name="stump_detector_v2",
        exist_ok=True,
        workers=2,
        optimizer="AdamW",
        lr0=0.001,
        patience=20,
        save=True,
        plots=True,
        verbose=True
    )
    print("Training finished successfully!")

if __name__ == '__main__':
    main()
