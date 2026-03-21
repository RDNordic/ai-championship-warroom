"""
Offline copy-paste augmentation v2 — section-aware + replace-in-place.

Two improvements over v1:
1. Section-aware: only paste products from the same store section as the base image
2. Replace-in-place: swap existing annotated products with different angles of the
   same product, keeping original background pixels (no black fill)

Usage:
    python scripts/augment_copypaste_v2.py [--num-augmented 248] [--pastes-per-image 8] \
        [--replace-fraction 0.4]
"""

import argparse
import json
import random
from collections import Counter
from pathlib import Path

import cv2
import numpy as np


# ---------------------------------------------------------------------------
# Foreground extraction (reused from v1)
# ---------------------------------------------------------------------------

def extract_foreground(img: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Extract product foreground from light background using GrabCut.

    Returns (img, mask) where mask is 0/255 uint8.
    """
    h, w = img.shape[:2]
    margin = max(3, min(h, w) // 20)
    rect = (margin, margin, w - 2 * margin, h - 2 * margin)

    mask = np.zeros((h, w), np.uint8)
    bgd_model = np.zeros((1, 65), np.float64)
    fgd_model = np.zeros((1, 65), np.float64)

    try:
        cv2.grabCut(img, mask, rect, bgd_model, fgd_model, 3, cv2.GC_INIT_WITH_RECT)
    except cv2.error:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 220, 255, cv2.THRESH_BINARY_INV)
        return img, binary

    fg_mask = np.where(
        (mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0
    ).astype(np.uint8)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel)
    fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)

    return img, fg_mask


# ---------------------------------------------------------------------------
# Paste product onto canvas (reused from v1)
# ---------------------------------------------------------------------------

def paste_product(
    canvas: np.ndarray,
    product_img: np.ndarray,
    product_mask: np.ndarray,
    x: int,
    y: int,
    target_w: int,
    target_h: int,
) -> tuple[np.ndarray, tuple[int, int, int, int] | None]:
    """Paste a masked product onto the canvas at (x, y) with given size.

    Returns (modified_canvas, (x, y, w, h) in COCO format) or None bbox if too small.
    """
    canvas_h, canvas_w = canvas.shape[:2]

    resized_img = cv2.resize(product_img, (target_w, target_h), interpolation=cv2.INTER_AREA)
    resized_mask = cv2.resize(product_mask, (target_w, target_h), interpolation=cv2.INTER_NEAREST)

    x1 = max(0, x)
    y1 = max(0, y)
    x2 = min(canvas_w, x + target_w)
    y2 = min(canvas_h, y + target_h)

    if x2 - x1 < 10 or y2 - y1 < 10:
        return canvas, None

    px1 = x1 - x
    py1 = y1 - y
    px2 = px1 + (x2 - x1)
    py2 = py1 + (y2 - y1)

    crop_img = resized_img[py1:py2, px1:px2]
    crop_mask = resized_mask[py1:py2, px1:px2]

    alpha = (crop_mask.astype(np.float32) / 255.0)[..., np.newaxis]
    roi = canvas[y1:y2, x1:x2].astype(np.float32)
    blended = roi * (1 - alpha) + crop_img.astype(np.float32) * alpha
    canvas[y1:y2, x1:x2] = blended.astype(np.uint8)

    bbox = (x1, y1, x2 - x1, y2 - y1)
    return canvas, bbox


# ---------------------------------------------------------------------------
# Replace-in-place: swap annotation bbox with a different angle
# ---------------------------------------------------------------------------

def replace_in_place(
    canvas: np.ndarray,
    bbox: list[int],
    product_img: np.ndarray,
    product_mask: np.ndarray,
) -> np.ndarray:
    """Replace bbox region with product cutout, keeping original background pixels.

    Scales product to fit WITHIN bbox preserving aspect ratio, centers it.
    Where the mask is background, original canvas pixels are preserved.
    """
    bx, by, bw, bh = bbox
    canvas_h, canvas_w = canvas.shape[:2]

    # Clamp bbox to canvas bounds
    bx2 = min(bx + bw, canvas_w)
    by2 = min(by + bh, canvas_h)
    bx = max(0, bx)
    by = max(0, by)
    bw = bx2 - bx
    bh = by2 - by

    if bw < 10 or bh < 10:
        return canvas

    prod_h, prod_w = product_img.shape[:2]

    # Scale to fit within bbox preserving aspect ratio
    scale = min(bw / prod_w, bh / prod_h)
    new_w = max(1, int(prod_w * scale))
    new_h = max(1, int(prod_h * scale))

    resized_img = cv2.resize(product_img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    resized_mask = cv2.resize(product_mask, (new_w, new_h), interpolation=cv2.INTER_NEAREST)

    # Center within bbox
    offset_x = (bw - new_w) // 2
    offset_y = (bh - new_h) // 2

    paste_x = bx + offset_x
    paste_y = by + offset_y

    # Clamp paste region to canvas
    px2 = min(paste_x + new_w, canvas_w)
    py2 = min(paste_y + new_h, canvas_h)
    paste_x = max(0, paste_x)
    paste_y = max(0, paste_y)
    cw = px2 - paste_x
    ch = py2 - paste_y

    if cw < 1 or ch < 1:
        return canvas

    # Crop resized product to match clamped region
    crop_img = resized_img[:ch, :cw]
    crop_mask = resized_mask[:ch, :cw]

    # Alpha blend: mask=foreground → product pixels, mask=background → keep canvas
    alpha = (crop_mask.astype(np.float32) / 255.0)[..., np.newaxis]
    roi = canvas[paste_y:py2, paste_x:px2].astype(np.float32)
    blended = roi * (1 - alpha) + crop_img.astype(np.float32) * alpha
    canvas[paste_y:py2, paste_x:px2] = blended.astype(np.uint8)

    return canvas


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def build_category_to_product_angles(
    annotations_path: Path,
    metadata_path: Path,
    individ_dir: Path,
) -> dict[int, dict[str, Path]]:
    """Map category_id -> {angle_name: image_path}."""
    with open(annotations_path) as f:
        coco = json.load(f)
    with open(metadata_path) as f:
        meta = json.load(f)

    cats = {c["id"]: c["name"] for c in coco["categories"]}
    name_to_cat = {name: cid for cid, name in cats.items()}
    code_to_name = {p["product_code"]: p["product_name"] for p in meta["products"]}

    cat_to_angles: dict[int, dict[str, Path]] = {}

    for product_dir in individ_dir.iterdir():
        if not product_dir.is_dir():
            continue
        product_code = product_dir.name
        product_name = code_to_name.get(product_code)
        if not product_name or product_name not in name_to_cat:
            continue

        cat_id = name_to_cat[product_name]
        angles = {}
        for p in sorted(product_dir.glob("*.jpg")):
            angles[p.stem] = p
        if angles:
            cat_to_angles[cat_id] = angles

    return cat_to_angles


def load_section_mapping(
    section_mapping_path: Path,
) -> tuple[dict[int, int], dict[int, set[int]]]:
    """Load section mapping.

    Returns:
        image_id_to_section: {image_id: section_id}
        section_to_cat_ids: {section_id: set of category_ids}
    """
    with open(section_mapping_path) as f:
        mapping = json.load(f)

    image_id_to_section = {}
    for img_id_str, info in mapping["image_sections"].items():
        image_id_to_section[int(img_id_str)] = info["section_id"]

    section_to_cat_ids = {}
    for sec_id_str, info in mapping["section_categories"].items():
        section_to_cat_ids[int(sec_id_str)] = set(info["category_ids"])

    return image_id_to_section, section_to_cat_ids


def build_section_sampling_weights(
    coco: dict,
    cat_to_cutouts: dict[int, list[tuple[np.ndarray, np.ndarray]]],
    section_to_cat_ids: dict[int, set[int]],
) -> dict[int, tuple[list[int], list[float]]]:
    """Build per-section sampling weights (inverse frequency, filtered by section)."""
    cat_counts = Counter(a["category_id"] for a in coco["annotations"])

    section_weights = {}
    for sec_id, allowed_cats in section_to_cat_ids.items():
        eligible = [cid for cid in cat_to_cutouts if cid in cat_counts and cid in allowed_cats]
        if not eligible:
            section_weights[sec_id] = ([], [])
            continue

        max_count = max(cat_counts[c] for c in eligible)
        weights = [max_count / max(cat_counts[c], 1) for c in eligible]
        total = sum(weights)
        weights = [w / total for w in weights]
        section_weights[sec_id] = (eligible, weights)

    return section_weights


# ---------------------------------------------------------------------------
# Main augmentation
# ---------------------------------------------------------------------------

def augment_dataset(
    project_dir: Path,
    num_augmented: int = 248,
    pastes_per_image: int = 8,
    replace_fraction: float = 0.4,
    seed: int = 42,
) -> None:
    """Generate augmented training images with section-aware paste + replace-in-place."""
    random.seed(seed)
    np.random.seed(seed)

    annotations_path = project_dir / "data" / "train" / "annotations.json"
    metadata_path = project_dir / "data" / "metadata.json"
    individ_dir = project_dir / "data" / "individ"
    images_dir = project_dir / "data" / "train" / "images"
    section_mapping_path = project_dir / "data" / "section_mapping.json"

    # Output directories
    aug_dir = project_dir / "data" / "train_augmented"
    aug_images_dir = aug_dir / "images"
    aug_images_dir.mkdir(parents=True, exist_ok=True)

    with open(annotations_path) as f:
        coco = json.load(f)

    # Build angle-aware category mapping
    cat_to_angles = build_category_to_product_angles(
        annotations_path, metadata_path, individ_dir
    )
    print(f"Categories with individual images: {len(cat_to_angles)}/{len(coco['categories'])}")

    # Load section mapping
    image_id_to_section, section_to_cat_ids = load_section_mapping(section_mapping_path)
    print(f"Section mapping loaded: {len(image_id_to_section)} images, {len(section_to_cat_ids)} sections")

    # Pre-extract foregrounds for ALL angles
    print("Extracting product foregrounds (all angles)...")
    # For random paste: flat list of cutouts per category (using front/main)
    cat_to_cutouts: dict[int, list[tuple[np.ndarray, np.ndarray]]] = {}
    # For replace-in-place: angle-keyed cutouts per category
    cat_to_angle_cutouts: dict[int, dict[str, tuple[np.ndarray, np.ndarray]]] = {}

    for cat_id, angles in cat_to_angles.items():
        angle_cutouts = {}
        flat_cutouts = []

        for angle_name, img_path in angles.items():
            img = cv2.imread(str(img_path))
            if img is None:
                continue
            img_fg, mask = extract_foreground(img)
            if mask.sum() < 500:
                continue
            angle_cutouts[angle_name] = (img_fg, mask)
            # For random paste, prefer front/main
            if angle_name in ("front", "main"):
                flat_cutouts.append((img_fg, mask))

        # If no front/main, use first two available
        if not flat_cutouts and angle_cutouts:
            flat_cutouts = list(angle_cutouts.values())[:2]

        if flat_cutouts:
            cat_to_cutouts[cat_id] = flat_cutouts
        if angle_cutouts:
            cat_to_angle_cutouts[cat_id] = angle_cutouts

    print(f"Categories with valid cutouts: {len(cat_to_cutouts)}")
    print(f"Categories with angle cutouts: {len(cat_to_angle_cutouts)}")

    # Count how many categories have alternative angles (not just front/main)
    cats_with_alt_angles = sum(
        1 for cat_id, angles in cat_to_angle_cutouts.items()
        if any(a not in ("front", "main") for a in angles)
    )
    print(f"Categories with alternative angles for replace-in-place: {cats_with_alt_angles}")

    # Build per-section sampling weights
    section_weights = build_section_sampling_weights(coco, cat_to_cutouts, section_to_cat_ids)
    for sec_id, (eligible, _) in section_weights.items():
        print(f"  Section {sec_id}: {len(eligible)} eligible categories for paste")

    # Bbox size distribution from annotations (for realistic sizing of random pastes)
    bbox_widths = [a["bbox"][2] for a in coco["annotations"]]
    bbox_heights = [a["bbox"][3] for a in coco["annotations"]]
    w_lo, w_hi = int(np.percentile(bbox_widths, 15)), int(np.percentile(bbox_widths, 85))
    h_lo, h_hi = int(np.percentile(bbox_heights, 15)), int(np.percentile(bbox_heights, 85))
    print(f"Paste size range: w=[{w_lo}, {w_hi}], h=[{h_lo}, {h_hi}]")

    # Collect source images
    source_images = sorted(
        p for p in images_dir.iterdir()
        if p.suffix.lower() in (".jpg", ".jpeg", ".png")
    )

    # Build annotations index by image_id
    anns_by_image = {}
    for ann in coco["annotations"]:
        anns_by_image.setdefault(ann["image_id"], []).append(ann)

    # Build image filename -> image_id lookup
    filename_to_id = {img["file_name"]: img["id"] for img in coco["images"]}

    # New annotations list = original + augmented
    new_annotations = list(coco["annotations"])
    new_images = list(coco["images"])
    next_ann_id = max(a["id"] for a in coco["annotations"]) + 1
    next_img_id = max(img["id"] for img in coco["images"]) + 1

    total_replaced = 0
    total_pasted = 0

    print(f"\nGenerating {num_augmented} augmented images "
          f"(replace_fraction={replace_fraction}, pastes={pastes_per_image})...")

    for aug_idx in range(num_augmented):
        # Pick a random source image
        src_path = random.choice(source_images)
        canvas = cv2.imread(str(src_path))
        if canvas is None:
            continue

        canvas_h, canvas_w = canvas.shape[:2]
        aug_filename = f"aug_{aug_idx:05d}.jpg"

        # Determine source image's section
        src_img_id = filename_to_id.get(src_path.name)
        section_id = image_id_to_section.get(src_img_id) if src_img_id else None

        # --- Replace-in-place ---
        # Copy all original annotations for this image (they'll be carried forward)
        src_anns = anns_by_image.get(src_img_id, []) if src_img_id else []
        img_annotations = []

        for ann in src_anns:
            cat_id = ann["category_id"]
            # Decide whether to replace this annotation
            if random.random() > replace_fraction:
                # Keep original annotation as-is
                img_annotations.append({
                    "id": next_ann_id,
                    "image_id": next_img_id,
                    "category_id": cat_id,
                    "bbox": list(ann["bbox"]),
                    "area": ann["area"],
                    "iscrowd": 0,
                })
                next_ann_id += 1
                continue

            # Check if this category has alternative angles
            angle_cutouts = cat_to_angle_cutouts.get(cat_id)
            if not angle_cutouts:
                # No reference images — keep original
                img_annotations.append({
                    "id": next_ann_id,
                    "image_id": next_img_id,
                    "category_id": cat_id,
                    "bbox": list(ann["bbox"]),
                    "area": ann["area"],
                    "iscrowd": 0,
                })
                next_ann_id += 1
                continue

            # Pick a non-front/main angle if available
            alt_angles = [a for a in angle_cutouts if a not in ("front", "main")]
            if not alt_angles:
                # Only front/main available — keep original
                img_annotations.append({
                    "id": next_ann_id,
                    "image_id": next_img_id,
                    "category_id": cat_id,
                    "bbox": list(ann["bbox"]),
                    "area": ann["area"],
                    "iscrowd": 0,
                })
                next_ann_id += 1
                continue

            # Replace with a random alternative angle
            angle = random.choice(alt_angles)
            prod_img, prod_mask = angle_cutouts[angle]
            canvas = replace_in_place(canvas, ann["bbox"], prod_img, prod_mask)
            total_replaced += 1

            # Annotation stays the same (same bbox, same category)
            img_annotations.append({
                "id": next_ann_id,
                "image_id": next_img_id,
                "category_id": cat_id,
                "bbox": list(ann["bbox"]),
                "area": ann["area"],
                "iscrowd": 0,
            })
            next_ann_id += 1

        # --- Section-aware random paste ---
        if section_id is not None and section_id in section_weights:
            eligible_cats, weights = section_weights[section_id]
        else:
            # Fallback: use all categories (shouldn't happen with valid section mapping)
            eligible_cats = list(cat_to_cutouts.keys())
            weights = [1.0 / len(eligible_cats)] * len(eligible_cats) if eligible_cats else []

        if eligible_cats:
            for _ in range(pastes_per_image):
                cat_id = random.choices(eligible_cats, weights=weights, k=1)[0]
                cutouts = cat_to_cutouts[cat_id]
                product_img, product_mask = random.choice(cutouts)

                # Sample target size preserving product aspect ratio
                prod_h, prod_w = product_img.shape[:2]
                aspect = prod_w / max(prod_h, 1)

                target_h = random.randint(h_lo, h_hi)
                target_w = max(20, int(target_h * aspect))
                target_w = min(target_w, w_hi)
                target_w = max(target_w, w_lo // 2)

                x = random.randint(0, max(1, canvas_w - target_w))
                y = random.randint(0, max(1, canvas_h - target_h))

                canvas, bbox = paste_product(
                    canvas, product_img, product_mask, x, y, target_w, target_h
                )
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
                total_pasted += 1

        # Save augmented image
        cv2.imwrite(str(aug_images_dir / aug_filename), canvas)

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

    # Symlink original images into augmented dir
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
    print(f"  Replace-in-place swaps: {total_replaced}")
    print(f"  Section-aware pastes: {total_pasted}")
    print(f"  Output: {aug_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Copy-paste augmentation v2: section-aware + replace-in-place"
    )
    parser.add_argument("--num-augmented", type=int, default=248,
                        help="Number of augmented images to generate (default: 248)")
    parser.add_argument("--pastes-per-image", type=int, default=0,
                        help="Products to paste per image (default: 0, disabled)")
    parser.add_argument("--replace-fraction", type=float, default=0.4,
                        help="Fraction of annotations to replace in-place (default: 0.4)")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    project_dir = Path(__file__).resolve().parent.parent

    augment_dataset(
        project_dir=project_dir,
        num_augmented=args.num_augmented,
        pastes_per_image=args.pastes_per_image,
        replace_fraction=args.replace_fraction,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
