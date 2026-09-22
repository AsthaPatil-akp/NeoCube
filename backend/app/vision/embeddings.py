"""Embedding extraction and cosine similarity for product vision."""

from __future__ import annotations

import json

import numpy as np
import torch

from app.vision.model_store import VisionModelBundle, load_vision_model
from app.vision.preprocessing import preprocess_image_bytes


class VisionUnavailableError(RuntimeError):
    """Raised when the trained vision model artifact is missing."""


def extract_image_embedding(payload: bytes, bundle: VisionModelBundle | None = None) -> np.ndarray:
    """Run the trained CNN and return an L2-normalized embedding vector."""
    bundle = bundle or load_vision_model()
    if bundle is None:
        raise VisionUnavailableError(
            "AI Product Finder is currently unavailable because the vision model has not been trained/deployed."
        )
    tensor = preprocess_image_bytes(payload, image_size=bundle.image_size)
    tensor = tensor.to(bundle.device)
    with torch.no_grad():
        emb = bundle.model.embedding(tensor)
    vector = emb.cpu().numpy()[0].astype(np.float32)
    return vector


def serialize_embedding(vector: np.ndarray) -> str:
    return json.dumps([float(x) for x in vector.tolist()])


def deserialize_embedding(raw: str) -> np.ndarray:
    values = json.loads(raw)
    return np.asarray(values, dtype=np.float32)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float32).reshape(-1)
    b = np.asarray(b, dtype=np.float32).reshape(-1)
    if a.shape != b.shape:
        raise ValueError("Embedding dimensions do not match")
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)
