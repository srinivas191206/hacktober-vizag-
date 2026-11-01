import os
from ultralytics import YOLO

def evaluate():
    data_yaml = os.path.abspath("ball_dataset/data.yaml")
    weights_path = os.path.abspath("weights/ball_best.pt")
    
    if not os.path.exists(weights_path):
        alt = os.path.abspath("runs/detect/ball_detector/weights/best.pt")
        if os.path.exists(alt):
            weights_path = alt

    print("=" * 60)
    print(f"EVALUATING BALL DETECTOR ON UNSEEN TEST SET")
    print(f"Weights: {weights_path}")
    print(f"Data:    {data_yaml}")
    print("=" * 60)

    model = YOLO(weights_path)
    metrics = model.val(data=data_yaml, split="test", imgsz=640, device="cpu", verbose=False)

    p = metrics.box.mp
    r = metrics.box.mr
    map50 = metrics.box.map50
    map5095 = metrics.box.map

    print("\n" + "=" * 60)
    print("BALL DETECTOR TEST SET PERFORMANCE:")
    print("=" * 60)
    print(f"  Precision: {p:.4f} ({p*100:.1f}%)")
    print(f"  Recall:    {r:.4f} ({r*100:.1f}%)")
    print(f"  mAP@50:    {map50:.4f} ({map50*100:.1f}%)")
    print(f"  mAP@50-95: {map5095:.4f} ({map5095*100:.1f}%)")
    print("=" * 60)

if __name__ == '__main__':
    evaluate()
