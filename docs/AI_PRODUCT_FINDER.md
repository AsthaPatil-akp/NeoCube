# AI Product Finder

AI Product Finder is an **optional, isolated** NeoCube feature that lets clients discover suppliers by uploading a product image. It uses a real PyTorch CNN for visual embeddings and cosine similarity ranking.

**AI Product Finder is independent of the existing requirement-based matching system.**

Existing LSA + Random Forest match scores are unchanged.

---

## 1. Purpose

Clients can upload a product image and receive a ranked list of suppliers whose offerings have visually similar product images. The displayed metric is **Visual Similarity**, not the existing Match Score.

## Supplier product images

Suppliers can attach an **optional** product image to an offering so Client AI Product Finder can rank by visual similarity.

### Sources

| Source value | Meaning |
|--------------|---------|
| `DIRECT_UPLOAD` | Supplier uploaded a JPG/PNG/WEBP file |
| `DOCUMENT_EXTRACTION` | Supplier selected an image extracted from the linked optional document |
| `null` | No product image |

**Priority:** an explicit direct upload or an explicit candidate selection sets the active image. Running extraction alone never silently overwrites an existing image.

### Flows

1. **Direct upload** — On create or edit offering, choose Product Image (Optional). On create, the file uploads after the offering is saved. On edit, it uploads immediately. Replaces any previous image and regenerates the vision embedding when the CNN is available.
2. **Document extraction** — Upload the existing optional PDF/DOCX document, save the offering (links the document), then extract images. If multiple usable images are found, the supplier selects one. Tiny icons (&lt; 48px) are skipped. TXT documents never yield images.
3. **Remove** — Clears file, source metadata, and embedding.

### APIs

| Method | Path |
|--------|------|
| POST | `/offerings/{id}/product-image` |
| GET | `/offerings/{id}/product-image` |
| DELETE | `/offerings/{id}/product-image` |
| POST | `/offerings/{id}/extract-product-images` |
| GET | `/offerings/{id}/product-image-candidates/{candidate_id}` |
| POST | `/offerings/{id}/select-product-image` |

Ownership: authenticated SUPPLIER who owns the offering only.

### Storage

Files under `uploads/product-images/` (safe UUID names). Temporary extract candidates under `uploads/product-image-candidates/{offering_id}/`. Metadata columns on `supplier_offerings` include `product_image_source` (migration `012_product_image_source`).

### AI Product Finder connection

Selecting or uploading an image calls the existing `upsert_offering_embedding` pipeline (real PyTorch CNN when `product_vision_cnn_v1` is deployed). Client search is unchanged and consumes these indexed embeddings.

## 3. Architecture

```
Client image
    → validate + preprocess
    → ProductVisionCNN embedding (once)
    → cosine similarity vs stored supplier embeddings
    → ranked ACTIVE offerings
```

Supplier image upload:

```
Image → validate → uploads/product-images/ → CNN embedding → product_image_embeddings
```

Feature flag: `AI_PRODUCT_FINDER_ENABLED` (default `true`).

## 4. CNN architecture

`ProductVisionCNN` (`backend/app/vision/model.py`):

- Conv 3→32 + BN + ReLU + MaxPool
- Conv 32→64 + BN + ReLU + MaxPool
- Conv 64→128 + BN + ReLU + Global Average Pool
- Linear projection → 128-d embedding (L2-normalized)
- Linear classifier → class logits

Loss: CrossEntropyLoss. Optimizer: Adam.

## 5–8. Dataset

| Item | Value |
|------|--------|
| Source | Synthetic geometric images generated with Pillow (`build_dataset.py`) |
| License | Original NeoCube training asset (no third-party photos) |
| Classes | steel_metals, electronics, packaging, textiles, industrial_components, raw_materials (aligned to NeoCube catalog) |
| Default size | 40 images/class ≈ 70% train / 15% val / 15% test |
| Location | `VISION_DATASET_DIR` (default `vision_dataset/`, gitignored) |

This is intentionally synthetic so the repo can train without shipping large photo corpora. Metrics reflect that dataset honestly.

## 9–11. Training / evaluation / artifacts

```bash
cd backend
python -m app.vision.build_dataset --per-class 40
python -m app.vision.train --epochs 8
python -m app.vision.evaluate
python -m app.vision.analyze
```

Artifacts (under `VISION_MODEL_DIR`, default `models/vision/`):

- `product_vision_cnn_v1.pth` (gitignored)
- `product_vision_cnn_v1.meta.json`
- `product_vision_cnn_v1.eval.json` (after evaluate)

**Model state:** Trained locally as `product_vision_cnn_v1` on the synthetic geometric dataset (240 images). Held-out test accuracy on that synthetic set: **1.0** (macro F1 **1.0**, n_test=36). These perfect scores reflect the intentionally separable synthetic shapes — not real product photography performance. Re-train before production use with real photos.

## 12. Embeddings

`extract_image_embedding(image_bytes)` runs the trained CNN feature path and returns an L2-normalized vector of dimension **128**.

## 13. Similarity

Cosine similarity between client embedding and each stored supplier embedding. Results below `MIN_VISUAL_SIMILARITY` (0.35) are filtered out. UI shows percentage = similarity × 100.

## 14. Supplier indexing

On product-image upload/replace, embedding is regenerated and stored with `model_version`. Old embeddings for a different model version are not treated as compatible during search (search filters on current model version).

## 15. API

| Method | Path | Who |
|--------|------|-----|
| GET | `/ai-product-finder/status` | CLIENT, SUPPLIER, ADMIN |
| POST | `/ai-product-finder/search` | CLIENT |
| POST | `/offerings/{id}/product-image` | owning SUPPLIER |
| GET | `/offerings/{id}/product-image` | CLIENT / owning SUPPLIER / ADMIN |
| DELETE | `/offerings/{id}/product-image` | owning SUPPLIER |

## 16. Security

Allowlisted magic-byte types (JPEG/PNG/WEBP), size limit, decode validation, UUID filenames under `uploads/product-images/`, ownership checks, no user-controlled paths.

## 17. Configuration

| Env | Default |
|-----|---------|
| `AI_PRODUCT_FINDER_ENABLED` | `true` |
| `VISION_MODEL_DIR` | `models/vision` |
| `VISION_DATASET_DIR` | `vision_dataset` |
| `MAX_PRODUCT_IMAGE_BYTES` | `5000000` |

## 18. Model versioning

Current: `product_vision_cnn_v1`. Search only uses embeddings whose `model_version` matches the loaded artifact.

## 19. Limitations

- Synthetic training images ≠ real product photography; real-world accuracy depends on retraining with real photos.
- Only offerings with indexed images participate.
- Visual Similarity ≠ Match Score.

## 20. How to train / update

See commands in section 9. After replacing weights, re-upload supplier product images (or run a reindex script) so embeddings match the new version.

## 21. How to disable / remove

**Disable:** set `AI_PRODUCT_FINDER_ENABLED=false` and restart the API. The dashboard button hides when status reports disabled; routes return 404.

**Remove safely:**

1. Disable the flag.
2. Remove `<AIProductFinderCard />` from `ClientDashboard.jsx`.
3. Remove `backend/app/vision/`, `routers/ai_product_finder.py`, and related API helpers.
4. Optionally reverse Alembic `011_product_vision` (optional columns/table).

Existing matching, RFQs, orders, and notifications do not depend on this feature.

## Migration

Alembic revision: `011_product_vision` — adds optional `product_image_*` columns on `supplier_offerings` and table `product_image_embeddings`.
