"""Build a synthetic geometric product-category dataset for CNN training.

Source: programmatically generated with Pillow (not real product photos).
License: original NeoCube training asset; no third-party image copyright.
Purpose: train/evaluate the ProductVisionCNN architecture with distinct
visual class signatures aligned to NeoCube catalog categories.
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

from PIL import Image, ImageDraw

from app.vision.config import VISION_CLASSES, vision_dataset_dir

# Distinct visual recipes per class so the CNN can learn real features.
_CLASS_STYLES: dict[str, dict] = {
    "steel_metals": {"bg": (70, 80, 90), "fg": (180, 190, 200), "shape": "bar"},
    "electronics": {"bg": (20, 30, 60), "fg": (40, 180, 255), "shape": "chip"},
    "packaging": {"bg": (240, 230, 210), "fg": (160, 100, 40), "shape": "box"},
    "textiles": {"bg": (230, 220, 240), "fg": (140, 70, 160), "shape": "wave"},
    "industrial_components": {"bg": (50, 50, 50), "fg": (220, 140, 40), "shape": "gear"},
    "raw_materials": {"bg": (90, 60, 40), "fg": (200, 160, 100), "shape": "grain"},
}


def _draw_shape(draw: ImageDraw.ImageDraw, style: dict, rng: random.Random, size: int) -> None:
    shape = style["shape"]
    fg = style["fg"]
    margin = rng.randint(8, 18)
    if shape == "bar":
        for i in range(4):
            y = margin + i * ((size - 2 * margin) // 4)
            draw.rectangle([margin, y, size - margin, y + 10], fill=fg)
    elif shape == "chip":
        draw.rectangle([margin, margin, size - margin, size - margin], outline=fg, width=4)
        for _ in range(8):
            x = rng.randint(margin + 5, size - margin - 5)
            y = rng.randint(margin + 5, size - margin - 5)
            draw.rectangle([x, y, x + 6, y + 6], fill=fg)
    elif shape == "box":
        draw.rectangle([margin, margin, size - margin, size - margin], outline=fg, width=5)
        draw.line([margin, margin + 12, size - margin, margin + 12], fill=fg, width=3)
    elif shape == "wave":
        points = []
        for x in range(margin, size - margin, 4):
            y = size // 2 + int(12 * __import__("math").sin(x / 8 + rng.random()))
            points.append((x, y))
        if len(points) > 1:
            draw.line(points, fill=fg, width=4)
    elif shape == "gear":
        cx = cy = size // 2
        r = size // 3
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=fg, width=4)
        draw.ellipse([cx - r // 3, cy - r // 3, cx + r // 3, cy + r // 3], fill=fg)
    else:  # grain
        for _ in range(40):
            x = rng.randint(margin, size - margin)
            y = rng.randint(margin, size - margin)
            draw.ellipse([x, y, x + 4, y + 4], fill=fg)


def _make_image(class_name: str, seed: int, size: int = 128) -> Image.Image:
    rng = random.Random(seed)
    style = _CLASS_STYLES[class_name]
    bg = tuple(max(0, min(255, c + rng.randint(-15, 15))) for c in style["bg"])
    image = Image.new("RGB", (size, size), bg)
    draw = ImageDraw.Draw(image)
    _draw_shape(draw, style, rng, size)
    return image


def build_dataset(output: Path, per_class: int = 40, seed: int = 42) -> dict:
    rng = random.Random(seed)
    splits = {
        "train": int(per_class * 0.7),
        "validation": int(per_class * 0.15),
        "test": per_class - int(per_class * 0.7) - int(per_class * 0.15),
    }
    counts: dict[str, dict[str, int]] = {}
    for split, n in splits.items():
        counts[split] = {}
        for class_name in VISION_CLASSES:
            folder = output / split / class_name
            folder.mkdir(parents=True, exist_ok=True)
            for i in range(n):
                img_seed = rng.randint(0, 10_000_000)
                image = _make_image(class_name, img_seed)
                image.save(folder / f"{class_name}_{i:03d}.png")
            counts[split][class_name] = n
    return {"output": str(output.resolve()), "counts": counts, "source": "synthetic_pillow_geometric_v1"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build synthetic NeoCube vision dataset")
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--per-class", type=int, default=40)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    output = Path(args.output) if args.output else vision_dataset_dir()
    summary = build_dataset(output, per_class=args.per_class, seed=args.seed)
    print(summary)


if __name__ == "__main__":
    main()
