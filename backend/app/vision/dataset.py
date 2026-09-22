"""Dataset helpers for product-vision training."""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from torch.utils.data import Dataset

from app.vision.config import IMAGE_SIZE, VISION_CLASSES
from app.vision.preprocessing import transform_eval, transform_train


class ProductImageFolder(Dataset):
    """Flat ImageFolder-style dataset over class subdirectories."""

    def __init__(self, root: Path, train: bool = False, image_size: int = IMAGE_SIZE) -> None:
        self.root = Path(root)
        self.classes = list(VISION_CLASSES)
        self.class_to_idx = {name: idx for idx, name in enumerate(self.classes)}
        self.train = train
        self.image_size = image_size
        self.samples: list[tuple[Path, int]] = []
        for class_name in self.classes:
            folder = self.root / class_name
            if not folder.is_dir():
                continue
            for path in sorted(folder.iterdir()):
                if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                    self.samples.append((path, self.class_to_idx[class_name]))
        if not self.samples:
            raise FileNotFoundError(f"No images found under {self.root}")

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int):
        path, label = self.samples[index]
        image = Image.open(path).convert("RGB")
        tensor = transform_train(image, self.image_size) if self.train else transform_eval(image, self.image_size)
        return tensor, label


def count_images_per_class(root: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    root = Path(root)
    for class_name in VISION_CLASSES:
        folder = root / class_name
        if not folder.is_dir():
            counts[class_name] = 0
            continue
        counts[class_name] = sum(
            1 for path in folder.iterdir() if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
        )
    return counts
