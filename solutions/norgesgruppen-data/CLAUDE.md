# Challenge 3 — Object Detection (NorgesGruppen)

## Sandbox Constraints
- Python 3.11, NVIDIA L4 24GB, 300s timeout, no network, no `import os`
- Max 420MB uncompressed zip, max 3 weight files
- Entry point: `python run.py --input /data/images --output /output/predictions.json`

## Sandbox Packages (exact versions)
PyTorch 2.6.0+cu124, torchvision 0.21.0+cu124, ultralytics 8.1.0,
onnxruntime-gpu 1.20.0, opencv-python-headless 4.9.0.80, albumentations 1.3.1,
Pillow 10.2.0, numpy 1.26.4, scipy 1.12.0, scikit-learn 1.4.0,
pycocotools 2.0.7, ensemble-boxes 1.0.9, timm 0.9.12, supervision 0.18.0,
safetensors 0.4.2

## Scoring
```
Score = 0.7 × detection_mAP@0.5 + 0.3 × classification_mAP@0.5
```
Detection-only baseline (all `category_id: 0`) caps at 0.70.

## Data Facts (verified)
- 248 training images (~2000×1500px), 22731 annotations
- 356 categories (IDs 0-355), ID 355 = `unknown_product`
- 327 reference products × 7 angles in `individual_samples/`

## torch.load Compatibility
ultralytics 8.1.0 calls `torch.load()` without `weights_only=False`.
torch 2.6.0 defaults `weights_only=True`. Must monkey-patch in run.py:
```python
import functools, torch
torch.load = functools.partial(torch.load, weights_only=False)
```

## Local Eval
```bash
uv run python submission/run.py --input data/train/images --output /tmp/predictions.json
uv run python scripts/evaluate.py --predictions /tmp/predictions.json
```

## Submission
```bash
uv run python scripts/prepare_submission.py --model-size s
# Upload submission.zip to app.ainm.no
```
