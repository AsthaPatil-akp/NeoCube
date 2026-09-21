from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline

from app.config import settings

FEATURE_COLUMNS = [
    "semantic_similarity",
    "quantity_ratio",
    "budget_ratio",
    "delivery_ratio",
    "location_overlap",
]


def artifacts_dir() -> Path:
    configured = Path(settings.model_dir)
    if configured.is_absolute():
        return configured
    return Path(__file__).resolve().parents[2] / configured


def cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    denom = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denom == 0:
        return 0.0
    return float(np.dot(left, right) / denom)


def build_lsa_pipeline() -> Pipeline:
    return Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    analyzer="char_wb",
                    ngram_range=(3, 5),
                    min_df=1,
                    max_features=8000,
                    lowercase=True,
                ),
            ),
            ("svd", TruncatedSVD(n_components=64, random_state=42)),
        ]
    )


class SemanticEncoder:
    def __init__(self, pipeline: Pipeline | None = None) -> None:
        self.pipeline = pipeline

    @classmethod
    def load(cls) -> "SemanticEncoder":
        path = artifacts_dir() / "lsa_encoder.joblib"
        if not path.exists():
            return cls(None)
        return cls(joblib.load(path))

    def fit(self, texts: list[str]) -> "SemanticEncoder":
        self.pipeline = build_lsa_pipeline()
        self.pipeline.fit(texts)
        return self

    def transform(self, texts: list[str]) -> np.ndarray:
        if self.pipeline is None:
            raise RuntimeError("Semantic encoder is not available")
        return self.pipeline.transform(texts)

    def similarity(self, left: str, right: str) -> float:
        if self.pipeline is None:
            return 0.0
        vectors = self.transform([left or "", right or ""])
        return max(0.0, min(1.0, cosine_similarity(vectors[0], vectors[1])))
