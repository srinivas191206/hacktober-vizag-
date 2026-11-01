import os
import sys
import shutil
import random
import xml.etree.ElementTree as ET
import cv2
import numpy as np

BASE_DIR = "/Users/thaladasrinivas/Downloads/stumps"
WHITE_BALL_DIR = os.path.join(BASE_DIR, "white ball")
XML_PATH = os.path.join(WHITE_BALL_DIR, "annotations 9.xml")
IMG_DIR = os.path.join(WHITE_BALL_DIR, "Varun-ballclib-20-10")
DATASET_DIR = os.path.join(BASE_DIR, "ball_dataset")

def main():
    if not os.path.exists(XML_PATH):
        print(f"Error: {XML_PATH} does not exist!")
        sys.exit(1)

    tree = ET.parse(XML_PATH)
    root = tree.getroot()
    image_elements = root.findall("image")
    print(f"Found {len(image_elements)} <image> entries in {XML_PATH}")

    # Set seed for reproducible split
    random.seed(42)

    # Prepare list of items
    items = []
    for img_el in image_elements:
        name = img_el.get("name")
        w = float(img_el.get("width"))
        h = float(img_el.get("height"))
        src_img_path = os.path.join(IMG_DIR, name)
        if not os.path.exists(src_img_path):
            print(f"Warning: image file not found: {src_img_path}")
            continue

        boxes = []
        for box_el in img_el.findall("box"):
            if box_el.get("label") == "ball":
                xtl = float(box_el.get("xtl"))
                ytl = float(box_el.get("ytl"))
                xbr = float(box_el.get("xbr"))
                ybr = float(box_el.get("ybr"))

                # Clamp to image boundaries
                xtl = max(0.0, min(xtl, w))
                ytl = max(0.0, min(ytl, h))
                xbr = max(0.0, min(xbr, w))
                ybr = max(0.0, min(ybr, h))

                bw = xbr - xtl
                bh = ybr - ytl
                if bw > 2 and bh > 2:
                    xc = (xtl + xbr) / 2.0 / w
                    yc = (ytl + ybr) / 2.0 / h
                    wn = bw / w
                    hn = bh / h
                    boxes.append((xc, yc, wn, hn))

        items.append({
            "name": name,
            "src_path": src_img_path,
            "boxes": boxes
        })

    print(f"Total valid annotated items: {len(items)}")

    # Shuffle and split 85% train / 15% val
    random.shuffle(items)
    n_val = int(len(items) * 0.15)
    val_items = items[:n_val]
    train_items = items[n_val:]

    print(f"Split: {len(train_items)} train, {len(val_items)} val")

    # Add 8 background negative images to train as well
    disk_files = set(os.listdir(IMG_DIR))
    xml_files = set(img_el.get("name") for img_el in image_elements)
    diff = sorted(list(disk_files - xml_files))
    extra_bg = []
    for extra_name in diff:
        p = os.path.join(IMG_DIR, extra_name)
        if extra_name.lower().endswith((".jpg", ".png", ".jpeg")) and os.path.exists(p):
            extra_bg.append({
                "name": extra_name,
                "src_path": p,
                "boxes": [] # 0 boxes = pure hard negative background
            })
    print(f"Adding {len(extra_bg)} unannotated background negatives to train split.")
    train_items.extend(extra_bg)

    # Process and copy to dataset
    splits = [("train", train_items), ("val", val_items)]
    total_copied = 0
    total_boxes = 0

    for split_name, split_list in splits:
        img_dest_dir = os.path.join(DATASET_DIR, "images", split_name)
        lbl_dest_dir = os.path.join(DATASET_DIR, "labels", split_name)
        os.makedirs(img_dest_dir, exist_ok=True)
        os.makedirs(lbl_dest_dir, exist_ok=True)

        for item in split_list:
            base_name = f"wb_{item['name']}"
            dst_img_path = os.path.join(img_dest_dir, base_name)
            txt_name = os.path.splitext(base_name)[0] + ".txt"
            dst_lbl_path = os.path.join(lbl_dest_dir, txt_name)

            # Copy image
            shutil.copy2(item["src_path"], dst_img_path)

            # Write YOLO label file
            with open(dst_lbl_path, "w") as lf:
                for xc, yc, wn, hn in item["boxes"]:
                    lf.write(f"0 {xc:.6f} {yc:.6f} {wn:.6f} {hn:.6f}\n")
                    total_boxes += 1

            total_copied += 1

    print(f"SUCCESS: Integrated {total_copied} images and {total_boxes} ball annotations into {DATASET_DIR}")

if __name__ == "__main__":
    main()
