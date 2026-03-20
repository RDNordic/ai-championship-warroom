"""
Build submission.zip for Challenge 3.

Packages run.py + best.pt weights at zip root.

Usage:
    python scripts/prepare_submission.py
"""

import sys
import zipfile
from pathlib import Path


MAX_ZIP_SIZE_MB = 420
BANNED_IMPORTS = ["import os", "import subprocess", "import socket", "import sys"]


def build_zip() -> Path:
    """Create submission.zip with run.py and best.pt at root level."""
    project_dir = Path(__file__).resolve().parent.parent
    submission_dir = project_dir / "submission"
    run_py = submission_dir / "run.py"
    weight_path = submission_dir / "best.pt"

    if not run_py.exists():
        print(f"ERROR: run.py not found at {run_py}", file=sys.stderr)
        sys.exit(1)

    if not weight_path.exists():
        print(f"ERROR: best.pt not found at {weight_path}", file=sys.stderr)
        sys.exit(1)

    # Create zip
    zip_path = project_dir / "submission.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(run_py, "run.py")
        zf.write(weight_path, "best.pt")

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
    for banned in BANNED_IMPORTS:
        if banned in run_content:
            print(f"WARNING: run.py contains '{banned}' which is banned in sandbox!", file=sys.stderr)

    print(f"\nSubmission ready: {zip_path}")
    return zip_path


def main() -> None:
    build_zip()


if __name__ == "__main__":
    main()
