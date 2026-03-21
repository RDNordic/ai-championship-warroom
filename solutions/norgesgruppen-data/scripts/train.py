"""
Train YOLOv8 on NorgesGruppen grocery shelf detection data.

Converts COCO annotations to YOLO format, splits 80/20 train/val,
then trains a YOLOv8 model.

Usage:
    python scripts/train.py [--model-size s] [--epochs 50] [--batch 16] [--imgsz 1280]
    python scripts/train.py --model-size m --epochs 100 --imgsz 1280

After training, copy best.pt to submission/:
    cp runs/detect/train/weights/best.pt submission/yolov8s.pt
"""

import argparse
import functools
import json
import random
import shutil
from pathlib import Path

import torch

# ultralytics 8.1.0 + torch 2.6.0 compat: restore weights_only=False default
_original_torch_load = torch.load
torch.load = functools.partial(_original_torch_load, weights_only=False)

from ultralytics import YOLO


def coco_to_yolo(
    annotations_path: Path,
    images_dir: Path,
    output_dir: Path,
    val_fraction: float = 0.2,
    seed: int = 42,
) -> Path:
    """Convert COCO annotations to YOLO format with train/val split.

    YOLO format per line: <class_id> <x_center> <y_center> <width> <height>
    All values normalized to [0, 1].

    Returns path to the generated dataset.yaml.
    """
    with open(annotations_path) as f:
        coco = json.load(f)

    # Build lookup: image_id -> image info
    images_by_id = {img["id"]: img for img in coco["images"]}

    # Build lookup: image_id -> list of annotations
    anns_by_image: dict[int, list] = {}
    for ann in coco["annotations"]:
        anns_by_image.setdefault(ann["image_id"], []).append(ann)

    # Filter to images that exist on disk
    available_images = []
    for img in coco["images"]:
        img_path = images_dir / img["file_name"]
        if img_path.exists():
            available_images.append(img)

    if not available_images:
        raise FileNotFoundError(f"No images found in {images_dir}")

    print(f"Found {len(available_images)}/{len(coco['images'])} images on disk")

    # Shuffle and split
    random.seed(seed)
    random.shuffle(available_images)
    split_idx = int(len(available_images) * (1 - val_fraction))
    train_images = available_images[:split_idx]
    val_images = available_images[split_idx:]

    print(f"Split: {len(train_images)} train, {len(val_images)} val")

    # Create YOLO directory structure
    dataset_dir = output_dir / "dataset"
    for split_name, split_images in [("train", train_images), ("val", val_images)]:
        img_out = dataset_dir / split_name / "images"
        lbl_out = dataset_dir / split_name / "labels"
        img_out.mkdir(parents=True, exist_ok=True)
        lbl_out.mkdir(parents=True, exist_ok=True)

        for img_info in split_images:
            src = images_dir / img_info["file_name"]
            dst = img_out / img_info["file_name"]

            # Symlink image (avoid copying large files)
            if dst.exists():
                dst.unlink()
            dst.symlink_to(src.resolve())

            # Write YOLO label file
            img_w = img_info["width"]
            img_h = img_info["height"]
            label_file = lbl_out / (Path(img_info["file_name"]).stem + ".txt")

            lines = []
            for ann in anns_by_image.get(img_info["id"], []):
                # COCO bbox: [x, y, w, h] (top-left corner)
                bx, by, bw, bh = ann["bbox"]
                # Convert to YOLO: center_x, center_y, width, height (normalized)
                cx = (bx + bw / 2) / img_w
                cy = (by + bh / 2) / img_h
                nw = bw / img_w
                nh = bh / img_h
                # Clamp to [0, 1]
                cx = max(0.0, min(1.0, cx))
                cy = max(0.0, min(1.0, cy))
                nw = max(0.0, min(1.0, nw))
                nh = max(0.0, min(1.0, nh))

                lines.append(f"{ann['category_id']} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")

            label_file.write_text("\n".join(lines) + "\n" if lines else "")

    # Build category names
    cat_names = {cat["id"]: cat["name"] for cat in coco["categories"]}
    nc = len(coco["categories"])

    # Write dataset.yaml
    yaml_path = dataset_dir / "dataset.yaml"
    yaml_lines = [
        f"path: {dataset_dir.resolve()}",
        "train: train/images",
        "val: val/images",
        f"nc: {nc}",
        "names:",
    ]
    for cat_id in sorted(cat_names.keys()):
        # Escape quotes in names
        name = cat_names[cat_id].replace("'", "''")
        yaml_lines.append(f"  {cat_id}: '{name}'")

    yaml_path.write_text("\n".join(yaml_lines) + "\n")
    print(f"Dataset YAML: {yaml_path}")

    return yaml_path


def train(
    yaml_path: Path,
    model_size: str = "s",
    epochs: int = 50,
    batch: int = 16,
    imgsz: int = 1280,
    project: str = "runs/detect",
    name: str = "train",
    resume: bool = False,
) -> Path:
    """Train YOLOv8 and return path to best weights."""
    if resume:
        # Resume from last checkpoint
        last_pt = Path(project) / name / "weights" / "last.pt"
        if not last_pt.exists():
            print(f"No checkpoint found at {last_pt}, starting fresh")
            resume = False
        else:
            print(f"Resuming from {last_pt}")
            model = YOLO(str(last_pt))
            results = model.train(resume=True)
            best_path = Path(project) / name / "weights" / "best.pt"
            return best_path

    # Load pretrained model
    model = YOLO(f"yolov8{model_size}.pt")

    results = model.train(
        data=str(yaml_path),
        epochs=epochs,
        batch=batch,
        imgsz=imgsz,
        project=project,
        name=name,
        exist_ok=True,
        # Performance
        workers=4,
        # Augmentation (sensible defaults for grocery shelves)
        hsv_h=0.015,
        hsv_s=0.7,
        hsv_v=0.4,
        degrees=0.0,       # No rotation — shelves are upright
        translate=0.1,
        scale=0.5,
        fliplr=0.5,
        flipud=0.0,        # No vertical flip — shelves don't flip
        mosaic=1.0,
        mixup=0.0,
        # Saving
        save=True,
        save_period=10,
        # Validation
        val=True,
        seed=42,
        deterministic=True,
        verbose=True,
    )

    best_path = Path(project) / name / "weights" / "best.pt"
    print(f"\nBest weights: {best_path}")
    print(f"Size: {best_path.stat().st_size / 1024 / 1024:.1f} MB")

    return best_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Train YOLOv8 on grocery shelf data")
    parser.add_argument("--model-size", type=str, default="s",
                        choices=["n", "s", "m", "l", "x"],
                        help="YOLOv8 model size (default: s)")
    parser.add_argument("--epochs", type=int, default=50,
                        help="Training epochs (default: 50)")
    parser.add_argument("--batch", type=int, default=16,
                        help="Batch size (default: 16, use -1 for auto)")
    parser.add_argument("--imgsz", type=int, default=1280,
                        help="Training image size (default: 1280)")
    parser.add_argument("--val-fraction", type=float, default=0.2,
                        help="Validation set fraction (default: 0.2)")
    parser.add_argument("--resume", action="store_true",
                        help="Resume training from last checkpoint")
    parser.add_argument("--augmented", action="store_true",
                        help="Use augmented data from data/train_augmented/")
    parser.add_argument("--tiled", action="store_true",
                        help="Use tiled data from data/train_tiled/ (or train_tiled_augmented/ with --augmented)")
    parser.add_argument("--project", type=str, default="runs/detect",
                        help="Project directory for outputs")
    parser.add_argument("--name", type=str, default="train",
                        help="Run name within project")
    args = parser.parse_args()

    project_dir = Path(__file__).resolve().parent.parent

    if args.tiled and args.augmented:
        annotations_path = project_dir / "data" / "train_tiled_augmented" / "annotations.json"
        images_dir = project_dir / "data" / "train_tiled_augmented" / "images"
    elif args.tiled:
        annotations_path = project_dir / "data" / "train_tiled" / "annotations.json"
        images_dir = project_dir / "data" / "train_tiled" / "images"
    elif args.augmented:
        annotations_path = project_dir / "data" / "train_augmented" / "annotations.json"
        images_dir = project_dir / "data" / "train_augmented" / "images"
    else:
        annotations_path = project_dir / "data" / "train" / "annotations.json"
        images_dir = project_dir / "data" / "train" / "images"

    if not annotations_path.exists():
        print(f"ERROR: annotations not found at {annotations_path}")
        if args.tiled:
            print("Run: python scripts/tile_dataset.py" + (" --augmented" if args.augmented else ""))
        elif args.augmented:
            print("Run: python scripts/augment_copypaste.py")
        raise SystemExit(1)

    # Step 1: Convert COCO → YOLO format with train/val split
    print("=" * 50)
    print("Step 1: Converting COCO to YOLO format")
    print("=" * 50)
    yaml_path = coco_to_yolo(
        annotations_path=annotations_path,
        images_dir=images_dir,
        output_dir=project_dir / "data",
        val_fraction=args.val_fraction,
    )

    # Step 2: Train
    print("\n" + "=" * 50)
    print(f"Step 2: Training YOLOv8{args.model_size} for {args.epochs} epochs")
    print("=" * 50)
    best_path = train(
        yaml_path=yaml_path,
        model_size=args.model_size,
        epochs=args.epochs,
        batch=args.batch,
        imgsz=args.imgsz,
        project=str(project_dir / args.project),
        name=args.name,
        resume=args.resume,
    )

    # Step 3: Copy to submission
    submission_weight = project_dir / "submission" / f"yolov8{args.model_size}.pt"
    shutil.copy2(best_path, submission_weight)
    print(f"\nCopied best weights to {submission_weight}")
    print("Ready to build submission: python scripts/prepare_submission.py")


if __name__ == "__main__":
    main()
