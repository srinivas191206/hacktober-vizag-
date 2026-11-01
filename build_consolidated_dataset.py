import os
import shutil
import random
import unicodedata
import yaml

BASE = "/Users/thaladasrinivas/Downloads/stumps"
DATASET_DIR = os.path.join(BASE, "dataset")

DATASETS = [
    {
        "source_tag": "orig",
        "img_dir": os.path.join(BASE, "stumps"),
        "lbl_dir": os.path.join(BASE, "labels", "train")
    },
    {
        "source_tag": "naimi",
        "img_dir": os.path.join(BASE, "StumpCalib(NAIMI) 30-9"),
        "lbl_dir": os.path.join(BASE, "stump(Naimi)", "labels", "train")
    },
    {
        "source_tag": "varun",
        "img_dir": os.path.join(BASE, "StumpCalib(Varun-29-09)"),
        "lbl_dir": os.path.join(BASE, "stump(varun)", "labels", "train")
    }
]

def norm(s):
    return unicodedata.normalize('NFKD', s).replace(' ', '').replace('\u202f', '')

def main():
    random.seed(42)
    print("=" * 70)
    print("BUILDING UNIFIED DATASET ACROSS 3 SOURCES (80% Train, 10% Val, 10% Test)")
    print("=" * 70)

    # Clean existing dataset directory
    if os.path.exists(DATASET_DIR):
        shutil.rmtree(DATASET_DIR)

    for split in ['train', 'val', 'test']:
        os.makedirs(os.path.join(DATASET_DIR, "images", split), exist_ok=True)
        os.makedirs(os.path.join(DATASET_DIR, "labels", split), exist_ok=True)

    all_pairs = []
    source_stats = {}

    for d in DATASETS:
        tag = d["source_tag"]
        img_dir = d["img_dir"]
        lbl_dir = d["lbl_dir"]
        
        raw_images = [f for f in os.listdir(img_dir) if not f.startswith('.')]
        raw_labels = [f for f in os.listdir(lbl_dir) if not f.startswith('.')]
        
        lbl_map = {}
        for l in raw_labels:
            stem = os.path.splitext(l)[0]
            lbl_map[stem] = l
            lbl_map[norm(stem)] = l

        matched = []
        for img in raw_images:
            stem = os.path.splitext(img)[0]
            lbl_file = lbl_map.get(stem) or lbl_map.get(norm(stem))
            if not lbl_file:
                continue
            
            lbl_path = os.path.join(lbl_dir, lbl_file)
            with open(lbl_path, 'r') as f:
                lines = [l.strip() for l in f if l.strip()]
            if not lines:
                continue

            matched.append((img, lbl_file, img_dir, lbl_dir, tag))

        source_stats[tag] = len(matched)
        print(f"Source [{tag}]: {len(matched)} valid pairs")
        
        # Shuffle each source and perform stratified split (80/10/10)
        random.shuffle(matched)
        n_tot = len(matched)
        n_train = int(n_tot * 0.80)
        n_val = int(n_tot * 0.10)
        
        train_slice = matched[:n_train]
        val_slice = matched[n_train:n_train + n_val]
        test_slice = matched[n_train + n_val:]
        
        splits = [('train', train_slice), ('val', val_slice), ('test', test_slice)]
        for split_name, slice_items in splits:
            for idx, (img_f, lbl_f, s_img_dir, s_lbl_dir, stag) in enumerate(slice_items):
                src_img = os.path.join(s_img_dir, img_f)
                src_lbl = os.path.join(s_lbl_dir, lbl_f)
                
                ext = os.path.splitext(img_f)[1]
                clean_name = img_f.replace(' ', '_').replace('\u202f', '_')
                safe_base = f"{stag}_{split_name}_{idx:03d}_{clean_name}"
                dst_img = os.path.join(DATASET_DIR, "images", split_name, safe_base)
                dst_lbl = os.path.join(DATASET_DIR, "labels", split_name, os.path.splitext(safe_base)[0] + ".txt")
                
                shutil.copy2(src_img, dst_img)
                shutil.copy2(src_lbl, dst_lbl)

    # Build data.yaml
    data_yaml = {
        'path': os.path.abspath(DATASET_DIR),
        'train': 'images/train',
        'val': 'images/val',
        'test': 'images/test',
        'names': {
            0: 'wicket'
        }
    }

    yaml_path = os.path.join(DATASET_DIR, "data.yaml")
    with open(yaml_path, 'w') as f:
        yaml.dump(data_yaml, f, sort_keys=False)

    print("\n" + "=" * 70)
    print("CONSOLIDATION COMPLETE:")
    for split in ['train', 'val', 'test']:
        n_i = len(os.listdir(os.path.join(DATASET_DIR, "images", split)))
        n_l = len(os.listdir(os.path.join(DATASET_DIR, "labels", split)))
        print(f"  {split.upper()}: {n_i} images, {n_l} labels")
    print(f"data.yaml written to: {yaml_path}")

if __name__ == '__main__':
    main()
