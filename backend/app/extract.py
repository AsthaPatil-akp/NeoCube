from __future__ import annotations

import io
import json
import re
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.commerce import normalize_basis, parse_amount, parse_basis_from_text, parse_currency_from_text, parse_money
from app.ml.parse import parse_days
from app.taxonomy import is_other_name, match_predefined_category, other_category_id

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
MAX_NOTES_LENGTH = 2000

PDF_MIME = {"application/pdf"}
DOCX_MIME = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/zip",
    "application/octet-stream",
}
TXT_MIME = {"text/plain", "application/octet-stream", "text/txt"}

# Longest labels first so "quantity unit" wins over "quantity".
LABEL_SPECS: tuple[tuple[str, str], ...] = (
    ("company", r"company\s*/\s*client\s*name"),
    ("company", r"client\s*/\s*company\s*name"),
    ("company", r"company\s*/\s*supplier\s*name"),
    ("company", r"supplier\s*/\s*company\s*name"),
    ("company", r"company\s*name"),
    ("company", r"client\s*name"),
    ("company", r"supplier\s*name"),
    ("quantity_unit", r"quantity\s*unit"),
    ("quantity", r"quantity\s*required"),
    ("quantity", r"available\s*quantity"),
    ("budget_basis", r"budget\s*basis"),
    ("budget", r"budget\s*amount"),
    ("price_basis", r"pricing\s*basis"),
    ("price_basis", r"price\s*basis"),
    ("price", r"pricing\s*amount"),
    ("price", r"pricing\s*details"),
    ("price", r"price\s*amount"),
    ("price", r"unit\s*price"),
    ("price", r"total\s*price"),
    ("product", r"product\s*requirement"),
    ("product", r"product\s*offered"),
    ("delivery", r"delivery\s*timeline"),
    ("delivery", r"delivery\s*capability"),
    ("notes", r"additional\s*notes"),
    ("category", r"intended\s*category"),
    ("company", r"\bcompany\b"),
    ("company", r"\bclient\b"),
    ("company", r"\bsupplier\b"),
    ("category", r"\bcategory\b"),
    ("product", r"\bproduct\b"),
    ("quantity", r"\bquantity\b"),
    ("quantity", r"\bqty\b"),
    ("budget", r"\bbudget\b"),
    ("price", r"\bpricing\b"),
    ("price", r"\bprice\b"),
    ("currency", r"\bcurrency\b"),
    ("location", r"\blocation\b"),
    ("delivery", r"\bdelivery\b"),
    ("notes", r"\bnotes\b"),
)
_HEADING_VALUE_RE = re.compile(
    r"^(?:requirement|offering|client\s*[—\-]\s*supplier|field\s*value|demo|matchmaking|platform)\b",
    re.IGNORECASE,
)
_UNIT_STOPWORDS = {
    "days",
    "day",
    "inr",
    "usd",
    "eur",
    "gbp",
    "aed",
    "total",
    "budget",
    "amount",
    "required",
    "available",
    "per",
    "unit",
}
_LABEL_ALTERNATION = "|".join(f"(?:{pattern})" for _, pattern in LABEL_SPECS)
_FLAT_LABEL_RE = re.compile(rf"(?P<label>{_LABEL_ALTERNATION})\s*[:\-]?\s*", re.IGNORECASE)
_LINE_LABEL_RE = re.compile(rf"^(?P<label>{_LABEL_ALTERNATION})\s*[:\-]?\s*(?P<value>.*)$", re.IGNORECASE)


class ExtractError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def extension_of(filename: str) -> str:
    return Path(filename or "").suffix.lower()


def detect_kind(filename: str, content_type: str | None, payload: bytes) -> str:
    ext = extension_of(filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise ExtractError("Unsupported file type. Upload a PDF, DOCX, or TXT file.")
    if not payload:
        raise ExtractError("The uploaded file is empty.")

    mime = (content_type or "").split(";")[0].strip().lower()
    if ext == ".pdf":
        if not payload.startswith(b"%PDF"):
            raise ExtractError("The file is not a valid PDF.")
        if mime and mime not in PDF_MIME and mime != "application/octet-stream":
            raise ExtractError("The file content does not match a PDF.")
        return "pdf"
    if ext == ".docx":
        if not payload.startswith(b"PK"):
            raise ExtractError("The file is not a valid DOCX document.")
        if mime and mime not in DOCX_MIME:
            raise ExtractError("The file content does not match a DOCX document.")
        return "docx"
    if mime and mime not in TXT_MIME:
        raise ExtractError("The file content does not match a text file.")
    return "txt"


def _pdf_literal_strings(payload: bytes) -> str:
    parts = re.findall(rb"\((?:\\.|[^\\)])*\)", payload)
    decoded = []
    for part in parts:
        inner = part[1:-1].replace(b"\\n", b" ").replace(b"\\(", b"(").replace(b"\\)", b")")
        decoded.append(inner.decode("latin-1", errors="ignore"))
    return " ".join(decoded).strip()


def extract_text(kind: str, payload: bytes) -> str:
    try:
        if kind == "pdf":
            reader = PdfReader(io.BytesIO(payload))
            pages = [page.extract_text() or "" for page in reader.pages]
            text = "\n".join(pages).strip() or _pdf_literal_strings(payload)
        elif kind == "docx":
            from docx import Document

            document = Document(io.BytesIO(payload))
            text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        else:
            text = payload.decode("utf-8")
    except (PdfReadError, UnicodeDecodeError, ValueError, OSError) as exc:
        raise ExtractError("The document could not be read. Please enter the requirement manually.") from exc

    text = text.strip()
    if not text:
        raise ExtractError("No text could be extracted from the document.")
    return text


def _canonical_label_key(label: str) -> str | None:
    text = re.sub(r"\s+", " ", (label or "").strip())
    for key, pattern in LABEL_SPECS:
        if re.fullmatch(pattern, text, flags=re.IGNORECASE):
            return key
    return None


def _clean_field_value(value: str | None) -> str:
    text = re.sub(r"\s+", " ", (value or "")).strip(" .,:;-/")
    text = re.sub(r"^(?:field\s*value|field|value)\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^[—\-:/]+\s*", "", text)
    return text.strip(" .,:;-/")


def _is_plausible_value(key: str, value: str) -> bool:
    cleaned = _clean_field_value(value)
    if not cleaned:
        return False
    if _HEADING_VALUE_RE.match(cleaned):
        return False
    lowered = cleaned.lower()
    if key == "company" and re.search(r"\b(matchmaking|platform demo|field value)\b", lowered):
        return False
    if key == "product" and re.match(r"^(?:requirement|offered)\b", lowered):
        return False
    if key in {"price", "budget"} and not re.search(r"\d", cleaned):
        return False
    return True


def _normalize_unit(value: str | None) -> str | None:
    cleaned = _clean_field_value(value)
    if not cleaned:
        return None
    token = re.sub(r"[^A-Za-z]", "", cleaned.split()[0])
    if len(token) < 2 or len(token) > 20:
        return None
    if token.lower() in _UNIT_STOPWORDS:
        return None
    return token


def _is_label_line(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    match = _LINE_LABEL_RE.match(stripped)
    if not match:
        return False
    return not _clean_field_value(match.group("value"))


def _labeled_map(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    lines = [line.strip() for line in text.splitlines()]
    index = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        if not line:
            continue
        match = _LINE_LABEL_RE.match(line)
        if not match:
            continue
        key = _canonical_label_key(match.group("label"))
        if key is None:
            continue
        value = _clean_field_value(match.group("value"))
        if not _is_plausible_value(key, value) and index < len(lines) and not _is_label_line(lines[index]):
            next_match = _LINE_LABEL_RE.match(lines[index] or "")
            if next_match is None:
                value = _clean_field_value(lines[index])
                index += 1
        if _is_plausible_value(key, value) and key not in found:
            found[key] = _clean_field_value(value)

    flattened = _clean_field_value(text)
    matches = list(_FLAT_LABEL_RE.finditer(flattened))
    for position, match in enumerate(matches):
        key = _canonical_label_key(match.group("label"))
        if key is None or key in found:
            continue
        end = matches[position + 1].start() if position + 1 < len(matches) else len(flattened)
        value = _clean_field_value(flattened[match.end() : end])
        if _is_plausible_value(key, value):
            found[key] = value
    return found


def _parse_quantity(text: str) -> tuple[int | None, str | None]:
    labeled = _labeled_map(text)
    unit = _normalize_unit(labeled.get("quantity_unit"))
    if "quantity" in labeled:
        amount = parse_amount(labeled["quantity"])
        if unit is None:
            unit_match = re.search(r"\d[\d,]*\s*([A-Za-z]{2,20})", labeled["quantity"])
            unit = _normalize_unit(unit_match.group(1) if unit_match else None)
        return amount, unit
    match = re.search(
        r"(?:need|quantity|qty|available)[^\d]{0,24}(\d{1,3}(?:,\d{3})+|\d{4,7}|\d{1,3})(?!\s*(?:days?|day))",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        match = re.search(r"\b(\d{1,3}(?:,\d{3})+)\b", text)
    if not match:
        return None, unit
    value = int(match.group(1).replace(",", ""))
    return (value if value > 0 else None), unit


def _parse_budget_fields(text: str) -> dict:
    labeled = _labeled_map(text)
    snippet = labeled.get("budget") or labeled.get("price") or ""
    money = parse_money(snippet)
    amount = money.amount
    currency = money.currency or parse_currency_from_text(labeled.get("currency")) or parse_currency_from_text(text)
    basis = (
        normalize_basis(labeled.get("budget_basis"))
        or normalize_basis(labeled.get("price_basis"))
        or money.basis
        or parse_basis_from_text(text)
    )
    if amount is None:
        lakh = re.search(
            r"(?:₹|rs\.?|inr|budget[^\d]{0,18})?\s*(\d+(?:\.\d+)?)\s*lakh",
            text,
            flags=re.IGNORECASE,
        )
        rupee = re.search(
            r"(?:₹|rs\.?|inr|budget(?:\s*amount)?|pric(?:e|ing)(?:\s*(?:amount|details))?)\s*[:\-]?\s*(?:of\s*)?(\d{1,3}(?:,\d{3})+|\d{4,12})\s*(INR|USD|EUR|GBP|AED)?",
            text,
            flags=re.IGNORECASE,
        )
        if lakh:
            amount = int(float(lakh.group(1)) * 100_000)
        elif rupee:
            amount = int(rupee.group(1).replace(",", ""))
            if rupee.group(2):
                currency = currency or rupee.group(2).upper()
    return {
        "amount": amount,
        "currency": currency,
        "basis": basis,
    }


def _parse_timeline(text: str) -> str | None:
    labeled = _labeled_map(text)
    if "delivery" in labeled:
        days = parse_days(labeled["delivery"])
        if days is not None:
            return f"{days} days"
        return labeled["delivery"]
    match = re.search(r"(?:within|in|timeline[:\s]+)\s*(\d+)\s*(days?|weeks?|months?)", text, flags=re.IGNORECASE)
    if match:
        return f"{match.group(1)} {match.group(2).lower()}"
    match = re.search(r"\b(\d+\s*(?:days?|weeks?|months?))\b", text, flags=re.IGNORECASE)
    return match.group(1).lower() if match else None


def _parse_product(text: str) -> str | None:
    labeled = _labeled_map(text)
    if labeled.get("product"):
        product = re.sub(r"\s+", " ", labeled["product"]).strip(" .,")
        return product if 3 <= len(product) <= 300 else None
    match = re.search(
        r"(?:need|looking for|product[:\s]+)\s*(?:about\s+)?(\d[\d,]*)?\s*(.+?)(?:\s+within|\s+with\s+a\s+budget|\s+budget|\s+in\s+\d|\.|$)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    product = re.sub(r"\s+", " ", match.group(2)).strip(" .,")
    product = re.sub(r"^(?:of|for)\s+", "", product, flags=re.IGNORECASE)
    if len(product) < 3 or len(product) > 300:
        return None
    return product.title()


def _parse_location(text: str) -> str | None:
    labeled = _labeled_map(text)
    if labeled.get("location"):
        value = labeled["location"].strip(" .,")
        return value if len(value) >= 3 else None
    match = re.search(
        r"(?:location|delivered?\s+to|ship(?:ping)?\s+to)\s*[:\-]?\s*([A-Za-z][A-Za-z .,-]{2,80})",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    value = match.group(1).strip(" .,")
    if re.search(r"\d+\s*(days?|weeks?|months?)", value, flags=re.IGNORECASE):
        return None
    if len(value) < 3:
        return None
    return value


def _parse_company(text: str) -> str | None:
    labeled = _labeled_map(text)
    if labeled.get("company"):
        value = labeled["company"].strip(" .,")
        return value if 2 <= len(value) <= 200 else None
    return None


def _parse_notes(text: str) -> str | None:
    labeled = _labeled_map(text)
    if labeled.get("notes"):
        return labeled["notes"][:MAX_NOTES_LENGTH]
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= 40:
        return None
    return cleaned[:MAX_NOTES_LENGTH]


def infer_category_id(text: str, categories: list[tuple[int, str]]) -> int | None:
    lowered = text.lower()
    for category_id, name in categories:
        if is_other_name(name):
            continue
        if name.lower() in lowered:
            return category_id
    aliases = {
        "steel": "Steel & Metals",
        "metal": "Steel & Metals",
        "bracket": "Industrial Components",
        "electronic": "Electronics",
        "fabric": "Textiles",
        "textile": "Textiles",
        "packag": "Packaging",
        "raw material": "Raw Materials",
        "logistics": "Logistics",
        "shipping": "Logistics",
    }
    names = {name.lower(): category_id for category_id, name in categories if not is_other_name(name)}
    for needle, label in aliases.items():
        if needle in lowered and label.lower() in names:
            return names[label.lower()]
    return None


def extract_fields(text: str, categories: list[tuple[int, str]]) -> dict:
    fields: dict = {}
    labeled = _labeled_map(text)
    product = _parse_product(text)
    quantity, quantity_unit = _parse_quantity(text)
    budget_fields = _parse_budget_fields(text)
    timeline = _parse_timeline(text)
    location = _parse_location(text)
    notes = _parse_notes(text)
    company = _parse_company(text)

    category_label = labeled.get("category")
    category_id = None
    custom_category = None
    if category_label:
        category_id = match_predefined_category(category_label, categories)
        if category_id is None and not is_other_name(category_label):
            custom_category = category_label
            category_id = other_category_id(categories)
    else:
        category_id = infer_category_id(text, categories)

    if company:
        fields["company_name"] = company
    if product:
        fields["product_requirement"] = product
        fields["product"] = product
    if quantity:
        fields["quantity"] = quantity
    if quantity_unit:
        fields["quantity_unit"] = quantity_unit
    amount = budget_fields.get("amount")
    if amount is not None:
        fields["budget"] = amount
        fields["budget_amount"] = amount
        fields["price_amount"] = amount
    if budget_fields.get("currency"):
        fields["budget_currency"] = budget_fields["currency"]
        fields["price_currency"] = budget_fields["currency"]
    if budget_fields.get("basis"):
        fields["budget_basis"] = budget_fields["basis"]
        fields["price_basis"] = budget_fields["basis"]
    if labeled.get("price"):
        price_money = parse_money(labeled["price"])
        if price_money.amount is not None:
            fields["price_amount"] = price_money.amount
        if price_money.currency:
            fields["price_currency"] = price_money.currency
        price_basis = normalize_basis(labeled.get("price_basis")) or price_money.basis
        if price_basis:
            fields["price_basis"] = price_basis
    if labeled.get("currency") and "budget_currency" not in fields:
        labeled_currency = parse_currency_from_text(labeled["currency"])
        if labeled_currency:
            fields["budget_currency"] = labeled_currency
            fields["price_currency"] = labeled_currency
    if timeline:
        fields["delivery_timeline"] = timeline
        days = parse_days(timeline)
        if days is not None:
            fields["delivery_days"] = days
    if location:
        fields["location"] = location
    if notes:
        fields["additional_notes"] = notes
    if category_id:
        fields["category_id"] = category_id
    if category_label:
        fields["category_label"] = category_label
    if custom_category:
        fields["custom_category"] = custom_category
    return fields


def dumps_extracted(fields: dict) -> str:
    return json.dumps(fields)
