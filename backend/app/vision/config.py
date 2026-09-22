"""Configuration for the NeoCube product-vision CNN."""

from __future__ import annotations

from pathlib import Path

from app.config import settings

# Folder-safe class ids mapped to NeoCube catalog categories used for training.
VISION_CLASSES: tuple[str, ...] = (
    "steel_metals",
    "electronics",
    "packaging",
    "textiles",
    "industrial_components",
    "raw_materials",
)

CLASS_DISPLAY_NAMES: dict[str, str] = {
    "steel_metals": "Steel & Metals",
    "electronics": "Electronics",
    "packaging": "Packaging",
    "textiles": "Textiles",
    "industrial_components": "Industrial Components",
    "raw_materials": "Raw Materials",
}

IMAGE_SIZE = 96
EMBEDDING_DIM = 128
MODEL_VERSION = "product_vision_cnn_v1"
MODEL_FILENAME = "product_vision_cnn_v1.pth"
METADATA_FILENAME = "product_vision_cnn_v1.meta.json"

DEFAULT_BATCH_SIZE = 32
DEFAULT_EPOCHS = 8
DEFAULT_LR = 1e-3
DEFAULT_SEED = 42
MIN_VISUAL_SIMILARITY = 0.35


def vision_model_dir() -> Path:
    path = Path(settings.vision_model_dir)
    if not path.is_absolute():
        path = Path.cwd() / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def vision_dataset_dir() -> Path:
    path = Path(settings.vision_dataset_dir)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def model_weights_path() -> Path:
    return vision_model_dir() / MODEL_FILENAME


def model_metadata_path() -> Path:
    return vision_model_dir() / METADATA_FILENAME
