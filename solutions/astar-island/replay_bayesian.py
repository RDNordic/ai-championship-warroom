"""Wrapper to run Bayesian replay validation."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from experimental.replay import main

main()
