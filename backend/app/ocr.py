from __future__ import annotations

import io
import logging
import math
import re
import shutil
import threading
from dataclasses import dataclass
from functools import lru_cache

import pymupdf
import pytesseract
from PIL import Image, ImageOps

from app.config import settings

logger = logging.getLogger(__name__)
_OCR_LOCK = threading.BoundedSemaphore(2)
_OCR_TEXT_LIMIT = 25_000
_NATIVE_TEXT_MIN_CHARS = 24


@dataclass(frozen=True)
class OCRResult:
    status: str
    text: str | None = None
    truncated: bool = False


@lru_cache(maxsize=16)
def _runtime_ready(binary: str, languages: str, enabled: bool) -> bool:
    if not enabled or not binary.strip() or not shutil.which(binary):
        return False
    pytesseract.pytesseract.tesseract_cmd = binary
    try:
        installed = set(pytesseract.get_languages(config=""))
    except Exception:
        return False
    requested = {language.strip() for language in languages.split("+") if language.strip()}
    return bool(requested) and requested.issubset(installed)


def ocr_configured() -> bool:
    return _runtime_ready(settings.ocr_binary, settings.ocr_languages, settings.ocr_enabled)


def _ocr_image(image: Image.Image) -> str:
    pytesseract.pytesseract.tesseract_cmd = settings.ocr_binary
    prepared = ImageOps.exif_transpose(image).convert("RGB")
    return pytesseract.image_to_string(
        prepared,
        lang=settings.ocr_languages,
        config="--psm 6",
        timeout=settings.ocr_page_timeout_seconds,
    )


def _clean_text(value: str) -> str:
    return value.replace("\x00", "").replace("\x0c", "\n").strip()


def _finish(text: str, truncated: bool = False) -> OCRResult:
    cleaned = _clean_text(text)
    if len(cleaned) > _OCR_TEXT_LIMIT:
        cleaned = cleaned[:_OCR_TEXT_LIMIT].rstrip()
        truncated = True
    if not cleaned:
        return OCRResult("PARTIAL" if truncated else "NO_TEXT", truncated=truncated)
    return OCRResult("PARTIAL" if truncated else "COMPLETED", cleaned, truncated)


def extract_document_text(content: bytes, content_type: str) -> OCRResult:
    """Run bounded, local-only OCR for an application document.

    OCR is a review aid. The text is deliberately not written to logs and is
    never used to make admission decisions.
    """
    if not ocr_configured():
        return OCRResult("NOT_CONFIGURED")

    text_parts: list[str] = []
    was_truncated = False
    try:
        with _OCR_LOCK:
            if content_type == "application/pdf":
                with pymupdf.open(stream=content, filetype="pdf") as document:
                    if document.needs_pass or document.page_count == 0:
                        return OCRResult("FAILED")
                    page_count = min(document.page_count, settings.ocr_max_pages)
                    was_truncated = document.page_count > page_count
                    for page_index in range(page_count):
                        page = document.load_page(page_index)
                        native_text = page.get_text("text")
                        if len(re.sub(r"\s", "", native_text)) >= _NATIVE_TEXT_MIN_CHARS:
                            text_parts.append(native_text)
                            continue
                        page_rect = page.rect
                        rendered_width = math.ceil(page_rect.width * 200 / 72)
                        rendered_height = math.ceil(page_rect.height * 200 / 72)
                        if rendered_width <= 0 or rendered_height <= 0 or rendered_width * rendered_height > settings.ocr_max_pixels:
                            was_truncated = True
                            continue
                        pixmap = page.get_pixmap(dpi=200, colorspace=pymupdf.csGRAY, alpha=False)
                        if pixmap.width * pixmap.height > settings.ocr_max_pixels:
                            was_truncated = True
                            continue
                        rendered = Image.open(io.BytesIO(pixmap.tobytes("png")))
                        try:
                            text_parts.append(_ocr_image(rendered))
                        finally:
                            rendered.close()
            elif content_type.startswith("image/"):
                with Image.open(io.BytesIO(content)) as image:
                    if image.width * image.height > settings.ocr_max_pixels:
                        return OCRResult("PARTIAL", truncated=True)
                    text_parts.append(_ocr_image(image))
            else:
                return OCRResult("SKIPPED")
    except (pytesseract.TesseractNotFoundError, pytesseract.TesseractError, RuntimeError, OSError, ValueError) as exc:
        logger.warning("Local OCR failed for an uploaded document (%s).", type(exc).__name__)
        if text_parts:
            return _finish("\n\n".join(text_parts), truncated=True)
        return OCRResult("FAILED")
    except Exception as exc:
        # Malformed images/PDFs and parser-specific failures must not reject or
        # expose the original upload; staff can still review it manually.
        logger.warning("Could not parse an uploaded document for OCR (%s).", type(exc).__name__)
        return OCRResult("FAILED")

    return _finish("\n\n".join(text_parts), truncated=was_truncated)
