import os
import sys
import shutil
import random
import unicodedata
import xml.etree.ElementTree as ET
import cv2

BASE_DIR = "/Users/thaladasrinivas/Downloads/stumps"
NAIMI_DIR = os.path.join(BASE_DIR, "StumpCalib(NAIMI) 27-10")
XML_PATH = os.path.join(NAIMI_DIR, "annotations 12.xml")
DATASET_DIR = os.path.join(BASE_DIR, "ball_dataset")

def normalize_filename(name):
    """Normalize unicode spaces and characters to match disk filenames."""
    s = unicodedata.normalize("NFKD", name)
    return s.replace(" ", "").replace("\u202f", "").replace("\u00a0", "")

def main():
    if not os.path.exists(XML_PATH):
        print(f"Error: {XML_PATH} does not exist")
        sys.exit(1)
    if not os.path.exists(NAIMI_DIR):
        print(f"Error: {NAIMI_DIR} does not exist")
        sys.exit(1)

    print("=" * 70)
    print("INGESTING STUMPCALIB(NAIMI) 27-10 ANNOTATIONS INTO BALL DATASET")
    print("=" * 70)

    # Build disk mapping using normalized names
    disk_files = [f for f in os.listdir(NAIMI_DIR) if f.lower().endswith((".png", ".jpg", ".jpeg"))]
    norm_to_disk = {normalize_filename(f): f for f in disk_files}
    print(f"Found {len(disk_files)} images on disk in {NAIMI_DIR}")

    tree = ET.parse(XML_PATH)
    root = tree.getroot()
    image_elements = root.findall("image")
    print(f"Found {len(image_elements)} <image> entries in {XML_PATH}")

    random.seed(42)

    annotated_items = []
    skipped = 0

    for img_el in image_elements:
        xml_name = img_el.get("name")
        norm_key = normalize_filename(xml_name)
        disk_filename = norm_to_disk.get(norm_key)

        if not disk_filename:
            print(f"Warning: file not found on disk for XML entry: {xml_name}")
            skipped += 1
            continue

        src_path = os.path.join(NAIMI_DIR, disk_filename)
        mat = cv2.imread(src_path)
        if mat is None:
            print(f"Warning: unreadable image: {src_path}")
            skipped += 1
            continue

        actual_h, actual_w = mat.shape[:2]
        boxes = []

        for box_el in img_el.findall("box"):
            label = box_el.get("label", "").lower()
            if label == "ball":
                xtl = float(box_el.get("xtl"))
                ytl = float(box_el.get("ytl"))
                xbr = float(box_el.get("xbr"))
                ybr = float(box_el.get("ybr"))

                # Clamp to image bounds
                xtl = max(0.0, min(xtl, float(actual_w)))
                ytl = max(0.0, min(ytl, float(actual_h)))
                xbr = max(0.0, min(xbr, float(actual_w)))
                ybr = max(0.0, min(ybr, float(actual_h)))

                bw = xbr - xtl
                bh = ybr - ytl

                if bw >= 2 and bh >= 2:
                    xc = (xtl + xbr) / 2.0 / float(actual_w)
                    yc = (ytl + ybr) / 2.0 / float(actual_h)
                    wn = bw / float(actual_w)
                    hn = bh / float(actual_h)
                    boxes.append((xc, yc, wn, hn))

        if len(boxes) > 0:
            annotated_items.append({
                "disk_filename": disk_filename,
                "src_path": src_path,
                "boxes": boxes
            })

    print(f"Successfully processed {len(annotated_items)} annotated images with ball bounding boxes.")
    if skipped > 0:
        print(f"Skipped {skipped} entries due to missing/corrupt files.")

    # Stratified split: 85% train (219 images) and 15% val (39 images)
    random.shuffle(annotated_items)
    n_val = int(len(annotated_items) * 0.15)
    val_items = annotated_items[:n_val]
    train_items = annotated_items[n_val:]

    print(f"Split: {len(train_items)} train images, {len(val_items)} validation images.")

    splits = [("train", train_items), ("val", val_items)]
    total_copied = 0
    total_boxes = 0

    for split_name, items in splits:
        img_dest_dir = os.path.join(DATASET_DIR, "images", split_name)
        lbl_dest_dir = os.path.join(DATASET_DIR, "labels", split_name)
        os.makedirs(img_dest_dir, exist_ok=True)
        os.makedirs(lbl_dest_dir, exist_ok=True)

        for item in items:
            raw_name = item["disk_filename"]
            base_root, ext = os.path.splitext(raw_name)
            # Create a clean safe base name without special characters or spaces
            clean_base = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in base_root)
            target_base = f"naimi2710_{clean_base}"
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

    print("\nIngestion Complete!")
    print(f"Total new images added: {total_copied}")
    print(f"Total new ball labels added: {total_boxes}")

    print("\n--- Full Updated Ball Dataset Summary ---")
    grand_total_imgs = 0
    grand_total_lbls = 0
    for s in ["train", "val", "test"]:
        imgs = os.listdir(os.path.join(DATASET_DIR, "images", s))
        lbls = os.listdir(os.path.join(DATASET_DIR, "labels", s))
        grand_total_imgs += len(imgs)
        grand_total_lbls += len(lbls)
        print(f"  {s.upper()}: {len(imgs)} images, {len(lbls)} label files")
    print(f"  TOTAL: {grand_total_imgs} images, {grand_total_lbls} labels")

if __name__ == "__main__":
    main()
