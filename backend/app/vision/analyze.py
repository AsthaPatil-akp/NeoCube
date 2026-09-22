"""Pandas/NumPy analysis of the product-vision dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from PIL import Image

from app.vision.config import VISION_CLASSES, vision_dataset_dir


def analyze(dataset_root: Path | None = None) -> dict:
    root = Path(dataset_root) if dataset_root else vision_dataset_dir()
    rows: list[dict] = []
    invalid: list[dict] = []
    for split in ("train", "validation", "test"):
        for class_name in VISION_CLASSES:
            folder = root / split / class_name
            if not folder.is_dir():
                continue
            for path in sorted(folder.iterdir()):
                if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                    continue
                try:
                    with Image.open(path) as image:
                        image.load()
                        width, height = image.size
                    rows.append(
                        {
                            "split": split,
                            "class": class_name,
                            "path": str(path),
                            "width": width,
                            "height": height,
                        }
                    )
                except OSError:
                    invalid.append({"split": split, "class": class_name, "path": str(path)})

    frame = pd.DataFrame(rows)
    summary = {
        "dataset_root": str(root.resolve()),
        "total_images": int(len(frame)),
        "invalid_files": invalid,
        "images_per_class": frame.groupby("class").size().to_dict() if not frame.empty else {},
        "images_per_split": frame.groupby("split").size().to_dict() if not frame.empty else {},
        "split_class_counts": (
            frame.groupby(["split", "class"]).size().unstack(fill_value=0).to_dict() if not frame.empty else {}
        ),
        "mean_width": float(frame["width"].mean()) if not frame.empty else 0.0,
        "mean_height": float(frame["height"].mean()) if not frame.empty else 0.0,
        "class_imbalance_ratio": (
            float(frame.groupby("class").size().max() / max(frame.groupby("class").size().min(), 1))
            if not frame.empty
            else 0.0
        ),
    }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze NeoCube vision dataset")
    parser.add_argument("--dataset", type=str, default=None)
    args = parser.parse_args()
    print(json.dumps(analyze(Path(args.dataset) if args.dataset else None), indent=2))


if __name__ == "__main__":
    main()
