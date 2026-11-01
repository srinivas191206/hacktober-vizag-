import os
import shutil
from ultralytics import YOLO

def main():
    weights_path = "/Users/thaladasrinivas/Downloads/stumps/runs/detect/runs/detect/stump_detector/weights/best.pt"
    # Also save a copy in root weights/ for easy access
    os.makedirs("/Users/thaladasrinivas/Downloads/stumps/weights", exist_ok=True)
    shutil.copy2(weights_path, "/Users/thaladasrinivas/Downloads/stumps/weights/best.pt")
    shutil.copy2(
        "/Users/thaladasrinivas/Downloads/stumps/runs/detect/runs/detect/stump_detector/weights/last.pt",
        "/Users/thaladasrinivas/Downloads/stumps/weights/last.pt"
    )
    print("Copied best.pt and last.pt to /Users/thaladasrinivas/Downloads/stumps/weights/")

    data_yaml = "/Users/thaladasrinivas/Downloads/stumps/dataset/data.yaml"
    model = YOLO(weights_path)

    print("\n--- EVALUATING MODEL ON HELD-OUT TEST SET ---")
    metrics = model.val(data=data_yaml, split='test', project="runs/detect", name="test_eval", exist_ok=True)

    print("\n" + "=" * 50)
    print("TEST SET EVALUATION METRICS:")
    print("=" * 50)
    print(f"Precision:   {metrics.results_dict.get('metrics/precision(B)', 0):.4f}")
    print(f"Recall:      {metrics.results_dict.get('metrics/recall(B)', 0):.4f}")
    print(f"mAP50:       {metrics.results_dict.get('metrics/mAP50(B)', 0):.4f}")
    print(f"mAP50-95:    {metrics.results_dict.get('metrics/mAP50-95(B)', 0):.4f}")
    print("=" * 50)

    # Run predictions on all test set images and save annotated results
    test_img_dir = "/Users/thaladasrinivas/Downloads/stumps/dataset/images/test"
    test_pred_dir = "/Users/thaladasrinivas/Downloads/stumps/runs/detect/test_predictions"
    os.makedirs(test_pred_dir, exist_ok=True)

    results = model.predict(source=test_img_dir, conf=0.25, save=True, project="runs/detect", name="test_predictions", exist_ok=True)
    print(f"\nSaved test set prediction visualizations to: runs/detect/test_predictions")

if __name__ == '__main__':
    main()
