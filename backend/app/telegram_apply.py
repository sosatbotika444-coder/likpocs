"""Applicant flow for the Telegram bot (aiogram-free, unit-testable).

Reuses the website's validation (``ApplicationDraftIn``, ``_apply_values``, ``validate_upload``,
``submit_application``) so both channels enforce identical rules.
"""

from __future__ import annotations

import io
from datetime import datetime, timedelta
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import admissions_api as adm
from app.audit import audit
from app.config import settings
from app.file_storage import storage, validate_upload
from app.models import (
    AdmissionCampaign, AdmissionInvitation, ApplicationFile, StudentApplication, TelegramAccount, utcnow,
)
from app.schemas import ApplicationDraftIn

APPLICATION_STEPS: tuple[tuple[str, str], ...] = (
    ("first_name_latin", "Ismingizni lotin harflarida yozing:"),
    ("last_name_latin", "Familiyangizni lotin harflarida yozing:"),
    ("birth_date", "Tug‘ilgan sanangizni yozing (KK.OO.YYYY, masalan 11.04.2005):"),
    ("phone", "Telefon raqamingizni yozing (masalan +998901234567):"),
    ("institution", "Ta’lim muassasangiz nomini yozing:"),
    ("requested_move_in", "Ko‘chib kirish sanasini yozing (KK.OO.YYYY):"),
)
DATE_KEYS = {"birth_date", "requested_move_in"}


def upsert_account(db: Session, chat_id: int, tg_user_id: int | None, username: str, full_name: str) -> TelegramAccount:
    account = db.scalar(select(TelegramAccount).where(TelegramAccount.chat_id == chat_id))
    if account is None:
        account = TelegramAccount(chat_id=chat_id)
        db.add(account)
    account.telegram_user_id = tg_user_id
    account.username = (username or "")[:64]
    account.full_name = (full_name or "")[:200]
    account.is_active = True
    return account


def start_application(db: Session, chat_id: int, tg_user_id: int | None, username: str, full_name: str, token: str) -> StudentApplication:
    """Open (or resume) a draft application from an invitation token, bound to this chat."""
    invitation = db.scalar(select(AdmissionInvitation).where(AdmissionInvitation.token_hash == adm._digest(token)).with_for_update())
    if not invitation or adm._invitation_status(invitation) != "ACTIVE":
        raise HTTPException(status_code=404, detail="Taklif havolasi muddati tugagan yoki bekor qilingan.")
    campaign = db.get(AdmissionCampaign, invitation.campaign_id)
    if not campaign or campaign.status != "ACTIVE":
        raise HTTPException(status_code=404, detail="Qabul kampaniyasi faol emas.")
    key_hash = adm._digest(f"{invitation.id}:telegram:{chat_id}")
    application = db.scalar(select(StudentApplication).where(StudentApplication.exchange_key_hash == key_hash))
    if application is None:
        application = StudentApplication(
            reference=f"DF-{utcnow():%y%m}-{uuid4().hex[:6].upper()}", invitation_id=invitation.id,
            exchange_key_hash=key_hash, campaign_id=campaign.id, dormitory_id=invitation.dormitory_id,
            consent_version=campaign.consent_version,
        )
        db.add(application)
        db.flush()
        adm._event(db, application, "DRAFT", None)
        audit(db, None, "APPLICATION_DRAFT_CREATED", "StudentApplication", application.id, {"via": "TELEGRAM"})
    account = upsert_account(db, chat_id, tg_user_id, username, full_name)
    account.application_id, account.user_id = application.id, None
    db.commit()
    return application


def parse_date(text: str) -> str:
    value = text.strip()
    for pattern in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, pattern).date().isoformat()
        except ValueError:
            continue
    raise ValueError("Sana formati noto‘g‘ri. Masalan: 11.04.2005")


def save_answer(db: Session, application: StudentApplication, key: str, text: str) -> None:
    """Validate one answer with the website's rules and store it on the draft."""
    if application.status != "DRAFT":
        raise ValueError("Ushbu arizani Telegram orqali tahrirlab bo‘lmaydi.")
    value = parse_date(text) if key in DATE_KEYS else text.strip()
    if not value:
        raise ValueError("Qiymat bo‘sh bo‘lmasligi kerak.")
    try:
        adm._apply_values(db, application, ApplicationDraftIn(**{key: value}), partial=True)
    except ValidationError as exc:
        raise ValueError(str(exc.errors()[0].get("msg", "Qiymat noto‘g‘ri."))) from None
    except HTTPException as exc:
        raise ValueError(str(exc.detail)) from None
    audit(db, None, "APPLICATION_DRAFT_UPDATED", "StudentApplication", application.id, {"changed_fields": [key], "via": "TELEGRAM"})
    db.commit()


def missing_files(db: Session, application: StudentApplication) -> list[tuple[str, str]]:
    """Return (kind, document_type) pairs still required before submission."""
    campaign = db.get(AdmissionCampaign, application.campaign_id)
    files = db.scalars(select(ApplicationFile).where(ApplicationFile.application_id == application.id, ApplicationFile.deleted_at.is_(None))).all()
    missing: list[tuple[str, str]] = []
    if not any(item.kind == "PHOTO" for item in files):
        missing.append(("PHOTO", ""))
    for doc in (campaign.document_types if campaign else []):
        if not any(item.kind == "DOCUMENT" and item.document_type == doc for item in files):
            missing.append(("DOCUMENT", doc))
    return missing


def attach_file(db: Session, application: StudentApplication, kind: str, document_type: str, content: bytes, filename: str) -> None:
    """Store a Telegram upload privately with the website's validation (no OCR/AI in the bot)."""
    if application.status != "DRAFT":
        raise ValueError("Ushbu arizaga fayl qo‘shib bo‘lmaydi.")
    if not storage.configured():
        raise ValueError("Fayl ombori sozlanmagan.")
    try:
        content_type, safe_name = validate_upload(UploadFile(filename=filename, file=io.BytesIO(content)), content)
    except HTTPException as exc:
        raise ValueError(str(exc.detail)) from None
    if kind == "PHOTO" and not content_type.startswith("image/"):
        raise ValueError("Surat uchun rasm yuboring.")
    suffix = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "application/pdf": ".pdf"}[content_type]
    doc_type = document_type if kind == "DOCUMENT" else ""
    now = utcnow()
    for previous in db.scalars(select(ApplicationFile).where(
        ApplicationFile.application_id == application.id, ApplicationFile.kind == kind,
        ApplicationFile.document_type == doc_type, ApplicationFile.deleted_at.is_(None),
    )).all():
        previous.deleted_at, previous.delete_after, previous.ai_status, previous.extracted_data = now, now, "DELETED", {}
        if storage.backend == "postgres":
            storage.delete(previous.object_key, db=db)
    retention = settings.file_retention_days
    row = ApplicationFile(
        application_id=application.id, kind=kind, document_type=doc_type,
        object_key=f"admissions/{application.id}/{uuid4().hex}{suffix}", original_name=safe_name, content_type=content_type,
        size_bytes=len(content), scan_status="NOT_CONFIGURED", ai_status="NOT_CONFIGURED", extracted_data={},
        delete_after=now + timedelta(days=retention) if retention else None, uploaded_at=now,
    )
    db.add(row)
    db.flush()
    storage.put(row.object_key, content, content_type, db=db)
    audit(db, None, "APPLICATION_FILE_UPLOADED", "ApplicationFile", row.id, {"kind": kind, "document_type": doc_type, "via": "TELEGRAM"})
    db.commit()


def applicant_profile(db: Session, chat_id: int) -> dict[str, str] | None:
    """Return only the applicant data belonging to this Telegram chat, never private uploads."""
    account = db.scalar(select(TelegramAccount).where(
        TelegramAccount.chat_id == chat_id, TelegramAccount.is_active.is_(True),
        TelegramAccount.application_id.is_not(None),
    ))
    if not account or not account.application_id:
        return None
    application = db.get(StudentApplication, account.application_id)
    if application is None:
        return None
    return {
        "reference": application.reference, "status": application.status,
        "first_name": application.first_name_latin or "", "last_name": application.last_name_latin or "",
        "birth_date": application.birth_date.isoformat() if application.birth_date else "",
        "phone": application.phone or "", "institution": application.institution or "",
        "requested_move_in": application.requested_move_in.isoformat() if application.requested_move_in else "",
        "signature_name": application.contract_signature_name or "",
        "contract_signed": "yes" if application.contract_accepted_at else "no",
    }

