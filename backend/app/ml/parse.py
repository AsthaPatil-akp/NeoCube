from __future__ import annotations

import re


def parse_days(text: str | None) -> int | None:
    if not text:
        return None
    match = re.search(r"(\d+)\s*(day|days|week|weeks|month|months)", text, flags=re.IGNORECASE)
    if not match:
        return None
    value = int(match.group(1))
    unit = match.group(2).lower()
    if unit.startswith("week"):
        return value * 7
    if unit.startswith("month"):
        return value * 30
    return value


def parse_unit_price(text: str | None) -> int | None:
    if not text:
        return None
    lakh = re.search(r"(\d+(?:\.\d+)?)\s*lakh", text, flags=re.IGNORECASE)
    if lakh:
        return int(float(lakh.group(1)) * 100_000)
    match = re.search(r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)", text)
    if not match:
        return None
    raw = match.group(1).replace(",", "")
    value = float(raw)
    if value <= 0:
        return None
    return int(value)


def location_overlap(left: str, right: str) -> float:
    a = {part for part in re.split(r"[^a-z0-9]+", left.lower()) if len(part) > 2}
    b = {part for part in re.split(r"[^a-z0-9]+", right.lower()) if len(part) > 2}
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)
