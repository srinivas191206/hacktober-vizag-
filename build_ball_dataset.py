import os
import re
import cv2
import json
import shutil
import random
import unicodedata
import yaml

BASE = "/Users/thaladasrinivas/Downloads/stumps"
DATASET_DIR = os.path.join(BASE, "ball_dataset")

SOURCES = [
    {
        "tag": "varun",
        "img_dir": os.path.join(BASE, "ball!", "Ball Calib(Varun-04-10)"),
        "lbl_dir": os.path.join(BASE, "ball!", "ball-", "labels", "train"),
        "is_bg": False
    },
    {
        "tag": "naimi_7_10",
        "img_dir": os.path.join(BASE, "new data", "StumpCalib(NAIMI)_7-10"),
        "lbl_dir": os.path.join(BASE, "new data", "naimi ball", "labels", "train"),
        "is_bg": False
    },
    {
        "tag": "naimi_14_10",
        "img_dir": os.path.join(BASE, "ball!", "StumpCalib(NAIMI) 14-10"),
        "lbl_dir": os.path.join(BASE, "ball!", "naimi_ball_14-10", "labels", "train"),
        "is_bg": False
    }
]

def canon(name):
    s = unicodedata.normalize('NFKD', name)
    return re.sub(r'\s+', '', os.path.splitext(s)[0])

def main():
    random.seed(42)
    print("=" * 70)
    print("BUILDING UNIFIED STANDARDIZED BALL DATASET (80% Train, 10% Val, 10% Test)")
    print("=" * 70)

    if os.path.exists(DATASET_DIR):
        shutil.rmtree(DATASET_DIR)

    for split in ['train', 'val', 'test']:
        os.makedirs(os.path.join(DATASET_DIR, "images", split), exist_ok=True)
        os.makedirs(os.path.join(DATASET_DIR, "labels", split), exist_ok=True)

    all_groups = []

    for src in SOURCES:
        tag = src["tag"]
        img_dir = src["img_dir"]
        lbl_dir = src["lbl_dir"]

        img_files = {canon(f): f for f in os.listdir(img_dir) if not f.startswith('.')}
        lbl_files = {canon(f): f for f in os.listdir(lbl_dir) if not f.startswith('.')}

        annotated_keys = sorted(set(img_files.keys()) & set(lbl_files.keys()))
        annotated_items = []
        for k in annotated_keys:
            annotated_items.append({
                "orig_img": img_files[k],
                "orig_lbl": lbl_files[k],
                "src_img_path": os.path.join(img_dir, img_files[k]),
                "src_lbl_path": os.path.join(lbl_dir, lbl_files[k]),
                "source": tag,
                "is_background": False
            })
        print(f"Source [{tag}] Annotated Balls: {len(annotated_items)}")
        all_groups.append(annotated_items)

        # Backgrounds (unannotated)
        unannotated_keys = [k for k in sorted(img_files.keys()) if k not in lbl_files]
        if tag == "naimi_7_10":
            random.shuffle(unannotated_keys)
            unannotated_keys = unannotated_keys[:45]
        bg_items = []
        for k in unannotated_keys:
            bg_items.append({
                "orig_img": img_files[k],
                "orig_lbl": None,
                "src_img_path": os.path.join(img_dir, img_files[k]),
                "src_lbl_path": None,
                "source": f"{tag}_bg",
                "is_background": True
            })
        if bg_items:
            print(f"Source [{tag}] Clean Backgrounds: {len(bg_items)}")
            all_groups.append(bg_items)

    # Stratified split: 80% train, 10% val, 10% test per group
    train_pool, val_pool, test_pool = [], [], []

    for grp in all_groups:
        random.shuffle(grp)
        n = len(grp)
        n_train = int(n * 0.80)
        n_val = int(n * 0.10)
        train_pool.extend(grp[:n_train])
        val_pool.extend(grp[n_train:n_train + n_val])
        test_pool.extend(grp[n_train + n_val:])

    print(f"\nSplit totals: Train={len(train_pool)}, Val={len(val_pool)}, Test={len(test_pool)} (Total={len(train_pool) + len(val_pool) + len(test_pool)})")

    splits_data = {
        'test': test_pool,
        'val': val_pool,
        'train': train_pool
    }

    manifest = {"train": [], "val": [], "test": []}
    global_id = 1

    # Number consecutively: test, val, train
    for split_name in ['test', 'val', 'train']:
        for item in splits_data[split_name]:
            ext = os.path.splitext(item["orig_img"])[1].lower()
            num_img = f"{global_id:04d}{ext}"
            num_lbl = f"{global_id:04d}.txt"

            dst_img = os.path.join(DATASET_DIR, "images", split_name, num_img)
            dst_lbl = os.path.join(DATASET_DIR, "labels", split_name, num_lbl)

            shutil.copy2(item["src_img_path"], dst_img)
            if item["is_background"]:
                with open(dst_lbl, 'w') as f:
                    pass
            else:
                shutil.copy2(item["src_lbl_path"], dst_lbl)

            manifest[split_name].append({
                "id": global_id,
                "original_image": item["orig_img"],
                "original_label": item["orig_lbl"],
                "numbered_image": num_img,
                "numbered_label": num_lbl,
                "source": item["source"],
                "is_background": item["is_background"]
            })
            global_id += 1

    # Save manifest
    manifest_path = os.path.join(DATASET_DIR, "rename_manifest.json")
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)

    # Save data.yaml
    yaml_content = {
        'path': DATASET_DIR,
        'train': 'images/train',
        'val': 'images/val',
        'test': 'images/test',
        'names': {0: 'ball'}
    }
    yaml_path = os.path.join(DATASET_DIR, "data.yaml")
    with open(yaml_path, 'w') as f:
        yaml.dump(yaml_content, f, sort_keys=False)

    print(f"\nCreated unified ball_dataset:")
    print(f"  - Train: {len(splits_data['train'])} pairs")
    print(f"  - Val:   {len(splits_data['val'])} pairs")
    print(f"  - Test:  {len(splits_data['test'])} pairs")
    print(f"  - Total: {global_id - 1} pairs consecutively numbered 0001 to {global_id - 1:04d}")
    print(f"  - YAML:  {yaml_path}")
    print(f"  - Manifest: {manifest_path}")

if __name__ == '__main__':
    main()
