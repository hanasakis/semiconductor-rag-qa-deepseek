"""Download helper for the UCI SECOM dataset.

The SECOM dataset must be downloaded manually from the UCI ML Repository
due to license and access terms. This module checks for data and prints
instructions when the dataset is not found.
"""

import sys
from pathlib import Path

SECOM_URL = "https://archive.ics.uci.edu/dataset/179/secom"
SECOM_FILES = ["secom.data", "secom_labels.data", "secom.names"]
RAW_DIR = Path("data/raw")


def is_downloaded() -> bool:
    """Check whether all SECOM files are present in data/raw/."""
    return all((RAW_DIR / f).exists() for f in SECOM_FILES)


def print_instructions():
    """Print step-by-step download instructions for the user."""
    print("=" * 60)
    print("  SECOM Dataset — Download Required")
    print("=" * 60)
    print()
    print(f"  URL:  {SECOM_URL}")
    print()
    print("  Steps:")
    print(f"  1. Open the URL above in a browser.")
    print(f"  2. Click 'Download' and get the .zip file.")
    print(f"  3. Extract the zip contents.")
    print(f"  4. Copy these files into {RAW_DIR.resolve()}/:")
    for f in SECOM_FILES:
        print(f"       - {f}")
    print()
    print("  After placing the files, re-run the pipeline.")
    print("=" * 60)


def main():
    """Entry point: check data and print instructions if missing."""
    if is_downloaded():
        print("All SECOM files found in data/raw/.")
        return 0
    else:
        print_instructions()
        return 1


if __name__ == "__main__":
    sys.exit(main())
