from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np

from app.ml.nlp import FEATURE_COLUMNS, artifacts_dir

logger = logging.getLogger("neocube")


class MatchModel:
    def __init__(self, estimator, metadata: dict) -> None:
        self.estimator = estimator
        self.metadata = metadata

    @property
    def version(self) -> str:
        return str(self.metadata.get("model_version", "unversioned"))

    def predict_proba(self, feature_row: list[float]) -> float:
        if len(feature_row) != len(FEATURE_COLUMNS):
            raise ValueError("feature row does not match the trained schema")
        array = np.array([feature_row], dtype=float)
        array = np.nan_to_num(array, nan=0.0, posinf=3.0, neginf=0.0)
        if hasattr(self.estimator, "predict_proba"):
            return float(self.estimator.predict_proba(array)[0][1])
        score = float(self.estimator.decision_function(array)[0])
        return 1.0 / (1.0 + np.exp(-score))


@lru_cache(maxsize=1)
def load_match_model() -> MatchModel | None:
    directory = artifacts_dir()
    model_path = directory / "supplier_match_model_v1.joblib"
    meta_path = directory / "model_metadata.json"
    if not model_path.exists() or not meta_path.exists():
        logger.warning("Match model artifact missing at %s", model_path)
        return None
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    if metadata.get("feature_columns") != FEATURE_COLUMNS:
        logger.error("Match model feature schema mismatch at %s", meta_path)
        return None
    loaded = MatchModel(joblib.load(model_path), metadata)
    logger.info("Loaded match model %s (%s)", loaded.version, metadata.get("selected_model"))
    return loaded


def clear_model_cache() -> None:
    load_match_model.cache_clear()
