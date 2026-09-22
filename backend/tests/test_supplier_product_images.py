"""Supplier-side product image + document extraction tests."""

from __future__ import annotations

import io
import os
import uuid
import zipfile

import pytest
from fastapi.testclient import TestClient
from PIL import Image

os.environ.setdefault("AI_PRODUCT_FINDER_ENABLED", "true")

pytest.importorskip("torch")

from app.config import settings
from app.main import app
from app.vision.model_store import clear_vision_model_cache
from app.vision.product_images import SOURCE_DIRECT_UPLOAD, SOURCE_DOCUMENT_EXTRACTION

settings.ai_product_finder_enabled = True
settings.upload_dir = os.path.join(os.path.dirname(__file__), "_uploads")
os.makedirs(settings.upload_dir, exist_ok=True)


def make_client():
    return TestClient(app)


def register_and_login(client, email, role="SUPPLIER", **overrides):
    payload = {
        "email": email,
        "password": "password123",
        "role": role,
        "full_name": "Test User",
        "company_name": "Test Co",
        "phone": "555-0100",
    }
    payload.update(overrides)
    assert client.post("/auth/register", json=payload).status_code == 201
    assert client.post("/auth/login", json={"email": email, "password": "password123"}).status_code == 200


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


def _png_bytes(color=(40, 180, 255), size=(96, 96)) -> bytes:
    image = Image.new("RGB", size, color)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _docx_with_images(*png_payloads: bytes) -> bytes:
    """Minimal OOXML package with embedded media images and enough text for extract_text."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="png" ContentType="image/png"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>""",
        )
        archive.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "word/document.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>Product Offered: Embedded Widget</w:t></w:r></w:p>
    <w:p><w:r><w:t>Available Quantity: 10</w:t></w:r></w:p>
    <w:p><w:r><w:t>Location: Pune</w:t></w:r></w:p>
    <w:p><w:r><w:t>Delivery Capability: 7 days</w:t></w:r></w:p>
    <w:p><w:r><w:t>Price Amount: 100</w:t></w:r></w:p>
  </w:body>
</w:document>""",
        )
        for index, payload in enumerate(png_payloads):
            archive.writestr(f"word/media/image{index + 1}.png", payload)
    return buffer.getvalue()


@pytest.fixture()
def trained_vision_model(tmp_path, monkeypatch):
    from app.vision.build_dataset import build_dataset
    from app.vision.config import IMAGE_SIZE
    from app.vision.train import train

    dataset_root = tmp_path / "dataset"
    model_dir = tmp_path / "models"
    build_dataset(dataset_root, per_class=8, seed=3)
    monkeypatch.setattr(settings, "vision_dataset_dir", str(dataset_root))
    monkeypatch.setattr(settings, "vision_model_dir", str(model_dir))
    clear_vision_model_cache()
    train(dataset_root, epochs=1, batch_size=8, learning_rate=1e-3, seed=3, image_size=IMAGE_SIZE)
    clear_vision_model_cache()
    yield
    clear_vision_model_cache()


def test_direct_upload_persists_source(trained_vision_model):
    client = make_client()
    register_and_login(client, f"up-{uuid.uuid4().hex}@example.com")
    category_id = next(item["id"] for item in client.get("/categories").json() if item["name"] == "Electronics")
    created = client.post("/offerings", json=offering_payload(category_id))
    assert created.status_code == 201
    offering_id = created.json()["id"]
    uploaded = client.post(
        f"/offerings/{offering_id}/product-image",
        files={"file": ("product.png", _png_bytes(), "image/png")},
    )
    assert uploaded.status_code == 200, uploaded.text
    body = uploaded.json()
    assert body["has_product_image"] is True
    assert body["product_image_source"] == SOURCE_DIRECT_UPLOAD
    reloaded = client.get(f"/offerings/{offering_id}")
    assert reloaded.json()["product_image_source"] == SOURCE_DIRECT_UPLOAD
    assert client.get(f"/offerings/{offering_id}/product-image").status_code == 200


def test_invalid_and_oversized_image_rejected(trained_vision_model):
    client = make_client()
    register_and_login(client, f"bad-{uuid.uuid4().hex}@example.com")
    category_id = next(item["id"] for item in client.get("/categories").json() if item["name"] == "Electronics")
    offering_id = client.post("/offerings", json=offering_payload(category_id)).json()["id"]
    assert (
        client.post(
            f"/offerings/{offering_id}/product-image",
            files={"file": ("x.txt", b"not-image", "text/plain")},
        ).status_code
        == 400
    )
    monkeypatch_max = settings.max_product_image_bytes
    settings.max_product_image_bytes = 100
    try:
        assert (
            client.post(
                f"/offerings/{offering_id}/product-image",
                files={"file": ("big.png", _png_bytes(size=(200, 200)), "image/png")},
            ).status_code
            == 413
        )
    finally:
        settings.max_product_image_bytes = monkeypatch_max


def test_replace_and_remove_image(trained_vision_model):
    client = make_client()
    register_and_login(client, f"rep-{uuid.uuid4().hex}@example.com")
    category_id = next(item["id"] for item in client.get("/categories").json() if item["name"] == "Electronics")
    offering_id = client.post("/offerings", json=offering_payload(category_id)).json()["id"]
    first = client.post(
        f"/offerings/{offering_id}/product-image",
        files={"file": ("a.png", _png_bytes((10, 10, 10)), "image/png")},
    )
    assert first.status_code == 200
    second = client.post(
        f"/offerings/{offering_id}/product-image",
        files={"file": ("b.png", _png_bytes((200, 20, 20)), "image/png")},
    )
    assert second.status_code == 200
    assert second.json()["product_image_source"] == SOURCE_DIRECT_UPLOAD
    removed = client.delete(f"/offerings/{offering_id}/product-image")
    assert removed.status_code == 200
    assert removed.json()["has_product_image"] is False
    assert removed.json()["product_image_source"] is None


def test_document_extract_select_and_source(trained_vision_model):
    client = make_client()
    register_and_login(client, f"doc-{uuid.uuid4().hex}@example.com")
    category_id = next(item["id"] for item in client.get("/categories").json() if item["name"] == "Electronics")
    docx = _docx_with_images(_png_bytes((40, 180, 255)), _png_bytes((220, 140, 40)))
    uploaded_doc = client.post(
        "/supplier-documents",
        files={
            "file": (
                "offering.docx",
                docx,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert uploaded_doc.status_code == 201, uploaded_doc.text
    document_id = uploaded_doc.json()["id"]
    created = client.post(
        "/offerings",
        json=offering_payload(category_id, document_id=document_id, product_offered="Embedded Widget"),
    )
    assert created.status_code == 201, created.text
    offering_id = created.json()["id"]

    extracted = client.post(f"/offerings/{offering_id}/extract-product-images")
    assert extracted.status_code == 200, extracted.text
    body = extracted.json()
    assert len(body["candidates"]) >= 2
    chosen = body["candidates"][1]["candidate_id"]
    selected = client.post(
        f"/offerings/{offering_id}/select-product-image",
        json={"candidate_id": chosen},
    )
    assert selected.status_code == 200, selected.text
    assert selected.json()["has_product_image"] is True
    assert selected.json()["product_image_source"] == SOURCE_DOCUMENT_EXTRACTION

    # Direct upload must not be overwritten without an explicit select — calling extract again leaves source.
    re_extract = client.post(f"/offerings/{offering_id}/extract-product-images")
    assert re_extract.status_code == 200
    still = client.get(f"/offerings/{offering_id}").json()
    assert still["product_image_source"] == SOURCE_DOCUMENT_EXTRACTION
    assert still["has_product_image"] is True


def test_document_images_extracted_before_publish_then_applied_once(trained_vision_model):
    client = make_client()
    register_and_login(client, f"pre-{uuid.uuid4().hex}@example.com")
    category_id = next(item["id"] for item in client.get("/categories").json() if item["name"] == "Electronics")
    docx = _docx_with_images(_png_bytes((40, 180, 255)), _png_bytes((220, 140, 40)))
    uploaded_doc = client.post(
        "/supplier-documents",
        files={
            "file": (
                "offering.docx",
                docx,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert uploaded_doc.status_code == 201, uploaded_doc.text
    document_id = uploaded_doc.json()["id"]
    extracted = client.post(f"/supplier-documents/{document_id}/extract-product-images")
    assert extracted.status_code == 200, extracted.text
    candidates = extracted.json()["candidates"]
    assert len(candidates) >= 2
    preview = client.get(candidates[0]["preview_url"])
    assert preview.status_code == 200
    chosen = candidates[1]["candidate_id"]
    created = client.post(
        "/offerings",
        json=offering_payload(category_id, document_id=document_id, product_offered="Embedded Widget"),
    )
    assert created.status_code == 201, created.text
    offering_id = created.json()["id"]
    selected = client.post(
        f"/offerings/{offering_id}/select-product-image",
        json={"candidate_id": chosen, "document_id": document_id},
    )
    assert selected.status_code == 200, selected.text
    assert selected.json()["has_product_image"] is True
    assert selected.json()["product_image_source"] == SOURCE_DOCUMENT_EXTRACTION
    listed = client.get("/offerings").json()
    assert len([row for row in listed if row["id"] == offering_id]) == 1


def test_txt_document_extract_empty_message(trained_vision_model):
    client = make_client()
    register_and_login(client, f"txt-{uuid.uuid4().hex}@example.com")
    category_id = next(item["id"] for item in client.get("/categories").json() if item["name"] == "Electronics")
    text = b"Product Offered: Plain Text Item\nAvailable Quantity: 5\nLocation: Pune\nDelivery Capability: 3 days\nPrice Amount: 50\n"
    uploaded_doc = client.post("/supplier-documents", files={"file": ("notes.txt", text, "text/plain")})
    assert uploaded_doc.status_code == 201, uploaded_doc.text
    offering_id = client.post(
        "/offerings",
        json=offering_payload(category_id, document_id=uploaded_doc.json()["id"]),
    ).json()["id"]
    extracted = client.post(f"/offerings/{offering_id}/extract-product-images")
    assert extracted.status_code == 200
    body = extracted.json()
    assert body["candidates"] == []
    assert "no product image" in (body["message"] or "").lower()


def test_ownership_and_auth_for_image_endpoints(trained_vision_model):
    owner = make_client()
    register_and_login(owner, f"own-{uuid.uuid4().hex}@example.com")
    category_id = next(item["id"] for item in owner.get("/categories").json() if item["name"] == "Electronics")
    offering_id = owner.post("/offerings", json=offering_payload(category_id)).json()["id"]
    assert (
        owner.post(
            f"/offerings/{offering_id}/product-image",
            files={"file": ("a.png", _png_bytes(), "image/png")},
        ).status_code
        == 200
    )

    other = make_client()
    register_and_login(other, f"oth-{uuid.uuid4().hex}@example.com")
    assert (
        other.post(
            f"/offerings/{offering_id}/product-image",
            files={"file": ("b.png", _png_bytes(), "image/png")},
        ).status_code
        == 404
    )
    assert other.delete(f"/offerings/{offering_id}/product-image").status_code == 404
    assert other.post(f"/offerings/{offering_id}/extract-product-images").status_code == 404

    anon = make_client()
    assert anon.post(f"/offerings/{offering_id}/extract-product-images").status_code == 401

    client_user = make_client()
    register_and_login(client_user, f"cli-{uuid.uuid4().hex}@example.com", role="CLIENT")
    assert (
        client_user.post(
            f"/offerings/{offering_id}/product-image",
            files={"file": ("c.png", _png_bytes(), "image/png")},
        ).status_code
        == 403
    )


def test_offering_without_image_remains_valid(trained_vision_model):
    client = make_client()
    register_and_login(client, f"none-{uuid.uuid4().hex}@example.com")
    category_id = next(item["id"] for item in client.get("/categories").json() if item["name"] == "Electronics")
    created = client.post("/offerings", json=offering_payload(category_id))
    assert created.status_code == 201
    body = created.json()
    assert body["has_product_image"] is False
    assert body["product_image_source"] is None
