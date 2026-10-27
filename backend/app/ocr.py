from __future__ import annotations

import io
import logging
import math
import re
import shutil
import threading
from dataclasses import dataclass
from datetime import date
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


_IDENTITY_LABELS: dict[str, tuple[str, ...]] = {
    "last_name_latin": (r"surname", r"family\s+name", r"last\s+name", r"familiya(?:si)?", r"фамилия"),
    "first_name_latin": (r"given\s+names?", r"first\s+name", r"ism(?:i)?", r"имя"),
    "middle_name_latin": (r"patronymic", r"middle\s+name", r"father['’]?s\s+name", r"otasining\s+ismi", r"отчество"),
    "birth_date": (r"date\s+of\s+birth", r"birth\s+date", r"tug['’‘ʻʼ`]?ilgan\s+sana(?:si)?", r"дата\s+рождения"),
    "gender": (r"sex", r"gender", r"jinsi", r"пол"),
    "nationality": (r"nationality", r"citizenship", r"fuqaroligi", r"гражданство"),
    "address": (r"address", r"manzil", r"адрес"),
}
_IDENTITY_LABEL_ONLY = tuple(
    re.compile(r"^(?:" + label + r")$", re.IGNORECASE)
    for labels in _IDENTITY_LABELS.values()
    for label in labels
)


def _is_identity_label(value: str) -> bool:
    parts = [
        re.sub(r"^\s*\d+[.)]\s*", "", part).strip(" \t;#№.,\\-–—")
        for part in re.split(r"[/|:]+", value)
    ]
    parts = [part for part in parts if part]
    return bool(parts) and all(any(pattern.fullmatch(part) for pattern in _IDENTITY_LABEL_ONLY) for part in parts)


def _clean_identity_value(value: str) -> str:
    value = re.sub(r"^[\s:;#№.,/\\|–—-]+|[\s:;#№.,/\\|–—-]+$", "", value)
    value = re.sub(r"\s+", " ", value)
    if len(value) > 120 or _is_identity_label(value):
        return ""
    return value.strip()


def _mrz_identity(lines: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    compact = [re.sub(r"\s+", "", line).upper() for line in lines]
    for index, line in enumerate(compact):
        if not line.startswith("P<") or "<<" not in line:
            continue
        names = line.split("<<", 1)
        surname = names[0][5:].replace("<", " ").strip()
        given_names = [name for name in names[1].split("<") if name]
        given = given_names[0] if given_names else ""
        if surname and re.fullmatch(r"[A-Z -]+", surname):
            result["last_name_latin"] = surname
        if given and re.fullmatch(r"[A-Z -]+", given):
            result["first_name_latin"] = given
        if len(given_names) > 1 and re.fullmatch(r"[A-Z -]+", given_names[-1]) and re.search(r"(?:OVICH|EVICH|OVNA|EVNA|QIZI|KIZI|OGLI|UGLI)$", given_names[-1]):
            result["middle_name_latin"] = given_names[-1]
        if index + 1 < len(compact):
            detail = compact[index + 1]
            # ICAO TD3 passports place birth date and sex at fixed positions.
            if len(detail) >= 21 and detail[13:19].isdigit():
                yy, month, day = detail[13:15], detail[15:17], detail[17:19]
                year = int(yy)
                century = 2000 if year <= int(date.today().strftime("%y")) else 1900
                birth_date = f"{century + year:04d}-{month}-{day}"
                try:
                    date.fromisoformat(birth_date)
                    result["birth_date"] = birth_date
                except ValueError:
                    pass
                sex = detail[20:21]
                if sex in {"M", "F"}:
                    result["gender"] = "MALE" if sex == "M" else "FEMALE"
        break
    return result


def extract_identity_fields(text: str | None) -> dict[str, str]:
    """Extract a small set of labeled identity fields without returning OCR text."""
    if not text:
        return {}
    lines = [re.sub(r"^\s*(?:\d+[.)](?=\s*[A-Za-z\u0400-\u04FF])\s*|[•*]\s*)", "", line).strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    result = _mrz_identity(lines)
    cyrillic_fields = {
        "first_name_latin": "first_name_cyrillic",
        "last_name_latin": "last_name_cyrillic",
        "middle_name_latin": "middle_name_cyrillic",
    }
    for field, labels in _IDENTITY_LABELS.items():
        label_regex = re.compile(r"(?:" + "|".join(f"(?:{label})" for label in labels) + r")", re.IGNORECASE)
        for index, line in enumerate(lines):
            match = label_regex.search(line)
            if not match:
                continue
            remainder = re.sub(r"^[\s:;#№.,/\\|–—-]+", "", line[match.end():]).strip()
            value = _clean_identity_value(remainder)
            if not value:
                for candidate in lines[index + 1:index + 3]:
                    if _is_identity_label(candidate):
                        continue
                    value = _clean_identity_value(candidate)
                    if value:
                        break
            if field == "birth_date":
                date_match = re.search(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b|\b(\d{4})[./-](\d{1,2})[./-](\d{1,2})\b", value)
                if date_match:
                    if date_match.group(1):
                        day, month, year = date_match.group(1, 2, 3)
                    else:
                        year, month, day = date_match.group(4, 5, 6)
                    if 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
                        candidate_date = f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
                        try:
                            date.fromisoformat(candidate_date)
                            value = candidate_date
                        except ValueError:
                            value = ""
                    else:
                        value = ""
                else:
                    value = ""
            elif field == "gender":
                normalized = value.upper()
                if re.search(r"\b(?:M|MALE|ERKAK|МУЖСКОЙ)\b", normalized):
                    value = "MALE"
                elif re.search(r"\b(?:F|FEMALE|AYOL|ЖЕНСКИЙ)\b", normalized):
                    value = "FEMALE"
                else:
                    value = ""
            if value:
                target = field
                if field in cyrillic_fields and re.search(r"[\u0400-\u04FF]", value):
                    target = cyrillic_fields[field]
                if target not in result:
                    result[target] = value
                    break
    return result


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
