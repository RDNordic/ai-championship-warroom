"""Wrapper to run the experimental Bayesian pipeline live."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from experimental.runner import main

main()
