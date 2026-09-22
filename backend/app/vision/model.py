"""Custom CNN for NeoCube product image classification and embeddings."""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

from app.vision.config import EMBEDDING_DIM


class ProductVisionCNN(nn.Module):
    """Three-block CNN with global average pooling and an embedding head.

    Forward path: image → conv blocks → GAP → projection → classifier logits.
    Embedding path: same trunk → L2-normalized embedding vector.
    """

    def __init__(self, num_classes: int, embedding_dim: int = EMBEDDING_DIM) -> None:
        super().__init__()
        if num_classes < 2:
            raise ValueError("num_classes must be at least 2")
        self.num_classes = num_classes
        self.embedding_dim = embedding_dim

        self.block1 = nn.Sequential(
            nn.Conv2d(3, 32, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
        )
        self.block2 = nn.Sequential(
            nn.Conv2d(32, 64, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
        )
        self.block3 = nn.Sequential(
            nn.Conv2d(64, 128, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(128),
            nn.ReLU(inplace=True),
            nn.AdaptiveAvgPool2d(1),
        )
        self.embedding_proj = nn.Linear(128, embedding_dim)
        self.classifier = nn.Linear(embedding_dim, num_classes)

    def forward_features(self, x: torch.Tensor) -> torch.Tensor:
        x = self.block1(x)
        x = self.block2(x)
        x = self.block3(x)
        return x.flatten(1)

    def embedding(self, x: torch.Tensor) -> torch.Tensor:
        feat = self.forward_features(x)
        emb = self.embedding_proj(feat)
        return F.normalize(emb, p=2, dim=1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        feat = self.forward_features(x)
        emb = self.embedding_proj(feat)
        return self.classifier(emb)
