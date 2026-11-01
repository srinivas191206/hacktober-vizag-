import os
import json
import random
import shutil
import numpy as np
import torch
from ultralytics import YOLO

BASE_DIR = "/Users/thaladasrinivas/Downloads/stumps"
DATASET_DIR = os.path.join(BASE_DIR, "ball_image_dataset")
MANIFEST_PATH = os.path.join(DATASET_DIR, "manifest.json")
SPLITS_DIR = os.path.join(DATASET_DIR, "splits")
CONFIGS_DIR = os.path.join(DATASET_DIR, "configs")
WEIGHTS_DIR = os.path.join(BASE_DIR, "weights")
KFOLD_WEIGHTS_DIR = os.path.join(WEIGHTS_DIR, "kfold_models")

def create_kfold_splits(k_folds=5, seed=42):
    random.seed(seed)
    os.makedirs(SPLITS_DIR, exist_ok=True)
    os.makedirs(CONFIGS_DIR, exist_ok=True)

    with open(MANIFEST_PATH, "r") as f:
        records = json.load(f)

    # Stratify by source / class type
    varun_items = [r for r in records if r["source"] == "varun_image"]
    naimi_items = [r for r in records if r["source"] == "naimi_image"]
    bg_items = [r for r in records if r["source"] == "naimi_calibration_bg"]

    random.shuffle(varun_items)
    random.shuffle(naimi_items)
    random.shuffle(bg_items)

    folds = [[] for _ in range(k_folds)]

    for group in [varun_items, naimi_items, bg_items]:
        for idx, item in enumerate(group):
            folds[idx % k_folds].append(item)

    print(f"Stratified {len(records)} images into {k_folds} balanced folds:")
    for i in range(k_folds):
        n_ball = sum(1 for item in folds[i] if not item["is_background"])
        n_bg = sum(1 for item in folds[i] if item["is_background"])
        print(f"  Fold {i+1}: {len(folds[i])} images ({n_ball} ball, {n_bg} background)")

    fold_configs = []
    for k in range(k_folds):
        val_items = folds[k]
        train_items = []
        for j in range(k_folds):
            if j != k:
                train_items.extend(folds[j])

        train_txt = os.path.join(SPLITS_DIR, f"fold_{k+1}_train.txt")
        val_txt = os.path.join(SPLITS_DIR, f"fold_{k+1}_val.txt")

        with open(train_txt, "w") as f:
            for item in train_items:
                f.write(f"{item['image_path']}\n")

        with open(val_txt, "w") as f:
            for item in val_items:
                f.write(f"{item['image_path']}\n")

        yaml_path = os.path.join(CONFIGS_DIR, f"fold_{k+1}.yaml")
        yaml_content = f"""path: {DATASET_DIR}
train: {train_txt}
val: {val_txt}
names:
  0: ball
"""
        with open(yaml_path, "w") as f:
            f.write(yaml_content)

        fold_configs.append({
            "fold": k + 1,
            "train_count": len(train_items),
            "val_count": len(val_items),
            "yaml_path": yaml_path
        })

    return fold_configs

def train_and_eval_kfolds(fold_configs, epochs=30, batch=16, imgsz=640):
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"\nTraining with device: {device}")
    base_weights = os.path.join(BASE_DIR, "yolo11s.pt")
    if not os.path.exists(base_weights):
        base_weights = os.path.join(BASE_DIR, "yolo11n.pt")
    print(f"Base model architecture: {base_weights}")

    # Backup current ball_best.pt if present
    current_best = os.path.join(WEIGHTS_DIR, "ball_best.pt")
    backup_path = os.path.join(WEIGHTS_DIR, "ball_best_pre_kfold.pt")
    if os.path.exists(current_best) and not os.path.exists(backup_path):
        shutil.copy2(current_best, backup_path)
        print(f"Backed up current ball_best.pt -> {backup_path}")

    os.makedirs(KFOLD_WEIGHTS_DIR, exist_ok=True)
    results = {}

    for cfg in fold_configs:
        k = cfg["fold"]
        yaml_path = cfg["yaml_path"]
        archived_pt = os.path.join(KFOLD_WEIGHTS_DIR, f"fold_{k}_best.pt")

        # Check if fold already trained and archived
        if os.path.exists(archived_pt) and os.path.getsize(archived_pt) > 1000000:
            print("\n" + "=" * 70)
            print(f"FOLD {k}/{len(fold_configs)} ALREADY TRAINED -> EVALUATING SAVED MODEL")
            print("=" * 70)
            val_model = YOLO(archived_pt)
            metrics = val_model.val(data=yaml_path, imgsz=imgsz, device=device, verbose=False)
            p = float(metrics.box.mp)
            r = float(metrics.box.mr)
            map50 = float(metrics.box.map50)
            map50_95 = float(metrics.box.map)

            results[f"fold_{k}"] = {
                "fold": k,
                "precision": round(p, 4),
                "recall": round(r, 4),
                "mAP50": round(map50, 4),
                "mAP50_95": round(map50_95, 4),
                "weights_path": archived_pt
            }
            print(f"[Fold {k} Summary] Precision: {p*100:.2f}% | Recall: {r*100:.2f}% | mAP@50: {map50*100:.2f}% | mAP@50-95: {map50_95*100:.2f}%")
            continue

        print("\n" + "=" * 70)
        print(f"STARTING TRAINING: FOLD {k}/{len(fold_configs)}")
        print(f"Train samples: {cfg['train_count']} | Val samples: {cfg['val_count']}")
        print("=" * 70)

        # Fresh model instance from base architecture
        model = YOLO(base_weights)

        model.train(
            data=yaml_path,
            epochs=epochs,
            batch=batch,
            imgsz=imgsz,
            device=device,
            project="runs/detect/runs/kfold",
            name=f"fold_{k}",
            exist_ok=True,
            workers=2,
            optimizer="AdamW",
            lr0=0.001,
            patience=10,
            save=True,
            plots=False,
            verbose=False
        )

        # Locate best.pt
        possible_pts = [
            getattr(getattr(model, "trainer", None), "best", None),
            os.path.join("runs", "detect", "runs", "kfold", f"fold_{k}", "weights", "best.pt"),
            os.path.join("runs", "kfold", f"fold_{k}", "weights", "best.pt")
        ]
        best_pt = None
        for pt in possible_pts:
            if pt and os.path.exists(str(pt)) and os.path.getsize(str(pt)) > 1000000:
                best_pt = str(pt)
                break

        if best_pt and os.path.exists(best_pt):
            shutil.copy2(best_pt, archived_pt)
            print(f"Archived Fold {k} weights: {best_pt} -> {archived_pt}")
            # Remove large last.pt to conserve disk space
            last_pt = os.path.join("runs", "detect", "runs", "kfold", f"fold_{k}", "weights", "last.pt")
            if os.path.exists(last_pt):
                os.remove(last_pt)
        else:
            archived_pt = base_weights

        # Evaluate on validation split
        val_model = YOLO(archived_pt)
        metrics = val_model.val(data=yaml_path, imgsz=imgsz, device=device, verbose=False)

        p = float(metrics.box.mp)
        r = float(metrics.box.mr)
        map50 = float(metrics.box.map50)
        map50_95 = float(metrics.box.map)

        results[f"fold_{k}"] = {
            "fold": k,
            "precision": round(p, 4),
            "recall": round(r, 4),
            "mAP50": round(map50, 4),
            "mAP50_95": round(map50_95, 4),
            "weights_path": archived_pt
        }

        print(f"[Fold {k} Summary] Precision: {p*100:.2f}% | Recall: {r*100:.2f}% | mAP@50: {map50*100:.2f}% | mAP@50-95: {map50_95*100:.2f}%")

    # Aggregate Statistics
    precisions = [v["precision"] for v in results.values()]
    recalls = [v["recall"] for v in results.values()]
    map50s = [v["mAP50"] for v in results.values()]
    map50_95s = [v["mAP50_95"] for v in results.values()]

    summary = {
        "k_folds": len(fold_configs),
        "epochs_per_fold": epochs,
        "mean_precision": round(float(np.mean(precisions)), 4),
        "std_precision": round(float(np.std(precisions)), 4),
        "mean_recall": round(float(np.mean(recalls)), 4),
        "std_recall": round(float(np.std(recalls)), 4),
        "mean_mAP50": round(float(np.mean(map50s)), 4),
        "std_mAP50": round(float(np.std(map50s)), 4),
        "mean_mAP50_95": round(float(np.mean(map50_95s)), 4),
        "std_mAP50_95": round(float(np.std(map50_95s)), 4),
        "folds": results
    }

    # Find the top-performing fold
    best_fold_key = max(results.keys(), key=lambda k: results[k]["mAP50"])
    best_fold = results[best_fold_key]
    summary["best_fold"] = best_fold

    # Save to weights/ball_best.pt and weights/ball_kfold_best.pt
    dest_best = os.path.join(WEIGHTS_DIR, "ball_best.pt")
    dest_kfold_best = os.path.join(WEIGHTS_DIR, "ball_kfold_best.pt")
    shutil.copy2(best_fold["weights_path"], dest_best)
    shutil.copy2(best_fold["weights_path"], dest_kfold_best)
    print(f"\n-> Successfully deployed best Fold {best_fold['fold']} model to {dest_best}")

    # Save report
    report_path = os.path.join(DATASET_DIR, "kfold_results.json")
    with open(report_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Saved K-Fold report to {report_path}")

    print("\n" + "=" * 70)
    print("5-FOLD CROSS VALIDATION OVERALL BENCHMARK RESULTS")
    print("=" * 70)
    print(f"Mean Precision:  {summary['mean_precision']*100:.2f}% ± {summary['std_precision']*100:.2f}%")
    print(f"Mean Recall:     {summary['mean_recall']*100:.2f}% ± {summary['std_recall']*100:.2f}%")
    print(f"Mean mAP@50:     {summary['mean_mAP50']*100:.2f}% ± {summary['std_mAP50']*100:.2f}%")
    print(f"Mean mAP@50-95:  {summary['mean_mAP50_95']*100:.2f}% ± {summary['std_mAP50_95']*100:.2f}%")
    print("-" * 70)
    print(f"Best Fold: Fold {best_fold['fold']} (mAP@50: {best_fold['mAP50']*100:.2f}%, Recall: {best_fold['recall']*100:.2f}%)")
    print("=" * 70)

    return summary

if __name__ == '__main__':
    configs = create_kfold_splits(k_folds=5, seed=42)
    train_and_eval_kfolds(configs, epochs=30, batch=16, imgsz=640)
