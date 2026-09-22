"""Extract embedded images from supplier PDF/DOCX documents for product-image selection."""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.extract import ExtractError

# Skip tiny logos/icons; product photos are usually larger.
_MIN_SIDE = 48
_MIN_PIXELS = 48 * 48
_MAX_CANDIDATES = 24


@dataclass
class ExtractedImage:
    payload: bytes
    mime_type: str
    extension: str
    width: int
    height: int
    source_hint: str


def _normalize_image(raw: bytes, source_hint: str) -> ExtractedImage | None:
    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except (UnidentifiedImageError, OSError):
        return None
    image = image.convert("RGB")
    width, height = image.size
    if width < _MIN_SIDE or height < _MIN_SIDE or (width * height) < _MIN_PIXELS:
        return None
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return ExtractedImage(
        payload=buffer.getvalue(),
        mime_type="image/png",
        extension=".png",
        width=width,
        height=height,
        source_hint=source_hint,
    )


def _extract_from_pdf(payload: bytes) -> list[ExtractedImage]:
    try:
        reader = PdfReader(io.BytesIO(payload))
    except PdfReadError as exc:
        raise ExtractError("Unable to read PDF for image extraction.") from exc

    found: list[ExtractedImage] = []
    for page_index, page in enumerate(reader.pages):
        try:
            images = getattr(page, "images", None) or []
            for img_index, image_file in enumerate(images):
                data = getattr(image_file, "data", None)
                if not data:
                    continue
                normalized = _normalize_image(data, f"pdf:page{page_index + 1}:img{img_index + 1}")
                if normalized is not None:
                    found.append(normalized)
                    if len(found) >= _MAX_CANDIDATES:
                        return found
        except Exception:
            continue

        # Fallback: inspect XObject image streams when page.images is empty.
        try:
            resources = page.get("/Resources")
            if resources is None:
                continue
            xobject = resources.get("/XObject")
            if xobject is None:
                continue
            xobject = xobject.get_object()
            for name in xobject:
                obj = xobject[name].get_object()
                if obj.get("/Subtype") != "/Image":
                    continue
                try:
                    data = obj.get_data()
                except Exception:
                    continue
                normalized = _normalize_image(data, f"pdf:page{page_index + 1}:{name}")
                if normalized is not None:
                    found.append(normalized)
                    if len(found) >= _MAX_CANDIDATES:
                        return found
        except Exception:
            continue
    return found


def _extract_from_docx(payload: bytes) -> list[ExtractedImage]:
    found: list[ExtractedImage] = []
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            media_names = sorted(
                name
                for name in archive.namelist()
                if name.startswith("word/media/") and not name.endswith("/")
            )
            for name in media_names:
                try:
                    data = archive.read(name)
                except KeyError:
                    continue
                normalized = _normalize_image(data, f"docx:{name}")
                if normalized is not None:
                    found.append(normalized)
                    if len(found) >= _MAX_CANDIDATES:
                        break
    except zipfile.BadZipFile as exc:
        raise ExtractError("Unable to read DOCX for image extraction.") from exc
    return found


def extract_embedded_images(kind: str, payload: bytes) -> list[ExtractedImage]:
    """Return usable embedded images from a supplier document payload.

    kind: 'pdf' | 'docx' | 'txt'
    txt never yields images.
    """
    if not payload:
        return []
    if kind == "pdf":
        return _extract_from_pdf(payload)
    if kind == "docx":
        return _extract_from_docx(payload)
    return []
