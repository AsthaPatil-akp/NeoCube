"""Tests for AI Product Finder (vision CNN + product images)."""

from __future__ import annotations

import io
import os
import uuid

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

os.environ.setdefault("AI_PRODUCT_FINDER_ENABLED", "true")

torch = pytest.importorskip("torch")

from app.config import settings
from app.main import app
from app.vision.build_dataset import build_dataset
from app.vision.config import EMBEDDING_DIM, IMAGE_SIZE, MODEL_VERSION, VISION_CLASSES
from app.vision.embeddings import cosine_similarity, deserialize_embedding, serialize_embedding
from app.vision.model import ProductVisionCNN
from app.vision.model_store import clear_vision_model_cache, save_model
from app.vision.preprocessing import preprocess_image_bytes

settings.ai_product_finder_enabled = True
settings.upload_dir = os.path.join(os.path.dirname(__file__), "_uploads")
os.makedirs(settings.upload_dir, exist_ok=True)


TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


def make_client():
    return TestClient(app)


def register_and_login(client, email, role="CLIENT", **overrides):
    payload = {
        "email": email,
        "password": "password123",
        "role": role,
        "full_name": "Test User",
        "company_name": "Test Co",
        "phone": "555-0100",
    }
    payload.update(overrides)
    created = client.post("/auth/register", json=payload)
    assert created.status_code == 201, created.text
    login = client.post("/auth/login", json={"email": email, "password": "password123"})
    assert login.status_code == 200, login.text
    return created.json()


def offering_payload(category_id: int, **overrides):
    data = {
        "supplier_name": "Vision Supply",
        "product_offered": "Steel coil sample",
        "category_id": category_id,
        "available_quantity": 500,
        "quantity_unit": "units",
        "price_amount": 1000,
        "price_currency": "INR",
        "price_basis": "PER_UNIT",
        "location": "Pune",
        "delivery_capability": "2 weeks",
        "status": "ACTIVE",
    }
    data.update(overrides)
    return data


def _png_bytes(color=(180, 190, 200), size=(96, 96)) -> bytes:
    image = Image.new("RGB", size, color)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture()
def trained_vision_model(tmp_path, monkeypatch):
    """Train a tiny CNN on a synthetic mini-dataset and point settings at it."""
    dataset_root = tmp_path / "dataset"
    model_dir = tmp_path / "models"
    build_dataset(dataset_root, per_class=12, seed=7)
    monkeypatch.setattr(settings, "vision_dataset_dir", str(dataset_root))
    monkeypatch.setattr(settings, "vision_model_dir", str(model_dir))
    clear_vision_model_cache()
    from app.vision.train import train

    train(dataset_root, epochs=2, batch_size=8, learning_rate=1e-3, seed=7, image_size=IMAGE_SIZE)
    clear_vision_model_cache()
    yield model_dir
    clear_vision_model_cache()


def test_cnn_forward_and_embedding_shapes():
    model = ProductVisionCNN(num_classes=len(VISION_CLASSES), embedding_dim=EMBEDDING_DIM)
    model.eval()
    batch = torch.randn(2, 3, IMAGE_SIZE, IMAGE_SIZE)
    logits = model(batch)
    emb = model.embedding(batch)
    assert logits.shape == (2, len(VISION_CLASSES))
    assert emb.shape == (2, EMBEDDING_DIM)
    norms = emb.norm(dim=1)
    assert torch.allclose(norms, torch.ones_like(norms), atol=1e-4)


def test_preprocess_and_cosine_similarity():
    tensor = preprocess_image_bytes(_png_bytes())
    assert tensor.shape == (1, 3, IMAGE_SIZE, IMAGE_SIZE)
    a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    b = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    c = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    assert abs(cosine_similarity(a, b) - 1.0) < 1e-5
    assert abs(cosine_similarity(a, c)) < 1e-5
    raw = serialize_embedding(a)
    assert deserialize_embedding(raw).tolist() == a.tolist()


def test_model_save_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "vision_model_dir", str(tmp_path))
    clear_vision_model_cache()
    model = ProductVisionCNN(num_classes=len(VISION_CLASSES), embedding_dim=EMBEDDING_DIM)
    meta = {
        "model_version": MODEL_VERSION,
        "class_names": list(VISION_CLASSES),
        "embedding_dim": EMBEDDING_DIM,
        "image_size": IMAGE_SIZE,
        "trained": True,
    }
    save_model(model, meta)
    from app.vision.model_store import load_vision_model

    bundle = load_vision_model()
    assert bundle is not None
    assert bundle.version == MODEL_VERSION
    clear_vision_model_cache()


def test_status_requires_auth():
    client = make_client()
    assert client.get("/ai-product-finder/status").status_code == 401


def test_status_model_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "vision_model_dir", str(tmp_path / "empty"))
    clear_vision_model_cache()
    client = make_client()
    register_and_login(client, f"status-{uuid.uuid4().hex}@example.com")
    response = client.get("/ai-product-finder/status")
    assert response.status_code == 200
    body = response.json()
    assert body["model_available"] is False
    assert "unavailable" in (body["message"] or "").lower()
    clear_vision_model_cache()


def test_search_rejects_non_client(trained_vision_model):
    client = make_client()
    register_and_login(client, f"sup-{uuid.uuid4().hex}@example.com", role="SUPPLIER")
    response = client.post(
        "/ai-product-finder/search",
        files={"file": ("q.png", _png_bytes(), "image/png")},
    )
    assert response.status_code == 403


def test_search_rejects_invalid_file(trained_vision_model):
    client = make_client()
    register_and_login(client, f"cli-{uuid.uuid4().hex}@example.com")
    response = client.post(
        "/ai-product-finder/search",
        files={"file": ("notes.txt", b"not-an-image", "text/plain")},
    )
    assert response.status_code == 400


def test_search_unavailable_model(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "vision_model_dir", str(tmp_path / "missing"))
    clear_vision_model_cache()
    client = make_client()
    register_and_login(client, f"cli-{uuid.uuid4().hex}@example.com")
    response = client.post(
        "/ai-product-finder/search",
        files={"file": ("q.png", _png_bytes(), "image/png")},
    )
    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"].lower()
    clear_vision_model_cache()


def test_product_image_upload_ownership_and_search(trained_vision_model):
    supplier = make_client()
    register_and_login(supplier, f"own-{uuid.uuid4().hex}@example.com", role="SUPPLIER")
    categories = supplier.get("/categories").json()
    category_id = next(item["id"] for item in categories if item["name"] == "Steel & Metals")
    created = supplier.post("/offerings", json=offering_payload(category_id))
    assert created.status_code == 201, created.text
    offering_id = created.json()["id"]

    uploaded = supplier.post(
        f"/offerings/{offering_id}/product-image",
        files={"file": ("steel.png", _png_bytes((180, 190, 200)), "image/png")},
    )
    assert uploaded.status_code == 200, uploaded.text
    body = uploaded.json()
    assert body["has_product_image"] is True
    assert body["product_image_indexed"] is True

    other = make_client()
    register_and_login(other, f"other-{uuid.uuid4().hex}@example.com", role="SUPPLIER")
    denied = other.post(
        f"/offerings/{offering_id}/product-image",
        files={"file": ("x.png", _png_bytes(), "image/png")},
    )
    assert denied.status_code == 404

    client = make_client()
    register_and_login(client, f"buyer-{uuid.uuid4().hex}@example.com")
    status = client.get("/ai-product-finder/status")
    assert status.status_code == 200
    assert status.json()["model_available"] is True
    assert status.json()["number_of_indexed_supplier_images"] >= 1

    search = client.post(
        "/ai-product-finder/search",
        files={"file": ("query.png", _png_bytes((180, 190, 200)), "image/png")},
    )
    assert search.status_code == 200, search.text
    payload = search.json()
    assert payload["result_count"] >= 1
    top = payload["results"][0]
    assert "visual_similarity" in top
    assert top["supplier_name"] == "Vision Supply"
    assert 0 <= top["visual_similarity"] <= 100

    removed = supplier.delete(f"/offerings/{offering_id}/product-image")
    assert removed.status_code == 200
    assert removed.json()["has_product_image"] is False


def test_empty_index_message(trained_vision_model):
    from sqlalchemy import delete

    from app.database import SessionLocal
    from app.models import ProductImageEmbedding

    db = SessionLocal()
    try:
        db.execute(delete(ProductImageEmbedding))
        db.commit()
    finally:
        db.close()

    client = make_client()
    register_and_login(client, f"empty-{uuid.uuid4().hex}@example.com")
    search = client.post(
        "/ai-product-finder/search",
        files={"file": ("query.png", _png_bytes(), "image/png")},
    )
    assert search.status_code == 200
    body = search.json()
    assert body["result_count"] == 0
    assert "no supplier product images" in body["message"].lower()


def test_feature_disabled(monkeypatch):
    monkeypatch.setattr(settings, "ai_product_finder_enabled", False)
    # Router may still be mounted from import-time flag; endpoint checks settings.
    client = make_client()
    register_and_login(client, f"off-{uuid.uuid4().hex}@example.com")
    assert client.get("/ai-product-finder/status").status_code == 404
    monkeypatch.setattr(settings, "ai_product_finder_enabled", True)


def test_dataset_loads(tmp_path):
    root = tmp_path / "ds"
    build_dataset(root, per_class=6, seed=1)
    from app.vision.dataset import ProductImageFolder

    ds = ProductImageFolder(root / "train", train=False)
    assert len(ds) > 0
    image, label = ds[0]
    assert image.shape[0] == 3
    assert 0 <= label < len(VISION_CLASSES)
