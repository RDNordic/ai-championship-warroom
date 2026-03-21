# Dataset Statistics — NorgesGruppen Object Detection

## Training Images

| Metric | Value |
|--------|-------|
| Total images | 248 |
| Total annotations | 22,731 |
| Categories | 356 (IDs 0–355) |
| Reference products | 327 × 7 angles |

## Image Dimensions

### Summary

| Stat | Width | Height |
|------|-------|--------|
| Min | 481 | 399 |
| Max | 5,712 | 4,624 |
| Mean | 2,800 | 2,596 |

### Megapixels

| Stat | Value |
|------|-------|
| Min | 0.25 MP |
| Max | 24.47 MP |
| Median | 9.14 MP |
| Mean | 8.05 MP |

### Aspect Ratio (W/H)

| Stat | Value |
|------|-------|
| Min | 0.392 (tall/narrow) |
| Max | 2.222 (wide) |
| Mean | 1.113 |

### Orientation

| Type | Count | % |
|------|-------|---|
| Landscape (W > H) | 146 | 58.9% |
| Portrait (H > W) | 101 | 40.7% |
| Square | 1 | 0.4% |

### Size Buckets (by max dimension)

| Bucket | Count | % |
|--------|-------|---|
| < 1,000 px | 9 | 3.6% |
| 1,000–1,999 px | 52 | 21.0% |
| 2,000–3,999 px | 62 | 25.0% |
| >= 4,000 px | 125 | 50.4% |

### Most Common Resolutions

| W × H | Count | % | Ratio |
|--------|-------|---|-------|
| 4032 × 3024 | 59 | 23.8% | 4:3 |
| 3024 × 4032 | 26 | 10.5% | 3:4 |
| 4000 × 3000 | 17 | 6.9% | 4:3 |
| 960 × 1280 | 6 | 2.4% | 3:4 |
| 3000 × 4000 | 5 | 2.0% | 3:4 |
| 3264 × 2448 | 5 | 2.0% | 4:3 |
| 2000 × 1500 | 4 | 1.6% | 4:3 |
| 1440 × 1920 | 4 | 1.6% | 3:4 |
| 1920 × 1440 | 4 | 1.6% | 4:3 |

114 unique resolutions total. The remaining 105 sizes each appear only 1–3 times.

## Store Sections (Clustering Analysis)

Images and categories were clustered into 4 store sections using hierarchical clustering (Ward linkage, Jaccard distance on image–category co-occurrence).

### Section Overview

| Section | Images | Categories | Annotations | Avg Ann/Image |
|---------|--------|------------|-------------|---------------|
| Knekkebrød | 90 (36.3%) | 120 | 10,551 (46.4%) | 117.2 |
| Frokost | 82 (33.1%) | 67 | 5,344 (23.5%) | 65.2 |
| Varmedrikker | 47 (19.0%) | 126 | 4,976 (21.9%) | 105.9 |
| Egg | 29 (11.7%) | 57 | 1,860 (8.2%) | 64.1 |

### Key Observations

- **Category exclusivity is high:** 343 of 356 categories (96.3%) appear in only one section. Only 13 categories span multiple sections.
- **Multi-section categories** are mostly cereals/müsli that appear in both Knekkebrød and Frokost (e.g., Nesquik, Müsli Frukt, Cheerios, granola bars). `unknown_product` (ID 355) appears in 3 sections.
- **Knekkebrød is the densest section** — 117 annotations per image on average, nearly 2× more than Frokost or Egg. These shelves are packed tightly.
- **Varmedrikker has the most categories (126)** despite having only 47 images — high category diversity per image.
- **Egg is the smallest section** — only 29 images and 57 categories, with 64 annotations per image.

### Section Implications for Training

- **Augmentation balance:** Copy-paste augmentation should oversample Egg images (only 29) to prevent the model from under-learning that section.
- **Section-aware validation:** Splitting train/val by section rather than randomly could reveal whether the model generalizes across shelf types.
- **Classification refinement:** Since 96% of categories are section-exclusive, knowing the section of a detected product dramatically narrows the classification candidates. A two-stage approach (detect → classify within section) could improve classification mAP.

Source: `data/section_mapping.json`

## Training Implications

- **50% of images are 4000+ px** — YOLO's `imgsz=1280` downscales these 3×+, losing small product detail. Consider `imgsz=1600` or `imgsz=1920` if VRAM allows.
- **High resolution variance** (0.25–24.5 MP) — the model must handle a ~100× range in pixel count. Mosaic augmentation helps here.
- **Mixed orientation** (59% landscape / 41% portrait) — no dominant orientation, so no special handling needed.
- **4:3 dominates** — 76% of the top resolutions are 4:3 or 3:4. A few outliers have extreme aspect ratios (0.39–2.22), which will be heavily padded at inference.
