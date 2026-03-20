"""
Build submission.zip for Challenge 3.

Downloads YOLOv8 weights if needed, packages run.py + weights at zip root.

Usage:
    python scripts/prepare_submission.py [--model-size s]
"""

import argparse
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

from ultralytics import YOLO


MAX_ZIP_SIZE_MB = 420


def download_weights(model_size: str, dest: Path) -> Path:
    """Download YOLOv8 weights if not already present."""
    weight_name = f"yolov8{model_size}.pt"
    weight_path = dest / weight_name

    if weight_path.exists():
        size_mb = weight_path.stat().st_size / (1024 * 1024)
        print(f"Weights already exist: {weight_path} ({size_mb:.1f} MB)")
        return weight_path

    print(f"Downloading yolov8{model_size} weights...")
    model = YOLO(f"yolov8{model_size}.pt")
    # ultralytics downloads to current dir or ~/.cache; find and copy
    downloaded = Path(f"yolov8{model_size}.pt")
    if downloaded.exists():
        shutil.copy2(downloaded, weight_path)
    else:
        # Check ultralytics default cache
        from ultralytics.utils import SETTINGS
        cache_dir = Path(SETTINGS.get("weights_dir", Path.home() / ".cache" / "ultralytics"))
        cached = cache_dir / weight_name
        if cached.exists():
            shutil.copy2(cached, weight_path)
        else:
            print(f"ERROR: Could not find downloaded weights", file=sys.stderr)
            sys.exit(1)

    size_mb = weight_path.stat().st_size / (1024 * 1024)
    print(f"Weights saved: {weight_path} ({size_mb:.1f} MB)")
    return weight_path


def build_zip(model_size: str) -> Path:
    """Create submission.zip with run.py and model weights at root level."""
    project_dir = Path(__file__).resolve().parent.parent
    submission_dir = project_dir / "submission"
    run_py = submission_dir / "run.py"
    weight_name = f"yolov8{model_size}.pt"

    if not run_py.exists():
        print(f"ERROR: run.py not found at {run_py}", file=sys.stderr)
        sys.exit(1)

    # Ensure weights are in submission dir
    weight_path = download_weights(model_size, submission_dir)

    # Create zip
    zip_path = project_dir / "submission.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(run_py, "run.py")
        zf.write(weight_path, weight_name)

    # Verify size
    zip_size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"\nSubmission zip: {zip_path} ({zip_size_mb:.1f} MB)")

    if zip_size_mb > MAX_ZIP_SIZE_MB:
        print(f"WARNING: Zip exceeds {MAX_ZIP_SIZE_MB} MB limit!", file=sys.stderr)
        sys.exit(1)

    # Verify structure
    print("\nZip contents:")
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            size_mb = info.file_size / (1024 * 1024)
            print(f"  {info.filename} ({size_mb:.1f} MB)")

    # Verify run.py has no banned imports
    run_content = run_py.read_text()
    if "import os" in run_content:
        print("WARNING: run.py contains 'import os' which is banned in sandbox!", file=sys.stderr)

    print(f"\nSubmission ready: {zip_path}")
    return zip_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Challenge 3 submission zip")
    parser.add_argument("--model-size", type=str, default="s", choices=["n", "s", "m", "l", "x"])
    args = parser.parse_args()

    build_zip(args.model_size)


if __name__ == "__main__":
    main()
