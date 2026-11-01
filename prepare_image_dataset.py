import os
import re
import cv2
import json
import shutil
import random
import unicodedata
from pathlib import Path

BASE_DIR = "/Users/thaladasrinivas/Downloads/stumps"
OUTPUT_DIR = os.path.join(BASE_DIR, "ball_image_dataset")

# Source 1: Varun (04-10)
VARUN_IMG_DIR = os.path.join(BASE_DIR, "ball!", "Ball Calib(Varun-04-10)")
VARUN_LBL_DIR = os.path.join(BASE_DIR, "ball!", "ball-", "labels", "train")

# Source 2: Naimi (07-10)
NAIMI_7_10_IMG_DIR = os.path.join(BASE_DIR, "new data", "StumpCalib(NAIMI)_7-10")
NAIMI_7_10_LBL_DIR = os.path.join(BASE_DIR, "new data", "naimi ball", "labels", "train")

# Source 3: Naimi (14-10)
NAIMI_14_10_IMG_DIR = os.path.join(BASE_DIR, "ball!", "StumpCalib(NAIMI) 14-10")
NAIMI_14_10_LBL_DIR = os.path.join(BASE_DIR, "ball!", "naimi_ball_14-10", "labels", "train")

def canon(name):
    s = unicodedata.normalize('NFKD', name)
    return re.sub(r'\s+', '', os.path.splitext(s)[0])

def build_dataset():
    random.seed(42)
    print("=" * 70)
    print("BUILDING UNIFIED EXPANDED BALL DETECTION IMAGE DATASET")
    print("=" * 70)

    # 1. Gather Varun pairs
    v_imgs = {canon(f): f for f in os.listdir(VARUN_IMG_DIR) if not f.startswith('.')}
    v_lbls = {canon(f): f for f in os.listdir(VARUN_LBL_DIR) if not f.startswith('.')}
    v_keys = sorted(set(v_imgs.keys()) & set(v_lbls.keys()))
    print(f"1. Varun annotated image pairs: {len(v_keys)}")

    # 2. Gather Naimi 7-10 pairs
    n7_imgs = {canon(f): f for f in os.listdir(NAIMI_7_10_IMG_DIR) if f.endswith(('.png', '.jpg', '.jpeg'))}
    n7_lbls = {canon(f): f for f in os.listdir(NAIMI_7_10_LBL_DIR) if f.endswith('.txt')}
    n7_keys = sorted(set(n7_imgs.keys()) & set(n7_lbls.keys()))
    print(f"2. Naimi 7-10 annotated image pairs: {len(n7_keys)}")

    # Naimi 7-10 background images
    n7_unlabeled = [n7_imgs[k] for k in sorted(n7_imgs.keys()) if k not in n7_lbls]
    random.shuffle(n7_unlabeled)
    selected_bg_7_10 = n7_unlabeled[:45]
    print(f"   Naimi 7-10 clean background images: {len(selected_bg_7_10)}")

    # 3. Gather Naimi 14-10 pairs
    n14_imgs = {canon(f): f for f in os.listdir(NAIMI_14_10_IMG_DIR) if f.endswith(('.png', '.jpg', '.jpeg'))}
    n14_lbls = {canon(f): f for f in os.listdir(NAIMI_14_10_LBL_DIR) if f.endswith('.txt')}
    n14_keys = sorted(set(n14_imgs.keys()) & set(n14_lbls.keys()))
    print(f"3. Naimi 14-10 annotated image pairs: {len(n14_keys)}")

    # Naimi 14-10 background images
    n14_unlabeled = [n14_imgs[k] for k in sorted(n14_imgs.keys()) if k not in n14_lbls]
    selected_bg_14_10 = sorted(n14_unlabeled)
    print(f"   Naimi 14-10 clean background images: {len(selected_bg_14_10)}")

    # Clean / prepare output directory
    img_out_dir = os.path.join(OUTPUT_DIR, "images")
    lbl_out_dir = os.path.join(OUTPUT_DIR, "labels")
    if os.path.exists(img_out_dir):
        shutil.rmtree(img_out_dir)
    if os.path.exists(lbl_out_dir):
        shutil.rmtree(lbl_out_dir)
    os.makedirs(img_out_dir, exist_ok=True)
    os.makedirs(lbl_out_dir, exist_ok=True)

    records = []
    global_id = 1

    # Copy Varun images & labels
    for k in v_keys:
        src_img = os.path.join(VARUN_IMG_DIR, v_imgs[k])
        src_lbl = os.path.join(VARUN_LBL_DIR, v_lbls[k])
        ext = os.path.splitext(v_imgs[k])[1].lower()
        dst_img_name = f"ball_img_{global_id:04d}{ext}"
        dst_lbl_name = f"ball_img_{global_id:04d}.txt"

        dst_img_path = os.path.join(img_out_dir, dst_img_name)
        dst_lbl_path = os.path.join(lbl_out_dir, dst_lbl_name)

        shutil.copy2(src_img, dst_img_path)
        shutil.copy2(src_lbl, dst_lbl_path)

        records.append({
            "id": global_id,
            "filename": dst_img_name,
            "image_path": dst_img_path,
            "label_path": dst_lbl_path,
            "source": "varun_image",
            "is_background": False
        })
        global_id += 1

    # Copy Naimi 7-10 images & labels
    for k in n7_keys:
        src_img = os.path.join(NAIMI_7_10_IMG_DIR, n7_imgs[k])
        src_lbl = os.path.join(NAIMI_7_10_LBL_DIR, n7_lbls[k])
        ext = os.path.splitext(n7_imgs[k])[1].lower()
        dst_img_name = f"ball_img_{global_id:04d}{ext}"
        dst_lbl_name = f"ball_img_{global_id:04d}.txt"

        dst_img_path = os.path.join(img_out_dir, dst_img_name)
        dst_lbl_path = os.path.join(lbl_out_dir, dst_lbl_name)

        shutil.copy2(src_img, dst_img_path)
        shutil.copy2(src_lbl, dst_lbl_path)

        records.append({
            "id": global_id,
            "filename": dst_img_name,
            "image_path": dst_img_path,
            "label_path": dst_lbl_path,
            "source": "naimi_image_7_10",
            "is_background": False
        })
        global_id += 1

    # Copy Naimi 7-10 background images (empty label files)
    for bg_f in selected_bg_7_10:
        src_img = os.path.join(NAIMI_7_10_IMG_DIR, bg_f)
        ext = os.path.splitext(bg_f)[1].lower()
        dst_img_name = f"ball_img_{global_id:04d}{ext}"
        dst_lbl_name = f"ball_img_{global_id:04d}.txt"

        dst_img_path = os.path.join(img_out_dir, dst_img_name)
        dst_lbl_path = os.path.join(lbl_out_dir, dst_lbl_name)

        shutil.copy2(src_img, dst_img_path)
        with open(dst_lbl_path, "w") as f:
            pass  # empty label for negative image

        records.append({
            "id": global_id,
            "filename": dst_img_name,
            "image_path": dst_img_path,
            "label_path": dst_lbl_path,
            "source": "naimi_calibration_bg_7_10",
            "is_background": True
        })
        global_id += 1

    # Copy Naimi 14-10 images & labels
    for k in n14_keys:
        src_img = os.path.join(NAIMI_14_10_IMG_DIR, n14_imgs[k])
        src_lbl = os.path.join(NAIMI_14_10_LBL_DIR, n14_lbls[k])
        ext = os.path.splitext(n14_imgs[k])[1].lower()
        dst_img_name = f"ball_img_{global_id:04d}{ext}"
        dst_lbl_name = f"ball_img_{global_id:04d}.txt"

        dst_img_path = os.path.join(img_out_dir, dst_img_name)
        dst_lbl_path = os.path.join(lbl_out_dir, dst_lbl_name)

        shutil.copy2(src_img, dst_img_path)
        shutil.copy2(src_lbl, dst_lbl_path)

        records.append({
            "id": global_id,
            "filename": dst_img_name,
            "image_path": dst_img_path,
            "label_path": dst_lbl_path,
            "source": "naimi_image_14_10",
            "is_background": False
        })
        global_id += 1

    # Copy Naimi 14-10 background images (empty label files)
    for bg_f in selected_bg_14_10:
        src_img = os.path.join(NAIMI_14_10_IMG_DIR, bg_f)
        ext = os.path.splitext(bg_f)[1].lower()
        dst_img_name = f"ball_img_{global_id:04d}{ext}"
        dst_lbl_name = f"ball_img_{global_id:04d}.txt"

        dst_img_path = os.path.join(img_out_dir, dst_img_name)
        dst_lbl_path = os.path.join(lbl_out_dir, dst_lbl_name)

        shutil.copy2(src_img, dst_img_path)
        with open(dst_lbl_path, "w") as f:
            pass  # empty label for negative image

        records.append({
            "id": global_id,
            "filename": dst_img_name,
            "image_path": dst_img_path,
            "label_path": dst_lbl_path,
            "source": "naimi_calibration_bg_14_10",
            "is_background": True
        })
        global_id += 1

    # Save manifest
    manifest_path = os.path.join(OUTPUT_DIR, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(records, f, indent=2)

    # Save data.yaml
    yaml_path = os.path.join(OUTPUT_DIR, "data.yaml")
    with open(yaml_path, "w") as f:
        f.write(f"""path: {OUTPUT_DIR}
train: images
val: images
names:
  0: ball
""")

    print(f"\nSUCCESSFULLY ASSEMBLED UNIFIED DATASET: {len(records)} images")
    print(f"  - Varun annotated balls: {len(v_keys)}")
    print(f"  - Naimi 7-10 annotated balls: {len(n7_keys)}")
    print(f"  - Naimi 7-10 clean backgrounds: {len(selected_bg_7_10)}")
    print(f"  - Naimi 14-10 annotated balls: {len(n14_keys)}")
    print(f"  - Naimi 14-10 clean backgrounds: {len(selected_bg_14_10)}")
    print(f"  - Total balls: {len(v_keys) + len(n7_keys) + len(n14_keys)}")
    print(f"  - Total backgrounds: {len(selected_bg_7_10) + len(selected_bg_14_10)}")
    print(f"Saved manifest to {manifest_path}")

if __name__ == '__main__':
    build_dataset()
