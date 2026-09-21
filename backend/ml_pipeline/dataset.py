"""Load labeled client–supplier pairs for training.

No historical company match log exists in this repository. Place a file at
`data/company_match_pairs.csv` with the documented columns to train on real
data later without changing inference code.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

PIPELINE_ROOT = Path(__file__).resolve().parent
DATA_DIR = PIPELINE_ROOT / "data"

REQUIRED_COLUMNS = [
    "client_product",
    "supplier_product",
    "client_category",
    "supplier_category",
    "required_quantity",
    "available_quantity",
    "client_budget",
    "supplier_unit_price",
    "client_location",
    "supplier_location",
    "delivery_required",
    "supplier_delivery_capability",
    "match_label",
]


def resolve_pairs_path() -> Path:
    company = DATA_DIR / "company_match_pairs.csv"
    if company.exists():
        return company
    curated = DATA_DIR / "curated_match_pairs.csv"
    if curated.exists():
        return curated
    raise FileNotFoundError(
        "No training CSV found. Add ml_pipeline/data/company_match_pairs.csv "
        "or generate curated_match_pairs.csv via scripts/train_match_model.py"
    )


def load_training_pairs(path: Path | None = None) -> tuple[pd.DataFrame, str]:
    csv_path = path or resolve_pairs_path()
    frame = pd.read_csv(csv_path)
    missing = [name for name in REQUIRED_COLUMNS if name not in frame.columns]
    if missing:
        raise ValueError(f"Training CSV missing columns: {missing}")
    frame = frame.dropna(subset=["client_product", "supplier_product", "match_label"])
    frame["match_label"] = frame["match_label"].astype(int)
    provenance = (
        "company_match_pairs.csv (replace this file to retrain on company history)"
        if csv_path.name == "company_match_pairs.csv"
        else "curated synthetic pairs. Not historical company data."
    )
    return frame, provenance
