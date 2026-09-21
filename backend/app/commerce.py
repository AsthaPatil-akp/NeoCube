from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

CURRENCY_COMPARISON_UNAVAILABLE = "CURRENCY_COMPARISON_UNAVAILABLE"
LEGACY_UNSPECIFIED = "LEGACY_UNSPECIFIED"

SUPPORTED_CURRENCIES = ("INR", "USD", "EUR", "GBP", "AED")
BASIS_TOTAL = "TOTAL"
BASIS_PER_UNIT = "PER_UNIT"
PriceBasis = Literal["TOTAL", "PER_UNIT"]

SYMBOL_TO_CODE = {
    "₹": "INR",
    "rs": "INR",
    "rs.": "INR",
    "rupee": "INR",
    "rupees": "INR",
    "$": "USD",
    "usd": "USD",
    "€": "EUR",
    "eur": "EUR",
    "£": "GBP",
    "gbp": "GBP",
    "aed": "AED",
}

CODE_RE = re.compile(r"\b(INR|USD|EUR|GBP|AED|JPY|CNY|AUD|CAD|SGD|CHF)\b", re.IGNORECASE)
AMOUNT_RE = re.compile(r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)")
LAKH_RE = re.compile(r"(\d+(?:\.\d+)?)\s*lakh", re.IGNORECASE)
PER_UNIT_RE = re.compile(r"\bper\s*units?\b|\bunit\s*price\b|\beach\b|\b/unit\b", re.IGNORECASE)
TOTAL_RE = re.compile(r"\btotal\b|\blump\s*sum\b|\boverall\b", re.IGNORECASE)


@dataclass
class Money:
    amount: int | None
    currency: str | None
    basis: str | None


def normalize_currency(value: str | None) -> str | None:
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    lowered = raw.lower().rstrip(".")
    if lowered in SYMBOL_TO_CODE:
        return SYMBOL_TO_CODE[lowered]
    if raw in SYMBOL_TO_CODE:
        return SYMBOL_TO_CODE[raw]
    code = raw.upper()
    if re.fullmatch(r"[A-Z]{3}", code):
        return code
    return None


def normalize_basis(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip().upper().replace(" ", "_")
    if raw in {"TOTAL", "TOTAL_BUDGET", "LUMP_SUM", "OVERALL"}:
        return BASIS_TOTAL
    if raw in {"PER_UNIT", "PER_UNIT_BUDGET", "UNIT", "PERUNIT", "EACH"}:
        return BASIS_PER_UNIT
    if "PER_UNIT" in raw:
        return BASIS_PER_UNIT
    if "TOTAL" in raw:
        return BASIS_TOTAL
    return None


def parse_amount(text: str | None) -> int | None:
    if not text:
        return None
    lakh = LAKH_RE.search(text)
    if lakh:
        return int(float(lakh.group(1)) * 100_000)
    match = AMOUNT_RE.search(text)
    if not match:
        return None
    value = float(match.group(1).replace(",", ""))
    if value <= 0:
        return None
    return int(value)


def parse_currency_from_text(text: str | None) -> str | None:
    if not text:
        return None
    for symbol, code in SYMBOL_TO_CODE.items():
        if symbol in {"rs", "rs.", "rupee", "rupees", "usd", "eur", "gbp", "aed"}:
            if re.search(rf"\b{re.escape(symbol)}\b", text, flags=re.IGNORECASE):
                return code
        elif symbol and symbol in text:
            return code
    match = CODE_RE.search(text)
    if match:
        return match.group(1).upper()
    return None


def parse_basis_from_text(text: str | None) -> str | None:
    if not text:
        return None
    if PER_UNIT_RE.search(text):
        return BASIS_PER_UNIT
    if TOTAL_RE.search(text):
        return BASIS_TOTAL
    return None


def parse_money(text: str | None) -> Money:
    if not text:
        return Money(None, None, None)
    return Money(
        amount=parse_amount(text),
        currency=parse_currency_from_text(text),
        basis=parse_basis_from_text(text),
    )


def format_pricing_details(amount: int | None, currency: str | None, basis: str | None) -> str:
    parts: list[str] = []
    if currency:
        parts.append(currency)
    if amount is not None:
        parts.append(str(amount))
    if basis == BASIS_PER_UNIT:
        parts.append("per unit")
    elif basis == BASIS_TOTAL:
        parts.append("total")
    return " ".join(parts).strip()


def requirement_money(requirement) -> Money:
    amount = getattr(requirement, "budget", None)
    currency = normalize_currency(getattr(requirement, "budget_currency", None))
    basis = normalize_basis(getattr(requirement, "budget_basis", None))
    if basis is None:
        basis = BASIS_TOTAL
    return Money(amount=amount, currency=currency, basis=basis)


def offering_money(offering) -> Money:
    amount = getattr(offering, "price_amount", None)
    currency = normalize_currency(getattr(offering, "price_currency", None))
    basis = normalize_basis(getattr(offering, "price_basis", None))
    parsed = parse_money(getattr(offering, "pricing_details", None))
    if amount is None:
        amount = parsed.amount
    if currency is None:
        currency = parsed.currency
    if basis is None:
        basis = parsed.basis
    return Money(amount=amount, currency=currency, basis=basis)


def required_supplier_cost(quantity: int, supplier: Money) -> int | None:
    if supplier.amount is None:
        return None
    if supplier.basis == BASIS_TOTAL:
        return supplier.amount
    if supplier.basis == BASIS_PER_UNIT:
        return supplier.amount * quantity
    return None


def client_budget_cap(quantity: int, client: Money) -> int | None:
    if client.amount is None:
        return None
    if client.basis == BASIS_PER_UNIT:
        return client.amount * quantity
    return client.amount


def compare_commercial(quantity: int, client: Money, supplier: Money) -> tuple[bool | None, int | None, str | None]:
    """Deterministic budget/price comparison. Never invents exchange rates.

    Currency policy B: amounts are compared only when currencies are the same,
    or when one/both currencies are unspecified (legacy rows). Distinct known
    currencies are ineligible as CURRENCY_COMPARISON_UNAVAILABLE.
    """
    cost = required_supplier_cost(quantity, supplier)
    cap = client_budget_cap(quantity, client)
    if cost is None or cap is None:
        return None, cost, None
    if client.currency and supplier.currency and client.currency != supplier.currency:
        return False, cost, CURRENCY_COMPARISON_UNAVAILABLE
    status = None
    if not client.currency or not supplier.currency:
        status = LEGACY_UNSPECIFIED
    return cost <= cap, cost, status
