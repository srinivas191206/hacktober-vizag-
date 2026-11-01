import os
import sys
import shutil
import random
import xml.etree.ElementTree as ET
import cv2

BASE_DIR = "/Users/thaladasrinivas/Downloads/stumps"
RED_BALL_DIR = os.path.join(BASE_DIR, "Redballdata-21-10")
XML_PATH = os.path.join(BASE_DIR, "annotations 10.xml")
DATASET_DIR = os.path.join(BASE_DIR, "ball_dataset")

def main():
    if not os.path.exists(XML_PATH):
        print(f"Error: {XML_PATH} does not exist!")
        sys.exit(1)
    if not os.path.exists(RED_BALL_DIR):
        print(f"Error: {RED_BALL_DIR} does not exist!")
        sys.exit(1)

    tree = ET.parse(XML_PATH)
    root = tree.getroot()
    image_elements = root.findall("image")
    print(f"Found {len(image_elements)} <image> elements in {XML_PATH}")

    random.seed(42)

    # Process annotated images
    annotated_items = []
    processed_names = set()

    for img_el in image_elements:
        name = img_el.get("name")
        w = float(img_el.get("width"))
        h = float(img_el.get("height"))
        src_path = os.path.join(RED_BALL_DIR, name)

        if not os.path.exists(src_path):
            print(f"Warning: File not found {src_path}")
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

                if bw >= 2 and bh >= 2:
                    xc = (xtl + xbr) / 2.0 / w
                    yc = (ytl + ybr) / 2.0 / h
                    wn = bw / w
                    hn = bh / h
                    boxes.append((xc, yc, wn, hn))

        annotated_items.append({
            "name": name,
            "src_path": src_path,
            "boxes": boxes
        })
        processed_names.add(name)

    print(f"Successfully processed {len(annotated_items)} annotated items.")

    # Find unannotated background negative frames
    all_disk_files = set(f for f in os.listdir(RED_BALL_DIR) if not f.startswith("."))
    negative_names = sorted(list(all_disk_files - processed_names))
    negative_items = []
    for neg_name in negative_names:
        p = os.path.join(RED_BALL_DIR, neg_name)
        if os.path.exists(p) and neg_name.lower().endswith((".jpg", ".png", ".jpeg")):
            negative_items.append({
                "name": neg_name,
                "src_path": p,
                "boxes": []  # Empty boxes = hard negative
            })

    print(f"Found {len(negative_items)} unannotated background negative items.")

    # Shuffle and split 85% train / 15% val
    random.shuffle(annotated_items)
    n_val_annot = int(len(annotated_items) * 0.15)
    val_items = annotated_items[:n_val_annot]
    train_items = annotated_items[n_val_annot:]

    # Add negatives proportionally
    random.shuffle(negative_items)
    n_val_neg = max(1, int(len(negative_items) * 0.15))
    val_items.extend(negative_items[:n_val_neg])
    train_items.extend(negative_items[n_val_neg:])

    print(f"Final split from new dataset: {len(train_items)} train, {len(val_items)} val (total: {len(train_items)+len(val_items)})")

    # Ingest into ball_dataset
    splits = [("train", train_items), ("val", val_items)]
    total_copied = 0
    total_boxes = 0

    for split_name, items in splits:
        img_dest_dir = os.path.join(DATASET_DIR, "images", split_name)
        lbl_dest_dir = os.path.join(DATASET_DIR, "labels", split_name)
        os.makedirs(img_dest_dir, exist_ok=True)
        os.makedirs(lbl_dest_dir, exist_ok=True)

        for item in items:
            raw_name = item["name"]
            base_root, ext = os.path.splitext(raw_name)
            # Prefix to guarantee zero collisions
            target_base = f"red2110_{base_root}"
            target_img_name = f"{target_base}{ext.lower()}"
            target_lbl_name = f"{target_base}.txt"

            dest_img_path = os.path.join(img_dest_dir, target_img_name)
            dest_lbl_path = os.path.join(lbl_dest_dir, target_lbl_name)

            shutil.copy2(item["src_path"], dest_img_path)

            with open(dest_lbl_path, "w") as f:
                for b in item["boxes"]:
                    f.write(f"0 {b[0]:.6f} {b[1]:.6f} {b[2]:.6f} {b[3]:.6f}\n")
                    total_boxes += 1

            total_copied += 1

    print(f"\nIngestion Complete!")
    print(f"Total new images integrated: {total_copied}")
    print(f"Total new ball annotations: {total_boxes}")

    # Summary of full dataset
    print("\n--- Full Updated Ball Dataset Summary ---")
    for s in ["train", "val", "test"]:
        imgs = os.listdir(os.path.join(DATASET_DIR, "images", s))
        lbls = os.listdir(os.path.join(DATASET_DIR, "labels", s))
        print(f"  {s.upper()}: {len(imgs)} images, {len(lbls)} label files")

if __name__ == "__main__":
    main()
