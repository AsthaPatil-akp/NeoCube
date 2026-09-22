"""Training loop for the NeoCube product-vision CNN."""

from __future__ import annotations

import argparse
import random
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from app.vision.config import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_EPOCHS,
    DEFAULT_LR,
    DEFAULT_SEED,
    EMBEDDING_DIM,
    IMAGE_SIZE,
    MODEL_VERSION,
    VISION_CLASSES,
    vision_dataset_dir,
    vision_model_dir,
)
from app.vision.dataset import ProductImageFolder
from app.vision.model import ProductVisionCNN
from app.vision.model_store import save_model


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def accuracy_from_logits(logits: torch.Tensor, targets: torch.Tensor) -> float:
    preds = logits.argmax(dim=1)
    return float((preds == targets).float().mean().item())


def run_epoch(
    model: ProductVisionCNN,
    loader: DataLoader,
    criterion: nn.Module,
    optimizer: torch.optim.Optimizer | None,
    device: torch.device,
) -> tuple[float, float]:
    training = optimizer is not None
    model.train(training)
    total_loss = 0.0
    total_acc = 0.0
    batches = 0
    for images, labels in loader:
        images = images.to(device)
        labels = labels.to(device)
        if training:
            optimizer.zero_grad(set_to_none=True)
        logits = model(images)
        loss = criterion(logits, labels)
        if training:
            loss.backward()
            optimizer.step()
        total_loss += float(loss.item())
        total_acc += accuracy_from_logits(logits.detach(), labels)
        batches += 1
    if batches == 0:
        return 0.0, 0.0
    return total_loss / batches, total_acc / batches


def train(
    dataset_root: Path | None = None,
    *,
    epochs: int = DEFAULT_EPOCHS,
    batch_size: int = DEFAULT_BATCH_SIZE,
    learning_rate: float = DEFAULT_LR,
    seed: int = DEFAULT_SEED,
    image_size: int = IMAGE_SIZE,
) -> dict:
    set_seed(seed)
    root = Path(dataset_root) if dataset_root else vision_dataset_dir()
    train_ds = ProductImageFolder(root / "train", train=True, image_size=image_size)
    val_ds = ProductImageFolder(root / "validation", train=False, image_size=image_size)
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False, num_workers=0)

    device = torch.device("cpu")
    model = ProductVisionCNN(num_classes=len(VISION_CLASSES), embedding_dim=EMBEDDING_DIM).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)

    history: list[dict] = []
    best_val_acc = -1.0
    best_state = None

    for epoch in range(1, epochs + 1):
        train_loss, train_acc = run_epoch(model, train_loader, criterion, optimizer, device)
        val_loss, val_acc = run_epoch(model, val_loader, criterion, None, device)
        history.append(
            {
                "epoch": epoch,
                "train_loss": train_loss,
                "train_acc": train_acc,
                "val_loss": val_loss,
                "val_acc": val_acc,
            }
        )
        if val_acc >= best_val_acc:
            best_val_acc = val_acc
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}

    if best_state is not None:
        model.load_state_dict(best_state)

    metadata = {
        "model_version": MODEL_VERSION,
        "architecture": "ProductVisionCNN",
        "class_names": list(VISION_CLASSES),
        "image_size": image_size,
        "embedding_dim": EMBEDDING_DIM,
        "training_date": datetime.now(timezone.utc).isoformat(),
        "dataset_version": "synthetic_geometric_v1",
        "dataset_root": str(root.resolve()),
        "epochs": epochs,
        "batch_size": batch_size,
        "learning_rate": learning_rate,
        "seed": seed,
        "best_val_accuracy": best_val_acc,
        "history": history,
        "trained": True,
    }
    vision_model_dir().mkdir(parents=True, exist_ok=True)
    save_model(model, metadata)
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description="Train NeoCube product-vision CNN")
    parser.add_argument("--dataset", type=str, default=None)
    parser.add_argument("--epochs", type=int, default=DEFAULT_EPOCHS)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--lr", type=float, default=DEFAULT_LR)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--image-size", type=int, default=IMAGE_SIZE)
    args = parser.parse_args()
    meta = train(
        Path(args.dataset) if args.dataset else None,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.lr,
        seed=args.seed,
        image_size=args.image_size,
    )
    print(f"Saved {MODEL_VERSION} best_val_accuracy={meta['best_val_accuracy']:.4f}")


if __name__ == "__main__":
    main()
