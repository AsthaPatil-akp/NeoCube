"""Model artifact load/save for the product-vision CNN."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import torch

from app.vision.config import (
    EMBEDDING_DIM,
    IMAGE_SIZE,
    METADATA_FILENAME,
    MODEL_FILENAME,
    MODEL_VERSION,
    VISION_CLASSES,
    model_metadata_path,
    model_weights_path,
    vision_model_dir,
)
from app.vision.model import ProductVisionCNN

logger = logging.getLogger("neocube")


@dataclass
class VisionModelBundle:
    model: ProductVisionCNN
    metadata: dict
    device: torch.device

    @property
    def version(self) -> str:
        return str(self.metadata.get("model_version", MODEL_VERSION))

    @property
    def embedding_dim(self) -> int:
        return int(self.metadata.get("embedding_dim", EMBEDDING_DIM))

    @property
    def image_size(self) -> int:
        return int(self.metadata.get("image_size", IMAGE_SIZE))

    @property
    def class_names(self) -> list[str]:
        names = self.metadata.get("class_names") or list(VISION_CLASSES)
        return list(names)


def save_model(
    model: ProductVisionCNN,
    metadata: dict,
    weights_path: Path | None = None,
    meta_path: Path | None = None,
) -> None:
    weights_path = weights_path or model_weights_path()
    meta_path = meta_path or model_metadata_path()
    weights_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"state_dict": model.state_dict(), "metadata": metadata}, weights_path)
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    clear_vision_model_cache()


def _load_from_paths(weights_path: Path, meta_path: Path) -> VisionModelBundle | None:
    if not weights_path.exists():
        logger.warning("Vision model weights missing at %s", weights_path)
        return None
    metadata: dict
    if meta_path.exists():
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    else:
        checkpoint_probe = torch.load(weights_path, map_location="cpu")
        metadata = checkpoint_probe.get("metadata") or {} if isinstance(checkpoint_probe, dict) else {}
    class_names = list(metadata.get("class_names") or VISION_CLASSES)
    embedding_dim = int(metadata.get("embedding_dim", EMBEDDING_DIM))
    model = ProductVisionCNN(num_classes=len(class_names), embedding_dim=embedding_dim)
    checkpoint = torch.load(weights_path, map_location="cpu")
    if isinstance(checkpoint, dict) and "state_dict" in checkpoint:
        state = checkpoint["state_dict"]
        if not metadata and checkpoint.get("metadata"):
            metadata = checkpoint["metadata"]
    else:
        state = checkpoint
    model.load_state_dict(state)
    model.eval()
    device = torch.device("cpu")
    model.to(device)
    logger.info("Loaded vision model %s", metadata.get("model_version", MODEL_VERSION))
    return VisionModelBundle(model=model, metadata=metadata, device=device)


@lru_cache(maxsize=1)
def load_vision_model() -> VisionModelBundle | None:
    return _load_from_paths(model_weights_path(), model_metadata_path())


def clear_vision_model_cache() -> None:
    load_vision_model.cache_clear()


def model_available() -> bool:
    return load_vision_model() is not None


def default_artifact_paths() -> tuple[Path, Path]:
    directory = vision_model_dir()
    return directory / MODEL_FILENAME, directory / METADATA_FILENAME
