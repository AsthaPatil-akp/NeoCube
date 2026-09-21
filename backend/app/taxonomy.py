from __future__ import annotations

import re
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Category

OTHER_NAME = "Other"
ProductFamilyStatus = Literal["known_compatible", "known_incompatible", "unknown"]

# Distinct product families used as a hard filter. Keywords are matched against
# normalized product text. This is not a special-case for any one test pair.
FAMILY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("solar", ("rooftop solar", "photovoltaic", "pv panel", "solar panel", "solar")),
    (
        "medical",
        (
            "patient monitoring",
            "medical device",
            "medical equipment",
            "diagnostic",
            "surgical",
            "hospital",
            "pharma",
            "medical",
        ),
    ),
    ("food", ("beverage", "grocery", "edible", "food")),
    ("software", ("software", "saas", "application license", "source code")),
    ("construction", ("construction material", "cement", "concrete", "rebar")),
    ("furniture", ("office furniture", "office chair", "furniture")),
    ("electronics", ("printed circuit", "circuit board", "semiconductor", "electronics")),
    ("steel", ("steel bracket", "steel", "aluminum", "metal")),
    ("textiles", ("textile", "fabric", "garment")),
    ("packaging", ("packaging", "carton", "corrugated")),
)


def normalize_label(value: str | None) -> str:
    if not value:
        return ""
    collapsed = re.sub(r"\s+", " ", value.strip().lower())
    collapsed = re.sub(r"[^a-z0-9& ]+", " ", collapsed)
    collapsed = re.sub(r"\s+", " ", collapsed).strip()
    tokens: list[str] = []
    for token in collapsed.split():
        if token.endswith("ies") and len(token) > 4:
            token = token[:-3] + "y"
        elif token.endswith("ses") and len(token) > 4:
            token = token[:-2]
        elif token.endswith("s") and not token.endswith("ss") and len(token) > 3:
            token = token[:-1]
        tokens.append(token)
    return " ".join(tokens)


def is_other_name(value: str | None) -> bool:
    return normalize_label(value) == normalize_label(OTHER_NAME)


def product_family(product: str | None) -> str | None:
    text = normalize_label(product)
    if not text:
        return None
    for family, keywords in FAMILY_KEYWORDS:
        for keyword in keywords:
            needle = normalize_label(keyword)
            if needle and needle in text:
                return family
    return None


def product_compatibility(left: str | None, right: str | None) -> tuple[bool, ProductFamilyStatus]:
    family_a = product_family(left)
    family_b = product_family(right)
    if family_a and family_b and family_a != family_b:
        return False, "known_incompatible"
    if family_a and family_b and family_a == family_b:
        return True, "known_compatible"
    return True, "unknown"


def effective_category_name(entity) -> str:
    custom = getattr(entity, "custom_category", None)
    if custom and str(custom).strip() and not is_other_name(custom):
        return str(custom).strip()
    category = getattr(entity, "category", None)
    if category is not None and getattr(category, "name", None):
        return str(category.name).strip()
    return ""


def categories_compatible(requirement, offering) -> bool:
    left = effective_category_name(requirement)
    right = effective_category_name(offering)
    if is_other_name(left) or is_other_name(right):
        return False
    if left and right:
        return normalize_label(left) == normalize_label(right)
    return requirement.category_id == offering.category_id and not is_other_name(left)


def get_or_create_named_category(db: Session, name: str) -> Category:
    label = re.sub(r"\s+", " ", name.strip())
    if not label or is_other_name(label):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Custom category is required when Other is selected",
        )
    existing = db.scalar(select(Category).where(func.lower(Category.name) == label.lower()))
    if existing is not None:
        return existing
    category = Category(name=label, is_active=True, is_predefined=False)
    db.add(category)
    db.flush()
    return category


def resolve_category(db: Session, category_id: int, custom_category: str | None) -> Category:
    category = db.get(Category, category_id)
    if category is None or not category.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid category")
    custom = (custom_category or "").strip()
    if is_other_name(category.name):
        if not custom:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Custom category is required when Other is selected",
            )
        return get_or_create_named_category(db, custom)
    if custom and not is_other_name(custom) and normalize_label(custom) != normalize_label(category.name):
        return get_or_create_named_category(db, custom)
    return category


def stored_custom_category(category: Category) -> str | None:
    if category.is_predefined and not is_other_name(category.name):
        return None
    if is_other_name(category.name):
        return None
    return category.name


def match_predefined_category(label: str, categories: list[tuple[int, str]]) -> int | None:
    wanted = normalize_label(label)
    if not wanted or wanted == normalize_label(OTHER_NAME):
        return None
    for category_id, name in categories:
        if is_other_name(name):
            continue
        if normalize_label(name) == wanted:
            return category_id
    return None


def other_category_id(categories: list[tuple[int, str]]) -> int | None:
    for category_id, name in categories:
        if is_other_name(name):
            return category_id
    return None
