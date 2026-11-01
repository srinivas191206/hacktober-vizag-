import os
from ultralytics import YOLO

def evaluate():
    data_yaml = os.path.abspath("dataset/data.yaml")
    
    print("=" * 60)
    print("EVALUATING MODEL V1 (Original Baseline on 106 images)")
    print("=" * 60)
    v1_model = YOLO("weights/best_v1.pt")
    metrics_v1 = v1_model.val(data=data_yaml, split="test", imgsz=640, device="cpu", verbose=False)
    
    p1 = metrics_v1.box.mp
    r1 = metrics_v1.box.mr
    map50_1 = metrics_v1.box.map50
    map5095_1 = metrics_v1.box.map
    print(f"V1 Test Results -> Precision: {p1:.4f}, Recall: {r1:.4f}, mAP50: {map50_1:.4f}, mAP50-95: {map5095_1:.4f}")

    v2_path = "weights/best.pt"
    if not os.path.exists(v2_path):
        alt_path = "runs/detect/stump_detector_v2/weights/best.pt"
        if os.path.exists(alt_path):
            v2_path = alt_path

    if os.path.exists(v2_path):
        print("\n" + "=" * 60)
        print("EVALUATING MODEL V2 (Trained on Consolidated 418 images)")
        print("=" * 60)
        v2_model = YOLO(v2_path)
        metrics_v2 = v2_model.val(data=data_yaml, split="test", imgsz=640, device="cpu", verbose=False)
        p2 = metrics_v2.box.mp
        r2 = metrics_v2.box.mr
        map50_2 = metrics_v2.box.map50
        map5095_2 = metrics_v2.box.map
        print(f"V2 Test Results -> Precision: {p2:.4f}, Recall: {r2:.4f}, mAP50: {map50_2:.4f}, mAP50-95: {map5095_2:.4f}")

        print("\n" + "=" * 60)
        print("IMPROVEMENT COMPARISON (Unseen Test Set)")
        print("=" * 60)
        print(f"Precision: {p1:.4f} -> {p2:.4f} ({'+' if p2>=p1 else ''}{(p2-p1)*100:.2f}%)")
        print(f"Recall:    {r1:.4f} -> {r2:.4f} ({'+' if r2>=r1 else ''}{(r2-r1)*100:.2f}%)")
        print(f"mAP@50:    {map50_1:.4f} -> {map50_2:.4f} ({'+' if map50_2>=map50_1 else ''}{(map50_2-map50_1)*100:.2f}%)")
        print(f"mAP@50-95: {map5095_1:.4f} -> {map50_2:.4f} ({'+' if map50_2>=map5095_1 else ''}{(map50_2-map5095_1)*100:.2f}%)")
    else:
        print(f"V2 weights not found yet at {v2_path}")

if __name__ == '__main__':
    evaluate()
