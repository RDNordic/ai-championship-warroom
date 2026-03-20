"""
RunPod serverless handler for YOLOv8 training.

Training data is baked into the Docker image at /data/train/.
Trained weights are returned base64-encoded in the job response.

Job input schema:
{
    "model_size": "s",        # n/s/m/l/x (default: s)
    "epochs": 50,             # (default: 50)
    "batch": 16,              # (default: 16, -1 for auto)
    "imgsz": 1280,            # (default: 1280)
    "val_fraction": 0.2,      # (default: 0.2)
    "data_path": "/data/train",  # (default, baked into image)
}
"""

import base64
import functools
import json
import random
import time
from pathlib import Path

import torch

# ultralytics 8.1.0 + torch 2.6.0 compat
_original_torch_load = torch.load
torch.load = functools.partial(_original_torch_load, weights_only=False)

import runpod
from ultralytics import YOLO


DEFAULT_DATA_PATH = Path("/data/train")


def coco_to_yolo(
    annotations_path: Path,
    images_dir: Path,
    output_dir: Path,
    val_fraction: float = 0.2,
    seed: int = 42,
) -> Path:
    """Convert COCO annotations to YOLO format with train/val split."""
    with open(annotations_path) as f:
        coco = json.load(f)

    anns_by_image: dict[int, list] = {}
    for ann in coco["annotations"]:
        anns_by_image.setdefault(ann["image_id"], []).append(ann)

    available_images = [
        img for img in coco["images"]
        if (images_dir / img["file_name"]).exists()
    ]

    if not available_images:
        raise FileNotFoundError(f"No images found in {images_dir}")

    print(f"Found {len(available_images)}/{len(coco['images'])} images on disk")

    random.seed(seed)
    random.shuffle(available_images)
    split_idx = int(len(available_images) * (1 - val_fraction))
    train_images = available_images[:split_idx]
    val_images = available_images[split_idx:]

    print(f"Split: {len(train_images)} train, {len(val_images)} val")

    dataset_dir = output_dir / "dataset"
    for split_name, split_images in [("train", train_images), ("val", val_images)]:
        img_out = dataset_dir / split_name / "images"
        lbl_out = dataset_dir / split_name / "labels"
        img_out.mkdir(parents=True, exist_ok=True)
        lbl_out.mkdir(parents=True, exist_ok=True)

        for img_info in split_images:
            src = images_dir / img_info["file_name"]
            dst = img_out / img_info["file_name"]

            if dst.exists():
                dst.unlink()
            dst.symlink_to(src.resolve())

            img_w = img_info["width"]
            img_h = img_info["height"]
            label_file = lbl_out / (Path(img_info["file_name"]).stem + ".txt")

            lines = []
            for ann in anns_by_image.get(img_info["id"], []):
                bx, by, bw, bh = ann["bbox"]
                cx = max(0.0, min(1.0, (bx + bw / 2) / img_w))
                cy = max(0.0, min(1.0, (by + bh / 2) / img_h))
                nw = max(0.0, min(1.0, bw / img_w))
                nh = max(0.0, min(1.0, bh / img_h))
                lines.append(f"{ann['category_id']} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")

            label_file.write_text("\n".join(lines) + "\n" if lines else "")

    cat_names = {cat["id"]: cat["name"] for cat in coco["categories"]}
    nc = len(coco["categories"])

    yaml_path = dataset_dir / "dataset.yaml"
    yaml_lines = [
        f"path: {dataset_dir.resolve()}",
        "train: train/images",
        "val: val/images",
        f"nc: {nc}",
        "names:",
    ]
    for cat_id in sorted(cat_names.keys()):
        name = cat_names[cat_id].replace("'", "''")
        yaml_lines.append(f"  {cat_id}: '{name}'")

    yaml_path.write_text("\n".join(yaml_lines) + "\n")
    print(f"Dataset YAML: {yaml_path}")
    return yaml_path


def train_yolo(
    yaml_path: Path,
    model_size: str = "s",
    epochs: int = 50,
    batch: int = 16,
    imgsz: int = 1280,
    project: str = "/tmp/runs/detect",
    name: str = "train",
) -> Path:
    """Train YOLOv8 and return path to best weights."""
    model = YOLO(f"yolov8{model_size}.pt")

    model.train(
        data=str(yaml_path),
        epochs=epochs,
        batch=batch,
        imgsz=imgsz,
        project=project,
        name=name,
        exist_ok=True,
        workers=4,
        # Augmentation for grocery shelves
        hsv_h=0.015,
        hsv_s=0.7,
        hsv_v=0.4,
        degrees=0.0,
        translate=0.1,
        scale=0.5,
        fliplr=0.5,
        flipud=0.0,
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
    return best_path


def handler(job):
    """RunPod serverless handler for YOLOv8 training."""
    job_input = job["input"]
    start_time = time.time()

    model_size = job_input.get("model_size", "s")
    epochs = job_input.get("epochs", 50)
    batch = job_input.get("batch", 16)
    imgsz = job_input.get("imgsz", 1280)
    val_fraction = job_input.get("val_fraction", 0.2)
    data_path = Path(job_input.get("data_path", str(DEFAULT_DATA_PATH)))

    annotations_path = data_path / "annotations.json"
    images_dir = data_path / "images"

    if not annotations_path.exists():
        return {"error": f"annotations.json not found at {annotations_path}"}
    if not images_dir.exists():
        return {"error": f"Images directory not found at {images_dir}"}

    # Step 1: Convert COCO → YOLO format
    print("=" * 50)
    print("Step 1: Converting COCO to YOLO format")
    print("=" * 50)
    yaml_path = coco_to_yolo(
        annotations_path=annotations_path,
        images_dir=images_dir,
        output_dir=Path("/tmp"),
        val_fraction=val_fraction,
    )

    # Step 2: Train
    print("\n" + "=" * 50)
    print(f"Step 2: Training YOLOv8{model_size} for {epochs} epochs")
    print("=" * 50)
    best_path = train_yolo(
        yaml_path=yaml_path,
        model_size=model_size,
        epochs=epochs,
        batch=batch,
        imgsz=imgsz,
    )

    # Step 3: Base64-encode weights for return
    results_dir = best_path.parent.parent
    weights_dir = best_path.parent
    last_path = weights_dir / "last.pt"

    response = {
        "status": "complete",
        "model_size": model_size,
        "epochs": epochs,
        "elapsed_seconds": round(time.time() - start_time),
    }

    # Encode best.pt
    if best_path.exists():
        best_bytes = best_path.read_bytes()
        response["best_pt_b64"] = base64.b64encode(best_bytes).decode("ascii")
        response["best_pt_size_mb"] = round(len(best_bytes) / (1024 * 1024), 1)
        print(f"best.pt: {response['best_pt_size_mb']} MB")

    # Encode last.pt
    if last_path.exists():
        last_bytes = last_path.read_bytes()
        response["last_pt_b64"] = base64.b64encode(last_bytes).decode("ascii")
        response["last_pt_size_mb"] = round(len(last_bytes) / (1024 * 1024), 1)
        print(f"last.pt: {response['last_pt_size_mb']} MB")

    # Include results.csv as text
    results_csv = results_dir / "results.csv"
    if results_csv.exists():
        response["results_csv"] = results_csv.read_text()

    print(f"\nTraining complete in {response['elapsed_seconds']}s")
    return response


runpod.serverless.start({"handler": handler})
