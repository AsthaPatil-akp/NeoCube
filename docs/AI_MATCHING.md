# AI matching pipeline

## What actually runs in production

1. A submitted client requirement is loaded from SQLite.
2. Active supplier offerings are queried from SQLite (not hardcoded lists).
3. Hard filters drop ineligible offerings. AI similarity cannot override these.
4. Requirement and offering text are encoded with the saved LSA pipeline.
5. Nine numeric features are built in the same order as training (`backend/models/feature_schema.json`).
6. `supplier_match_model_v1.joblib` returns a class-1 probability.
7. Rank eligible suppliers by the trained model’s `P(match=1)` (`final_score`). Semantic cosine is a **model feature**, not the match decision by itself. Component scores are stored. If the model file is missing, fallback is `0.6 * semantic + 0.4 * structured`.
8. Ranked rows are stored on `matches` with component scores, JSON explanations, and `model_version`.

If the model file is missing, `ml_score` is stored as null and the engine falls back to `0.60 * semantic + 0.40 * structured`. It does not invent a probability.

## Hard filters

Mandatory failures (offering is not stored as a qualified match):

- offering status is not `ACTIVE` or available quantity is 0
- category id differs
- available quantity < required quantity
- parsed unit price × required quantity > client budget (when a unit price can be parsed)
- parsed supplier delivery days > parsed client days (when both can be parsed)
- required certification parsed from requirement notes is missing from supplier notes (for example “ISO 9001 certification required”)

Unparseable price or timeline does **not** auto-fail the pair; those dimensions are omitted from the hard filter and encoded as neutral structured features (`0.5`) for the model.

## NLP

Embedding model: scikit-learn `TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), max_features=8000)` followed by `TruncatedSVD(n_components=64, random_state=42)`.

Similarity: cosine similarity of the two 64-d vectors, clipped to `[0, 1]`.

The encoder is fitted **only on training-split product/category text** in `scripts/train_match_model.py`, then serialized to `backend/models/lsa_encoder.joblib`.

This is genuine vector-space semantic similarity, not keyword equality. Related phrases such as “industrial metal components” vs “steel and aluminum mechanical parts” share character n-grams and latent dimensions; unrelated electronics text does not.

## Features

Order is fixed:

1. `semantic_similarity`
2. `quantity_ratio` (clipped 0–3)
3. `budget_ratio` (clipped 0–3)
4. `delivery_ratio` (clipped 0–3)
5. `location_overlap` (Jaccard of location tokens)

Binary constraint flags (same category, quantity sufficient, within budget, delivery ok) are **hard filters**, not model inputs, so the classifier cannot reconstruct the label by copying those bits.

Inference uses `vector_to_list` so column order cannot drift from training.

## Training

See `backend/ml_pipeline/README.md` and `backend/models/model_metadata.json` after running:

```bash
cd backend
.venv\Scripts\python.exe scripts\train_match_model.py
```

Candidates: Logistic Regression (with StandardScaler), Random Forest, Gradient Boosting. Selection criterion is **validation F1**, not accuracy. Test metrics are computed once on the held-out test split.

## Explainability

Reasons are derived from actual constraint/feature values:

- Category compatible
- Quantity sufficient
- Within budget
- Delivery compatible
- Certification compatible (when a certification is required and present)
- Location compatible
- Product compatible (semantic ≥ 0.35)

A reason is not shown unless the corresponding check passed.

## Delivery feasibility (not part of the ML score)

Delivery feasibility uses only the supplier's declared delivery capability versus the client's required timeline. If both parse as days and the supplier's days are greater than the client's days, the pair fails the hard filter and is not an eligible match. Location remains a separate matching factor (stored on both sides, used for location overlap / “Location compatible”). Distance and Google Maps route times are not used and are not shown as delivery estimates.

`final_score` remains `P(match=1)` from the trained model.
