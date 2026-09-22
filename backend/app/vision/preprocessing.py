"""Image preprocessing for the product-vision CNN (Pillow + NumPy + torch)."""

from __future__ import annotations

from io import BytesIO
import random

import numpy as np
from PIL import Image, ImageEnhance, UnidentifiedImageError
import torch

from app.vision.config import IMAGE_SIZE

_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(3, 1, 1)
_IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(3, 1, 1)


def load_rgb_image(payload: bytes) -> Image.Image:
    if not payload:
        raise ValueError("Image payload is empty")
    try:
        image = Image.open(BytesIO(payload))
        image.load()
    except UnidentifiedImageError as exc:
        raise ValueError("Unable to decode image") from exc
    except OSError as exc:
        raise ValueError("Corrupt or unreadable image") from exc
    return image.convert("RGB")


def _to_tensor(image: Image.Image) -> torch.Tensor:
    array = np.asarray(image, dtype=np.float32) / 255.0
    array = np.transpose(array, (2, 0, 1))
    array = (array - _IMAGENET_MEAN) / _IMAGENET_STD
    return torch.from_numpy(array.copy())


def _resize(image: Image.Image, size: int) -> Image.Image:
    return image.resize((size, size), Image.Resampling.BILINEAR)


def _random_crop(image: Image.Image, size: int) -> Image.Image:
    width, height = image.size
    if width < size or height < size:
        return _resize(image, size)
    left = random.randint(0, width - size)
    top = random.randint(0, height - size)
    return image.crop((left, top, left + size, top + size))


def transform_eval(image: Image.Image, image_size: int = IMAGE_SIZE) -> torch.Tensor:
    return _to_tensor(_resize(image, image_size))


def transform_train(image: Image.Image, image_size: int = IMAGE_SIZE) -> torch.Tensor:
    larger = _resize(image, image_size + 8)
    cropped = _random_crop(larger, image_size)
    if random.random() < 0.5:
        cropped = cropped.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if random.random() < 0.5:
        factor = 1.0 + random.uniform(-0.15, 0.15)
        cropped = ImageEnhance.Brightness(cropped).enhance(factor)
    if random.random() < 0.5:
        factor = 1.0 + random.uniform(-0.15, 0.15)
        cropped = ImageEnhance.Contrast(cropped).enhance(factor)
    return _to_tensor(cropped)


def preprocess_image_bytes(payload: bytes, image_size: int = IMAGE_SIZE) -> torch.Tensor:
    """Return a single-image tensor shaped (1, 3, H, W)."""
    image = load_rgb_image(payload)
    return transform_eval(image, image_size).unsqueeze(0)
