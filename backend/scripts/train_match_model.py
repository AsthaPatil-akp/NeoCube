"""Build a curated client-supplier label set and train match models from scratch.

This is NOT historical company data. Labels follow documented business rules.
"""

from __future__ import annotations

import json
import sys
from importlib import metadata
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ml.nlp import FEATURE_COLUMNS, SemanticEncoder, artifacts_dir  # noqa: E402
from app.ml.parse import location_overlap, parse_days, parse_unit_price  # noqa: E402
from ml_pipeline.dataset import DATA_DIR, load_training_pairs  # noqa: E402

FAMILIES = {
    "Steel & Metals": [
        "steel brackets",
        "industrial metal components",
        "steel and aluminum mechanical parts",
        "galvanized steel fasteners",
        "stainless steel fittings",
    ],
    "Electronics": [
        "printed circuit boards",
        "electronic control modules",
        "pcb assemblies",
        "industrial sensors",
        "power supply units",
    ],
    "Packaging": [
        "corrugated cartons",
        "industrial packaging boxes",
        "protective packing material",
        "custom cardboard cartons",
    ],
    "Textiles": [
        "cotton fabric rolls",
        "industrial textile material",
        "woven cotton cloth",
        "polyester fabric",
    ],
    "Industrial Components": [
        "hydraulic fittings",
        "mechanical couplings",
        "industrial machine parts",
        "precision machined components",
    ],
    "Raw Materials": [
        "polymer resin pellets",
        "industrial raw polymer",
        "plastic granules",
        "commodity resin",
    ],
    "Logistics": [
        "palletized freight handling",
        "inland cargo transport",
        "warehouse logistics service",
        "road freight capacity",
    ],
}


def _clip(value: float, high: float = 3.0) -> float:
    return max(0.0, min(high, value))


def build_frame() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    rows = []
    categories = list(FAMILIES)
    for category in categories:
        products = FAMILIES[category]
        other_cat = [name for name in categories if name != category]
        for client_product in products:
            for supplier_product in products:
                for _ in range(2):
                    qty = int(rng.integers(500, 8000))
                    avail = int(qty * rng.uniform(1.05, 2.2))
                    unit = int(rng.integers(20, 200))
                    budget = int(unit * qty * rng.uniform(1.05, 1.6))
                    client_days = int(rng.choice([14, 21, 30, 45]))
                    supplier_days = int(rng.choice([7, 10, 14, 21, client_days]))
                    loc = str(rng.choice(["Pune", "Pune Maharashtra", "Mumbai", "Chennai"]))
                    rows.append(_row(
                        client_product, supplier_product, category, category, qty, avail,
                        budget, unit, loc, loc if rng.random() > 0.3 else "Pune",
                        f"{client_days} days", f"{supplier_days} days nationwide", 1,
                    ))
            for supplier_product in FAMILIES[rng.choice(other_cat)]:
                qty = int(rng.integers(500, 5000))
                rows.append(_row(
                    client_product, supplier_product, category, rng.choice(other_cat), qty, qty + 100,
                    qty * 80, 50, "Pune", "Delhi", "30 days", "14 days", 0,
                ))
            rows.append(_row(
                client_product, products[0], category, category, 5000, 1000,
                800000, 120, "Pune", "Pune", "30 days", "14 days", 0,
            ))
            rows.append(_row(
                client_product, products[0], category, category, 2000, 9000,
                50000, 80, "Pune", "Pune", "10 days", "30 days", 0,
            ))
    return pd.DataFrame(rows)


def _row(cprod, sprod, ccat, scat, qty, avail, budget, unit, cloc, sloc, ctime, stime, forced_label) -> dict:
    unit_price = unit
    estimated = unit_price * qty
    client_days = parse_days(ctime)
    supplier_days = parse_days(stime)
    quantity_ok = avail >= qty
    category_ok = ccat == scat
    budget_ok = estimated <= budget
    delivery_ok = supplier_days is not None and client_days is not None and supplier_days <= client_days
    same_family = ccat == scat
    label = int(same_family and quantity_ok and budget_ok and delivery_ok)
    if forced_label == 0:
        label = 0
    return {
        "client_product": cprod,
        "supplier_product": sprod,
        "client_category": ccat,
        "supplier_category": scat,
        "required_quantity": qty,
        "available_quantity": avail,
        "client_budget": budget,
        "supplier_unit_price": unit_price,
        "client_location": cloc,
        "supplier_location": sloc,
        "delivery_required": ctime,
        "supplier_delivery_capability": stime,
        "match_label": label,
        "label_rule": "positive only if same category family, quantity sufficient, estimated cost within budget, and delivery days <= required days",
    }


def add_features(df: pd.DataFrame, encoder: SemanticEncoder) -> pd.DataFrame:
    semantics = [
        encoder.similarity(f"{row.client_product} {row.client_category}", f"{row.supplier_product} {row.supplier_category}")
        for row in df.itertuples()
    ]
    df = df.copy()
    df["semantic_similarity"] = semantics
    df["same_category"] = (df["client_category"] == df["supplier_category"]).astype(float)
    df["quantity_ratio"] = (df["available_quantity"] / df["required_quantity"]).clip(0, 3)
    df["quantity_sufficient"] = (df["available_quantity"] >= df["required_quantity"]).astype(float)
    estimated = df["supplier_unit_price"] * df["required_quantity"]
    df["budget_ratio"] = (estimated / df["client_budget"]).clip(0, 3)
    df["within_budget"] = (estimated <= df["client_budget"]).astype(float)
    c_days = df["delivery_required"].map(parse_days).fillna(30)
    s_days = df["supplier_delivery_capability"].map(parse_days).fillna(30)
    df["delivery_ratio"] = (s_days / c_days).clip(0, 3)
    df["delivery_ok"] = (s_days <= c_days).astype(float)
    df["location_overlap"] = [
        location_overlap(row.client_location, row.supplier_location) for row in df.itertuples()
    ]
    return df


def metrics(y_true, y_prob, y_pred) -> dict:
    return {
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(y_true, y_prob)), 4),
        "confusion_matrix": confusion_matrix(y_true, y_pred).tolist(),
        "report": classification_report(y_true, y_pred, zero_division=0),
    }


def main() -> None:
    company_csv = DATA_DIR / "company_match_pairs.csv"
    if company_csv.exists():
        raw, provenance = load_training_pairs(company_csv)
    else:
        raw = build_frame().drop_duplicates(
            subset=["client_product", "supplier_product", "required_quantity", "available_quantity", "client_budget", "supplier_unit_price", "match_label"]
        )
        provenance = "curated synthetic client-supplier pairs generated from product-family templates. Not historical company data."
    train_raw, temp = train_test_split(raw, test_size=0.30, random_state=42, stratify=raw["match_label"])
    val_raw, test_raw = train_test_split(temp, test_size=0.50, random_state=42, stratify=temp["match_label"])

    encoder = SemanticEncoder().fit(
        (train_raw["client_product"] + " " + train_raw["client_category"]).tolist()
        + (train_raw["supplier_product"] + " " + train_raw["supplier_category"]).tolist()
    )
    train_df = add_features(train_raw, encoder)
    val_df = add_features(val_raw, encoder)
    test_df = add_features(test_raw, encoder)

    x_train = train_df[FEATURE_COLUMNS].to_numpy(dtype=float)
    y_train = train_df["match_label"].to_numpy()
    x_val = val_df[FEATURE_COLUMNS].to_numpy(dtype=float)
    y_val = val_df["match_label"].to_numpy()
    x_test = test_df[FEATURE_COLUMNS].to_numpy(dtype=float)
    y_test = test_df["match_label"].to_numpy()

    candidates = {
        "logistic_regression": Pipeline(
            [
                ("scaler", StandardScaler()),
                ("model", LogisticRegression(max_iter=400, class_weight="balanced", random_state=42)),
            ]
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=200, max_depth=8, min_samples_leaf=3, class_weight="balanced", random_state=42
        ),
        "gradient_boosting": GradientBoostingClassifier(random_state=42),
    }

    validation = {}
    best_name = None
    best_f1 = -1.0
    best_estimator = None
    for name, model in candidates.items():
        model.fit(x_train, y_train)
        val_prob = model.predict_proba(x_val)[:, 1]
        val_pred = (val_prob >= 0.5).astype(int)
        score = metrics(y_val, val_prob, val_pred)
        validation[name] = {k: v for k, v in score.items() if k != "report"}
        if score["f1"] > best_f1:
            best_f1 = score["f1"]
            best_name = name
            best_estimator = model

    assert best_estimator is not None
    test_prob = best_estimator.predict_proba(x_test)[:, 1]
    test_pred = (test_prob >= 0.5).astype(int)
    test_metrics = metrics(y_test, test_prob, test_pred)

    out = artifacts_dir()
    out.mkdir(parents=True, exist_ok=True)
    data_dir = ROOT / "ml_pipeline" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    eda_dir = ROOT / "ml_pipeline" / "eda"
    eda_dir.mkdir(parents=True, exist_ok=True)
    if not company_csv.exists():
        raw.to_csv(data_dir / "curated_match_pairs.csv", index=False)
    train_df[FEATURE_COLUMNS + ["match_label"]].describe().to_csv(eda_dir / "train_feature_describe.csv")
    fig, ax = plt.subplots()
    raw["match_label"].value_counts().sort_index().plot(kind="bar", ax=ax, color="#556b2f")
    ax.set_title("Curated match_label distribution")
    ax.set_xlabel("label")
    ax.set_ylabel("count")
    fig.tight_layout()
    fig.savefig(eda_dir / "class_distribution.png")
    plt.close(fig)
    joblib.dump(best_estimator, out / "supplier_match_model_v1.joblib")
    joblib.dump(encoder.pipeline, out / "lsa_encoder.joblib")
    (out / "feature_schema.json").write_text(json.dumps({"feature_columns": FEATURE_COLUMNS}, indent=2), encoding="utf-8")

    def pkg_version(name: str) -> str:
        try:
            return metadata.version(name)
        except metadata.PackageNotFoundError:
            return "unknown"

    metadata_doc = {
        "model_version": "supplier_match_model_v1",
        "selected_model": best_name,
        "selection_rule": "highest validation F1; accuracy was not the selection criterion",
        "dataset_source": provenance,
        "label_definition": "match_label=1 only when category family matches, available_quantity >= required_quantity, unit_price*quantity <= budget, and parsed supplier delivery days <= client days.",
        "records": int(len(raw)),
        "class_balance": {str(k): int(v) for k, v in raw["match_label"].value_counts().to_dict().items()},
        "split": {"train": int(len(train_df)), "validation": int(len(val_df)), "test": int(len(test_df)), "random_state": 42, "stratified": True},
        "feature_columns": FEATURE_COLUMNS,
        "preprocessing": "LSA (Tfidf char_wb 3-5 grams + TruncatedSVD 64) fitted on TRAIN product text only. ML features are semantic cosine plus quantity/budget/delivery ratios and location overlap. Binary label-rule flags are NOT used as model inputs (they remain hard filters at inference).",
        "validation_metrics": validation,
        "test_metrics": {k: v for k, v in test_metrics.items() if k != "report"},
        "test_classification_report": test_metrics["report"],
        "final_score_formula": "Hard filters first. Among eligible suppliers, final_score equals the trained model P(match=1). Semantic cosine is a model feature, not a standalone keyword score. If the model artifact is missing, fallback is 0.6*semantic + 0.4*structured.",
        "dependencies": {
            "scikit-learn": pkg_version("scikit-learn"),
            "numpy": pkg_version("numpy"),
            "pandas": pkg_version("pandas"),
            "joblib": pkg_version("joblib"),
        },
    }
    (out / "model_metadata.json").write_text(json.dumps(metadata_doc, indent=2), encoding="utf-8")
    print(json.dumps({"selected": best_name, "validation_f1": best_f1, "test": metadata_doc["test_metrics"], "records": metadata_doc["records"]}, indent=2))


if __name__ == "__main__":
    main()
