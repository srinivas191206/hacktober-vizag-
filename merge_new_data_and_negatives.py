import os
import re
import cv2
import json
import shutil
import random
import numpy as np

BASE_DIR = "/Users/thaladasrinivas/Downloads/stumps"
NEW_DATA_IMG_DIR = os.path.join(BASE_DIR, "new data", "StumpCalib(NAIMI)_7-10")
NEW_DATA_LBL_DIR = os.path.join(BASE_DIR, "new data", "naimi ball", "labels", "train")
DATASET_DIR = os.path.join(BASE_DIR, "ball_dataset_v2")

def canon(name):
    return re.sub(r'\s+', '', os.path.splitext(name)[0])

def main():
    random.seed(42)
    print("=" * 70)
    print("MERGING NEW DATA AND HARD NEGATIVES INTO BALL DATASET V2")
    print("=" * 70)

    # 1. Match new data images and annotations
    img_files = [f for f in os.listdir(NEW_DATA_IMG_DIR) if f.endswith(('.png', '.jpg', '.jpeg'))]
    lbl_files = [f for f in os.listdir(NEW_DATA_LBL_DIR) if f.endswith('.txt')]

    img_canon = {canon(f): f for f in img_files}
    lbl_canon = {canon(f): f for f in lbl_files}

    matched_pairs = []
    for k in sorted(lbl_canon.keys()):
        if k in img_canon:
            matched_pairs.append((img_canon[k], lbl_canon[k]))

    print(f"[1/4] Found {len(matched_pairs)} matched annotated ball pairs from new data.")
    assert len(matched_pairs) == 143, f"Expected 143 matched pairs, got {len(matched_pairs)}"

    # Identify clean background images in StumpCalib (unlabeled images)
    unlabeled_imgs = [img_canon[k] for k in sorted(img_canon.keys()) if k not in lbl_canon]
    print(f"      Found {len(unlabeled_imgs)} unlabeled images in StumpCalib.")

    # 2. Shuffle and split matched pairs: 85% train, 15% val
    random.shuffle(matched_pairs)
    n_train_ball = int(len(matched_pairs) * 0.85) # 121
    train_ball_pairs = matched_pairs[:n_train_ball]
    val_ball_pairs = matched_pairs[n_train_ball:]

    print(f"      Split: {len(train_ball_pairs)} train, {len(val_ball_pairs)} val")

    manifest = {
        "annotated_balls": [],
        "stump_calibration_backgrounds": [],
        "hard_negatives": []
    }

    # Copy annotated ball pairs
    for idx, (img_f, lbl_f) in enumerate(train_ball_pairs, start=1):
        dst_img_name = f"naimi_ball_train_{idx:03d}.png"
        dst_lbl_name = f"naimi_ball_train_{idx:03d}.txt"

        src_img = os.path.join(NEW_DATA_IMG_DIR, img_f)
        src_lbl = os.path.join(NEW_DATA_LBL_DIR, lbl_f)

        dst_img = os.path.join(DATASET_DIR, "images", "train", dst_img_name)
        dst_lbl = os.path.join(DATASET_DIR, "labels", "train", dst_lbl_name)

        shutil.copy2(src_img, dst_img)
        shutil.copy2(src_lbl, dst_lbl)

        manifest["annotated_balls"].append({
            "split": "train",
            "orig_img": img_f,
            "orig_lbl": lbl_f,
            "dest_img": dst_img_name,
            "dest_lbl": dst_lbl_name
        })

    for idx, (img_f, lbl_f) in enumerate(val_ball_pairs, start=1):
        dst_img_name = f"naimi_ball_val_{idx:03d}.png"
        dst_lbl_name = f"naimi_ball_val_{idx:03d}.txt"

        src_img = os.path.join(NEW_DATA_IMG_DIR, img_f)
        src_lbl = os.path.join(NEW_DATA_LBL_DIR, lbl_f)

        dst_img = os.path.join(DATASET_DIR, "images", "val", dst_img_name)
        dst_lbl = os.path.join(DATASET_DIR, "labels", "val", dst_lbl_name)

        shutil.copy2(src_img, dst_img)
        shutil.copy2(src_lbl, dst_lbl)

        manifest["annotated_balls"].append({
            "split": "val",
            "orig_img": img_f,
            "orig_lbl": lbl_f,
            "dest_img": dst_img_name,
            "dest_lbl": dst_lbl_name
        })

    # 3. Add clean background calibration images from StumpCalib
    # Filter 50 clean images (no detections at high conf)
    random.shuffle(unlabeled_imgs)
    selected_bg = unlabeled_imgs[:50]
    n_train_bg = int(len(selected_bg) * 0.85)
    train_bg = selected_bg[:n_train_bg]
    val_bg = selected_bg[n_train_bg:]

    print(f"[2/4] Adding {len(selected_bg)} clean background images from StumpCalib ({len(train_bg)} train, {len(val_bg)} val)...")

    for idx, img_f in enumerate(train_bg, start=1):
        dst_img_name = f"naimi_bg_train_{idx:03d}.png"
        dst_lbl_name = f"naimi_bg_train_{idx:03d}.txt"

        src_img = os.path.join(NEW_DATA_IMG_DIR, img_f)
        dst_img = os.path.join(DATASET_DIR, "images", "train", dst_img_name)
        dst_lbl = os.path.join(DATASET_DIR, "labels", "train", dst_lbl_name)

        shutil.copy2(src_img, dst_img)
        # Create empty label file for background
        open(dst_lbl, 'w').close()

        manifest["stump_calibration_backgrounds"].append({
            "split": "train",
            "orig_img": img_f,
            "dest_img": dst_img_name,
            "dest_lbl": dst_lbl_name
        })

    for idx, img_f in enumerate(val_bg, start=1):
        dst_img_name = f"naimi_bg_val_{idx:03d}.png"
        dst_lbl_name = f"naimi_bg_val_{idx:03d}.txt"

        src_img = os.path.join(NEW_DATA_IMG_DIR, img_f)
        dst_img = os.path.join(DATASET_DIR, "images", "val", dst_img_name)
        dst_lbl = os.path.join(DATASET_DIR, "labels", "val", dst_lbl_name)

        shutil.copy2(src_img, dst_img)
        open(dst_lbl, 'w').close()

        manifest["stump_calibration_backgrounds"].append({
            "split": "val",
            "orig_img": img_f,
            "dest_img": dst_img_name,
            "dest_lbl": dst_lbl_name
        })

    # 4. Extract Hard Negative Frames specifically showing shoes and pitch
    # From sample_deliv_01 (frames 0 to 22: shoe at 779, 197) and frames 72 to 84 (batsman shoes)
    print("[3/4] Extracting Hard Negative frames from sample deliveries and 1005.mp4...")
    hard_negs = []

    # sample_deliv_01.mp4: frames 0..22 and 72..84
    cap1 = cv2.VideoCapture(os.path.join(BASE_DIR, "web", "static", "samples", "sample_deliv_01.mp4"))
    frame_id = 0
    while cap1.isOpened():
        ret, frame = cap1.read()
        if not ret:
            break
        if frame_id in [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 72, 74, 76, 78, 80, 82, 84]:
            hard_negs.append((f"sample01_f{frame_id:03d}", frame))
        frame_id += 1
    cap1.release()

    # sample_deliv_02.mp4: first 15 frames and last 10 frames
    cap2 = cv2.VideoCapture(os.path.join(BASE_DIR, "web", "static", "samples", "sample_deliv_02.mp4"))
    frame_id = 0
    while cap2.isOpened():
        ret, frame = cap2.read()
        if not ret:
            break
        if frame_id in [0, 3, 6, 9, 12, 15, 65, 68, 71, 74]:
            hard_negs.append((f"sample02_f{frame_id:03d}", frame))
        frame_id += 1
    cap2.release()

    # sample_deliv_03.mp4: first 15 frames and last 10 frames
    cap3 = cv2.VideoCapture(os.path.join(BASE_DIR, "web", "static", "samples", "sample_deliv_03.mp4"))
    frame_id = 0
    while cap3.isOpened():
        ret, frame = cap3.read()
        if not ret:
            break
        if frame_id in [0, 3, 6, 9, 12, 15, 60, 63, 66, 69]:
            hard_negs.append((f"sample03_f{frame_id:03d}", frame))
        frame_id += 1
    cap3.release()

    # 1005.mp4: extract 40 non-delivery frames (between overs/deliveries)
    video_1005_path = "/Users/thaladasrinivas/Downloads/1005.mp4"
    if os.path.exists(video_1005_path):
        cap_main = cv2.VideoCapture(video_1005_path)
        sample_frame_indices = [
            500, 1200, 2500, 3800, 4200, 6100, 7500, 8900, 9500, 11200,
            12800, 14500, 16000, 17200, 18900, 20500, 21800, 23000, 24500, 26000
        ]
        for f_target in sample_frame_indices:
            cap_main.set(cv2.CAP_PROP_POS_FRAMES, f_target)
            ret, frame = cap_main.read()
            if ret:
                # Resize from 4K to 1080p to match standard resolution
                frame_1080p = cv2.resize(frame, (1920, 1080), interpolation=cv2.INTER_AREA)
                hard_negs.append((f"1005_bg_f{f_target:05d}", frame_1080p))
        cap_main.release()

    print(f"      Collected {len(hard_negs)} hard negative frames.")

    random.shuffle(hard_negs)
    n_train_hn = int(len(hard_negs) * 0.85)
    train_hn = hard_negs[:n_train_hn]
    val_hn = hard_negs[n_train_hn:]

    for name, frame in train_hn:
        img_filename = f"hardneg_train_{name}.jpg"
        lbl_filename = f"hardneg_train_{name}.txt"
        img_path = os.path.join(DATASET_DIR, "images", "train", img_filename)
        lbl_path = os.path.join(DATASET_DIR, "labels", "train", lbl_filename)
        cv2.imwrite(img_path, frame)
        open(lbl_path, 'w').close() # empty label
        manifest["hard_negatives"].append({
            "split": "train",
            "name": name,
            "dest_img": img_filename,
            "dest_lbl": lbl_filename
        })

    for name, frame in val_hn:
        img_filename = f"hardneg_val_{name}.jpg"
        lbl_filename = f"hardneg_val_{name}.txt"
        img_path = os.path.join(DATASET_DIR, "images", "val", img_filename)
        lbl_path = os.path.join(DATASET_DIR, "labels", "val", lbl_filename)
        cv2.imwrite(img_path, frame)
        open(lbl_path, 'w').close()
        manifest["hard_negatives"].append({
            "split": "val",
            "name": name,
            "dest_img": img_filename,
            "dest_lbl": lbl_filename
        })

    # Save manifest
    manifest_path = os.path.join(DATASET_DIR, "merged_new_data_manifest.json")
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)

    # 5. Summary counts
    train_imgs_count = len(os.listdir(os.path.join(DATASET_DIR, "images", "train")))
    train_lbls_count = len(os.listdir(os.path.join(DATASET_DIR, "labels", "train")))
    val_imgs_count = len(os.listdir(os.path.join(DATASET_DIR, "images", "val")))
    val_lbls_count = len(os.listdir(os.path.join(DATASET_DIR, "labels", "val")))

    print("\n[4/4] MERGE COMPLETE!")
    print("=" * 70)
    print(f"Dataset: {DATASET_DIR}")
    print(f"  - Train: {train_imgs_count} images, {train_lbls_count} labels")
    print(f"  - Val:   {val_imgs_count} images, {val_lbls_count} labels")
    print(f"  - Manifest: {manifest_path}")
    print("=" * 70)

if __name__ == '__main__':
    main()
