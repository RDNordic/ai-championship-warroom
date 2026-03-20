"""
Offline copy-paste augmentation using individual product reference images.

For each training image, pastes random product cutouts onto the image,
generating new synthetic training samples with extra annotations for
underrepresented categories.

This runs BEFORE train.py — it extends the COCO annotations and writes
augmented images to data/train_augmented/.

Usage:
    python scripts/augment_copypaste.py [--num-augmented 248] [--pastes-per-image 10]
"""

import argparse
import json
import random
from pathlib import Path

import cv2
import numpy as np


def build_category_to_product_images(
    annotations_path: Path,
    metadata_path: Path,
    individ_dir: Path,
) -> dict[int, list[Path]]:
    """Map category_id -> list of individual product image paths."""
    with open(annotations_path) as f:
        coco = json.load(f)
    with open(metadata_path) as f:
        meta = json.load(f)

    cats = {c["id"]: c["name"] for c in coco["categories"]}
    name_to_cat = {name: cid for cid, name in cats.items()}
    code_to_name = {p["product_code"]: p["product_name"] for p in meta["products"]}

    cat_to_images: dict[int, list[Path]] = {}

    for product_dir in individ_dir.iterdir():
        if not product_dir.is_dir():
            continue
        product_code = product_dir.name
        product_name = code_to_name.get(product_code)
        if not product_name or product_name not in name_to_cat:
            continue

        cat_id = name_to_cat[product_name]
        imgs = sorted(product_dir.glob("*.jpg"))
        if imgs:
            cat_to_images[cat_id] = imgs

    return cat_to_images


def extract_foreground(img: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Extract product foreground from light background using GrabCut.

    Returns (img, mask) where mask is 0/255 uint8.
    """
    h, w = img.shape[:2]

    # Start with a rectangle that excludes a thin border
    margin = max(3, min(h, w) // 20)
    rect = (margin, margin, w - 2 * margin, h - 2 * margin)

    mask = np.zeros((h, w), np.uint8)
    bgd_model = np.zeros((1, 65), np.float64)
    fgd_model = np.zeros((1, 65), np.float64)

    try:
        cv2.grabCut(img, mask, rect, bgd_model, fgd_model, 3, cv2.GC_INIT_WITH_RECT)
    except cv2.error:
        # Fallback: simple brightness threshold
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 220, 255, cv2.THRESH_BINARY_INV)
        return img, binary

    # Convert GrabCut mask: 0,2 = background, 1,3 = foreground
    fg_mask = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)

    # Clean up with morphology
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel)
    fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)

    return img, fg_mask


def paste_product(
    canvas: np.ndarray,
    product_img: np.ndarray,
    product_mask: np.ndarray,
    x: int,
    y: int,
    target_w: int,
    target_h: int,
) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """Paste a masked product onto the canvas at (x, y) with given size.

    Returns (modified_canvas, (x, y, w, h) in COCO format).
    """
    canvas_h, canvas_w = canvas.shape[:2]

    # Resize product and mask
    resized_img = cv2.resize(product_img, (target_w, target_h), interpolation=cv2.INTER_AREA)
    resized_mask = cv2.resize(product_mask, (target_w, target_h), interpolation=cv2.INTER_NEAREST)

    # Clamp to canvas bounds
    x1 = max(0, x)
    y1 = max(0, y)
    x2 = min(canvas_w, x + target_w)
    y2 = min(canvas_h, y + target_h)

    if x2 - x1 < 10 or y2 - y1 < 10:
        return canvas, None

    # Compute offsets into the product image
    px1 = x1 - x
    py1 = y1 - y
    px2 = px1 + (x2 - x1)
    py2 = py1 + (y2 - y1)

    crop_img = resized_img[py1:py2, px1:px2]
    crop_mask = resized_mask[py1:py2, px1:px2]

    # Alpha blend using mask
    alpha = (crop_mask.astype(np.float32) / 255.0)[..., np.newaxis]
    roi = canvas[y1:y2, x1:x2].astype(np.float32)
    blended = roi * (1 - alpha) + crop_img.astype(np.float32) * alpha
    canvas[y1:y2, x1:x2] = blended.astype(np.uint8)

    # COCO bbox
    bbox = (x1, y1, x2 - x1, y2 - y1)
    return canvas, bbox


def build_sampling_weights(
    coco: dict,
    cat_to_images: dict[int, list[Path]],
) -> tuple[list[int], list[float]]:
    """Build category sampling weights — inverse frequency so rare classes are pasted more."""
    from collections import Counter

    cat_counts = Counter(a["category_id"] for a in coco["annotations"])

    # Only categories that have individual images
    eligible = [cid for cid in cat_to_images if cid in cat_counts]
    if not eligible:
        return [], []

    # Inverse frequency weights
    max_count = max(cat_counts[c] for c in eligible)
    weights = []
    for cid in eligible:
        # Rare categories get higher weight
        w = max_count / max(cat_counts[cid], 1)
        weights.append(w)

    # Normalize
    total = sum(weights)
    weights = [w / total for w in weights]

    return eligible, weights


def augment_dataset(
    project_dir: Path,
    num_augmented: int = 248,
    pastes_per_image: int = 10,
    seed: int = 42,
) -> None:
    """Generate augmented training images with copy-pasted products."""
    random.seed(seed)
    np.random.seed(seed)

    annotations_path = project_dir / "data" / "train" / "annotations.json"
    metadata_path = project_dir / "data" / "metadata.json"
    individ_dir = project_dir / "data" / "individ"
    images_dir = project_dir / "data" / "train" / "images"

    # Output directories
    aug_dir = project_dir / "data" / "train_augmented"
    aug_images_dir = aug_dir / "images"
    aug_images_dir.mkdir(parents=True, exist_ok=True)

    with open(annotations_path) as f:
        coco = json.load(f)

    # Build category -> product images mapping
    cat_to_images = build_category_to_product_images(
        annotations_path, metadata_path, individ_dir
    )
    print(f"Categories with individual images: {len(cat_to_images)}/{len(coco['categories'])}")

    # Pre-extract foregrounds (cache to avoid repeated GrabCut)
    print("Extracting product foregrounds...")
    cat_to_cutouts: dict[int, list[tuple[np.ndarray, np.ndarray]]] = {}
    for cat_id, img_paths in cat_to_images.items():
        cutouts = []
        # Use front and main views (best for shelf appearance)
        preferred = []
        for p in img_paths:
            if p.stem in ("front", "main"):
                preferred.append(p)
        if not preferred:
            preferred = img_paths[:2]

        for p in preferred:
            img = cv2.imread(str(p))
            if img is None:
                continue
            img_fg, mask = extract_foreground(img)
            # Skip if mask is mostly empty
            if mask.sum() < 500:
                continue
            cutouts.append((img_fg, mask))

        if cutouts:
            cat_to_cutouts[cat_id] = cutouts

    print(f"Categories with valid cutouts: {len(cat_to_cutouts)}")

    # Build sampling weights (favor rare categories)
    eligible_cats, weights = build_sampling_weights(coco, cat_to_cutouts)
    if not eligible_cats:
        print("ERROR: No eligible categories for augmentation")
        return

    # Bbox size distribution from annotations (for realistic sizing)
    bbox_widths = [a["bbox"][2] for a in coco["annotations"]]
    bbox_heights = [a["bbox"][3] for a in coco["annotations"]]
    # Use percentiles for sampling range
    w_lo, w_hi = int(np.percentile(bbox_widths, 15)), int(np.percentile(bbox_widths, 85))
    h_lo, h_hi = int(np.percentile(bbox_heights, 15)), int(np.percentile(bbox_heights, 85))
    print(f"Paste size range: w=[{w_lo}, {w_hi}], h=[{h_lo}, {h_hi}]")

    # Collect source images
    source_images = sorted(
        p for p in images_dir.iterdir()
        if p.suffix.lower() in (".jpg", ".jpeg", ".png")
    )

    images_by_id = {img["id"]: img for img in coco["images"]}

    # New annotations list = original + augmented
    new_annotations = list(coco["annotations"])
    new_images = list(coco["images"])
    next_ann_id = max(a["id"] for a in coco["annotations"]) + 1
    next_img_id = max(img["id"] for img in coco["images"]) + 1

    print(f"\nGenerating {num_augmented} augmented images with {pastes_per_image} pastes each...")

    for aug_idx in range(num_augmented):
        # Pick a random source image
        src_path = random.choice(source_images)
        canvas = cv2.imread(str(src_path))
        if canvas is None:
            continue

        canvas_h, canvas_w = canvas.shape[:2]
        aug_filename = f"aug_{aug_idx:05d}.jpg"

        # Track new annotations for this image
        img_annotations = []

        for _ in range(pastes_per_image):
            # Sample a category (weighted toward rare ones)
            cat_id = random.choices(eligible_cats, weights=weights, k=1)[0]
            cutouts = cat_to_cutouts[cat_id]
            product_img, product_mask = random.choice(cutouts)

            # Sample target size preserving product aspect ratio
            prod_h, prod_w = product_img.shape[:2]
            aspect = prod_w / max(prod_h, 1)

            # Random size within distribution
            target_h = random.randint(h_lo, h_hi)
            target_w = max(20, int(target_h * aspect))
            # Clamp width to reasonable range
            target_w = min(target_w, w_hi)
            target_w = max(target_w, w_lo // 2)

            # Random position
            x = random.randint(0, max(1, canvas_w - target_w))
            y = random.randint(0, max(1, canvas_h - target_h))

            # Paste
            canvas, bbox = paste_product(canvas, product_img, product_mask, x, y, target_w, target_h)
            if bbox is None:
                continue

            img_annotations.append({
                "id": next_ann_id,
                "image_id": next_img_id,
                "category_id": cat_id,
                "bbox": list(bbox),
                "area": bbox[2] * bbox[3],
                "iscrowd": 0,
            })
            next_ann_id += 1

        # Save augmented image
        cv2.imwrite(str(aug_images_dir / aug_filename), canvas)

        # Add image entry
        new_images.append({
            "id": next_img_id,
            "file_name": aug_filename,
            "width": canvas_w,
            "height": canvas_h,
        })
        new_annotations.extend(img_annotations)
        next_img_id += 1

        if (aug_idx + 1) % 50 == 0:
            print(f"  Generated {aug_idx + 1}/{num_augmented} images")

    # Also symlink original images into augmented dir
    for img_path in source_images:
        dst = aug_images_dir / img_path.name
        if not dst.exists():
            dst.symlink_to(img_path.resolve())

    # Write combined annotations
    aug_annotations = {
        "images": new_images,
        "annotations": new_annotations,
        "categories": coco["categories"],
    }
    aug_ann_path = aug_dir / "annotations.json"
    aug_ann_path.write_text(json.dumps(aug_annotations))

    orig_count = len(coco["annotations"])
    new_count = len(new_annotations) - orig_count
    print(f"\nDone!")
    print(f"  Original: {len(coco['images'])} images, {orig_count} annotations")
    print(f"  Augmented: {num_augmented} new images, {new_count} new annotations")
    print(f"  Total: {len(new_images)} images, {len(new_annotations)} annotations")
    print(f"  Output: {aug_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy-paste augmentation with product images")
    parser.add_argument("--num-augmented", type=int, default=248,
                        help="Number of augmented images to generate (default: 248)")
    parser.add_argument("--pastes-per-image", type=int, default=10,
                        help="Products to paste per image (default: 10)")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    project_dir = Path(__file__).resolve().parent.parent

    augment_dataset(
        project_dir=project_dir,
        num_augmented=args.num_augmented,
        pastes_per_image=args.pastes_per_image,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
