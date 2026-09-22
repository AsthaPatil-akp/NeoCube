"""Evaluation metrics for the product-vision CNN on the held-out test split."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader

from app.vision.config import VISION_CLASSES, vision_dataset_dir
from app.vision.dataset import ProductImageFolder
from app.vision.model_store import load_vision_model, model_metadata_path


def evaluate(dataset_root: Path | None = None, batch_size: int = 32) -> dict:
    bundle = load_vision_model()
    if bundle is None:
        raise FileNotFoundError("Trained vision model is not available")

    root = Path(dataset_root) if dataset_root else vision_dataset_dir()
    test_ds = ProductImageFolder(root / "test", train=False, image_size=bundle.image_size)
    loader = DataLoader(test_ds, batch_size=batch_size, shuffle=False, num_workers=0)

    all_preds: list[int] = []
    all_labels: list[int] = []
    model = bundle.model
    model.eval()
    with torch.no_grad():
        for images, labels in loader:
            images = images.to(bundle.device)
            logits = model(images)
            preds = logits.argmax(dim=1).cpu().numpy().tolist()
            all_preds.extend(preds)
            all_labels.extend(labels.numpy().tolist())

    y_true = np.asarray(all_labels)
    y_pred = np.asarray(all_preds)
    num_classes = len(VISION_CLASSES)
    confusion = np.zeros((num_classes, num_classes), dtype=int)
    for t, p in zip(y_true, y_pred):
        confusion[t, p] += 1

    per_class: dict[str, dict[str, float]] = {}
    precisions = []
    recalls = []
    f1s = []
    for idx, name in enumerate(VISION_CLASSES):
        tp = confusion[idx, idx]
        fp = confusion[:, idx].sum() - tp
        fn = confusion[idx, :].sum() - tp
        precision = float(tp / (tp + fp)) if (tp + fp) else 0.0
        recall = float(tp / (tp + fn)) if (tp + fn) else 0.0
        f1 = float(2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        per_class[name] = {"precision": precision, "recall": recall, "f1": f1, "support": int(confusion[idx].sum())}
        precisions.append(precision)
        recalls.append(recall)
        f1s.append(f1)

    accuracy = float((y_true == y_pred).mean()) if len(y_true) else 0.0
    report = {
        "model_version": bundle.version,
        "accuracy": accuracy,
        "macro_precision": float(np.mean(precisions)) if precisions else 0.0,
        "macro_recall": float(np.mean(recalls)) if recalls else 0.0,
        "macro_f1": float(np.mean(f1s)) if f1s else 0.0,
        "confusion_matrix": confusion.tolist(),
        "per_class": per_class,
        "n_test": int(len(y_true)),
        "class_names": list(VISION_CLASSES),
        "training_history": bundle.metadata.get("history"),
        "best_val_accuracy": bundle.metadata.get("best_val_accuracy"),
    }

    out_path = model_metadata_path().with_name("product_vision_cnn_v1.eval.json")
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate NeoCube product-vision CNN")
    parser.add_argument("--dataset", type=str, default=None)
    args = parser.parse_args()
    report = evaluate(Path(args.dataset) if args.dataset else None)
    print(json.dumps({k: report[k] for k in ("accuracy", "macro_f1", "n_test", "model_version")}, indent=2))


if __name__ == "__main__":
    main()
