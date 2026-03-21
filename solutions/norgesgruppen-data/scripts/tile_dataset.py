"""
Tile training images into fixed-size crops with corresponding COCO annotations.

Slices large images into overlapping tiles of `tile_size x tile_size`,
clips bounding boxes to tile boundaries, filters fragments, and outputs
a new COCO dataset ready for YOLO training.

Usage:
    python scripts/tile_dataset.py [--tile-size 1280] [--overlap 0.2] [--min-area-ratio 0.3]
    python scripts/tile_dataset.py --augmented  # tile the augmented dataset instead
"""

import argparse
import json
import shutil
from pathlib import Path

import cv2
import numpy as np


def compute_tile_grid(img_w: int, img_h: int, tile_size: int, overlap: float):
    """Compute tile origins (x, y) for an image.

    Last row/column tiles are shifted backward so they end at the image edge,
    ensuring all tiles are exactly tile_size x tile_size.

    Returns list of (x_start, y_start) tuples.
    """
    stride = int(tile_size * (1 - overlap))

    if img_w <= tile_size and img_h <= tile_size:
        # Image fits in a single tile — no tiling needed
        return None

    xs = []
    x = 0
    while x + tile_size < img_w:
        xs.append(x)
        x += stride
    # Last tile snaps to right edge
    xs.append(max(0, img_w - tile_size))
    # Deduplicate (can happen if image is barely larger than tile_size)
    xs = sorted(set(xs))

    ys = []
    y = 0
    while y + tile_size < img_h:
        ys.append(y)
        y += stride
    ys.append(max(0, img_h - tile_size))
    ys = sorted(set(ys))

    return [(x, y) for y in ys for x in xs]


def clip_annotation_to_tile(
    ann: dict,
    tx: int,
    ty: int,
    tw: int,
    th: int,
    min_area_ratio: float,
) -> dict | None:
    """Clip a COCO annotation bbox to a tile, return new annotation or None.

    Args:
        ann: COCO annotation dict with 'bbox' [x, y, w, h] (top-left).
        tx, ty: Tile origin in full-image coordinates.
        tw, th: Tile width and height.
        min_area_ratio: Minimum fraction of original box area that must be
            visible in the tile. Boxes below this are fragments and are dropped.

    Returns:
        New annotation dict with tile-local coordinates, or None if dropped.
    """
    bx, by, bw, bh = ann["bbox"]
    box_x1, box_y1 = bx, by
    box_x2, box_y2 = bx + bw, by + bh

    tile_x1, tile_y1 = tx, ty
    tile_x2, tile_y2 = tx + tw, ty + th

    # No overlap check
    if box_x2 <= tile_x1 or box_x1 >= tile_x2:
        return None
    if box_y2 <= tile_y1 or box_y1 >= tile_y2:
        return None

    # Clip to tile boundaries
    clipped_x1 = max(box_x1, tile_x1)
    clipped_y1 = max(box_y1, tile_y1)
    clipped_x2 = min(box_x2, tile_x2)
    clipped_y2 = min(box_y2, tile_y2)

    clipped_w = clipped_x2 - clipped_x1
    clipped_h = clipped_y2 - clipped_y1

    if clipped_w <= 0 or clipped_h <= 0:
        return None

    # Area ratio filter — drop fragments
    original_area = bw * bh
    if original_area <= 0:
        return None
    clipped_area = clipped_w * clipped_h
    if clipped_area / original_area < min_area_ratio:
        return None

    # Remap to tile-local coordinates
    local_x = clipped_x1 - tx
    local_y = clipped_y1 - ty

    return {
        "category_id": ann["category_id"],
        "bbox": [
            round(local_x, 2),
            round(local_y, 2),
            round(clipped_w, 2),
            round(clipped_h, 2),
        ],
    }


def tile_dataset(
    annotations_path: Path,
    images_dir: Path,
    output_dir: Path,
    tile_size: int = 1280,
    overlap: float = 0.2,
    min_area_ratio: float = 0.3,
    max_empty_fraction: float = 0.3,
    seed: int = 42,
) -> None:
    """Tile a COCO dataset into fixed-size crops.

    Args:
        annotations_path: Path to COCO annotations.json.
        images_dir: Directory containing source images.
        output_dir: Output directory for tiled images and annotations.
        tile_size: Tile width and height in pixels.
        overlap: Fractional overlap between adjacent tiles (0-1).
        min_area_ratio: Drop annotations with less than this fraction visible.
        max_empty_fraction: Keep at most this fraction of empty tiles (hard negatives).
        seed: Random seed for sampling empty tiles.
    """
    with open(annotations_path) as f:
        coco = json.load(f)

    images_by_id = {img["id"]: img for img in coco["images"]}

    # Group annotations by image_id
    anns_by_image: dict[int, list] = {}
    for ann in coco["annotations"]:
        anns_by_image.setdefault(ann["image_id"], []).append(ann)

    out_images_dir = output_dir / "images"
    out_images_dir.mkdir(parents=True, exist_ok=True)

    new_images = []
    new_annotations = []
    ann_id_counter = 1
    img_id_counter = 1

    stats = {
        "images_processed": 0,
        "images_copied_untiled": 0,
        "tiles_created": 0,
        "tiles_with_annotations": 0,
        "tiles_empty": 0,
        "tiles_empty_kept": 0,
        "annotations_original": len(coco["annotations"]),
        "annotations_tiled": 0,
        "annotations_dropped_fragment": 0,
    }

    rng = np.random.RandomState(seed)

    for img_info in coco["images"]:
        img_path = images_dir / img_info["file_name"]
        if not img_path.exists():
            continue

        img_w = img_info["width"]
        img_h = img_info["height"]
        original_id = img_info["id"]
        image_anns = anns_by_image.get(original_id, [])

        stats["images_processed"] += 1

        tile_grid = compute_tile_grid(img_w, img_h, tile_size, overlap)

        if tile_grid is None:
            # Image fits in one tile — copy as-is
            stem = Path(img_info["file_name"]).stem
            ext = Path(img_info["file_name"]).suffix
            out_name = f"{stem}_t0{ext}"
            out_path = out_images_dir / out_name

            # Read and write (not symlink, for portability)
            img = cv2.imread(str(img_path))
            cv2.imwrite(str(out_path), img)

            new_img_id = img_id_counter
            img_id_counter += 1

            new_images.append({
                "id": new_img_id,
                "file_name": out_name,
                "width": img_w,
                "height": img_h,
            })

            for ann in image_anns:
                new_annotations.append({
                    "id": ann_id_counter,
                    "image_id": new_img_id,
                    "category_id": ann["category_id"],
                    "bbox": ann["bbox"],
                    "area": ann.get("area", ann["bbox"][2] * ann["bbox"][3]),
                    "iscrowd": ann.get("iscrowd", 0),
                })
                ann_id_counter += 1
                stats["annotations_tiled"] += 1

            stats["images_copied_untiled"] += 1
            continue

        # Read image once for all tiles
        img = cv2.imread(str(img_path))
        if img is None:
            print(f"WARNING: Could not read {img_path}")
            continue

        stem = Path(img_info["file_name"]).stem
        ext = Path(img_info["file_name"]).suffix

        # Collect empty tiles to subsample later
        empty_tiles = []
        annotated_tiles = []

        for tile_idx, (tx, ty) in enumerate(tile_grid):
            tw = min(tile_size, img_w - tx)
            th = min(tile_size, img_h - ty)

            # Clip annotations to this tile
            tile_anns = []
            for ann in image_anns:
                clipped = clip_annotation_to_tile(ann, tx, ty, tw, th, min_area_ratio)
                if clipped is not None:
                    tile_anns.append(clipped)
                elif ann["bbox"][0] + ann["bbox"][2] > tx and ann["bbox"][0] < tx + tw and \
                     ann["bbox"][1] + ann["bbox"][3] > ty and ann["bbox"][1] < ty + th:
                    stats["annotations_dropped_fragment"] += 1

            tile_data = {
                "tile_idx": tile_idx,
                "tx": tx, "ty": ty, "tw": tw, "th": th,
                "anns": tile_anns,
            }

            if tile_anns:
                annotated_tiles.append(tile_data)
            else:
                empty_tiles.append(tile_data)

        # Subsample empty tiles
        if annotated_tiles and empty_tiles:
            max_empty = max(1, int(len(annotated_tiles) * max_empty_fraction))
            if len(empty_tiles) > max_empty:
                rng.shuffle(empty_tiles)
                empty_tiles = empty_tiles[:max_empty]
                stats["tiles_empty_kept"] += len(empty_tiles)
            else:
                stats["tiles_empty_kept"] += len(empty_tiles)
        elif empty_tiles:
            # All tiles empty (no annotations for this image) — keep 1
            empty_tiles = empty_tiles[:1]
            stats["tiles_empty_kept"] += 1

        all_tiles = annotated_tiles + empty_tiles

        for tile_data in all_tiles:
            tile_idx = tile_data["tile_idx"]
            tx, ty = tile_data["tx"], tile_data["ty"]
            tw, th = tile_data["tw"], tile_data["th"]
            tile_anns = tile_data["anns"]

            # Crop tile
            tile_img = img[ty:ty + th, tx:tx + tw]

            out_name = f"{stem}_t{tile_idx}{ext}"
            out_path = out_images_dir / out_name
            cv2.imwrite(str(out_path), tile_img)

            new_img_id = img_id_counter
            img_id_counter += 1

            new_images.append({
                "id": new_img_id,
                "file_name": out_name,
                "width": tw,
                "height": th,
            })

            for clipped_ann in tile_anns:
                bx, by, bw, bh = clipped_ann["bbox"]
                new_annotations.append({
                    "id": ann_id_counter,
                    "image_id": new_img_id,
                    "category_id": clipped_ann["category_id"],
                    "bbox": [bx, by, bw, bh],
                    "area": round(bw * bh, 2),
                    "iscrowd": 0,
                })
                ann_id_counter += 1
                stats["annotations_tiled"] += 1

            stats["tiles_created"] += 1
            if tile_anns:
                stats["tiles_with_annotations"] += 1
            else:
                stats["tiles_empty"] += 1

    # Write output annotations
    out_coco = {
        "images": new_images,
        "annotations": new_annotations,
        "categories": coco["categories"],
    }

    out_ann_path = output_dir / "annotations.json"
    with open(out_ann_path, "w") as f:
        json.dump(out_coco, f)

    print(f"\n{'='*50}")
    print("Tiling complete")
    print(f"{'='*50}")
    print(f"Source images processed:     {stats['images_processed']}")
    print(f"  Copied untiled (small):    {stats['images_copied_untiled']}")
    print(f"  Tiles created:             {stats['tiles_created']}")
    print(f"    With annotations:        {stats['tiles_with_annotations']}")
    print(f"    Empty (hard negatives):  {stats['tiles_empty']} (kept {stats['tiles_empty_kept']})")
    print(f"Annotations original:        {stats['annotations_original']}")
    print(f"Annotations in tiles:        {stats['annotations_tiled']}")
    print(f"Annotations dropped (frag):  {stats['annotations_dropped_fragment']}")
    print(f"\nOutput: {output_dir}")
    print(f"  Images:      {out_images_dir} ({len(new_images)} files)")
    print(f"  Annotations: {out_ann_path}")


def main():
    parser = argparse.ArgumentParser(description="Tile training images for SAHI-style training")
    parser.add_argument("--tile-size", type=int, default=1280,
                        help="Tile size in pixels (default: 1280)")
    parser.add_argument("--overlap", type=float, default=0.2,
                        help="Fractional overlap between tiles (default: 0.2)")
    parser.add_argument("--min-area-ratio", type=float, default=0.3,
                        help="Min visible area fraction to keep a bbox (default: 0.3)")
    parser.add_argument("--max-empty-fraction", type=float, default=0.3,
                        help="Max ratio of empty tiles to annotated tiles (default: 0.3)")
    parser.add_argument("--augmented", action="store_true",
                        help="Tile the augmented dataset instead of original")
    args = parser.parse_args()

    project_dir = Path(__file__).resolve().parent.parent

    if args.augmented:
        annotations_path = project_dir / "data" / "train_augmented" / "annotations.json"
        images_dir = project_dir / "data" / "train_augmented" / "images"
        output_dir = project_dir / "data" / "train_tiled_augmented"
    else:
        annotations_path = project_dir / "data" / "train" / "annotations.json"
        images_dir = project_dir / "data" / "train" / "images"
        output_dir = project_dir / "data" / "train_tiled"

    if not annotations_path.exists():
        print(f"ERROR: annotations not found at {annotations_path}")
        raise SystemExit(1)

    tile_dataset(
        annotations_path=annotations_path,
        images_dir=images_dir,
        output_dir=output_dir,
        tile_size=args.tile_size,
        overlap=args.overlap,
        min_area_ratio=args.min_area_ratio,
        max_empty_fraction=args.max_empty_fraction,
    )


if __name__ == "__main__":
    main()
