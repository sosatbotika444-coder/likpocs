from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.audit import audit, notify
from app.ai_extraction import (
    document_processing_available,
    document_processing_issue,
    extract_identity_document,
    local_ocr_available,
    openrouter_document_processing_available,
    openrouter_processing_issue,
)
from app.billing import create_initial_period
from app.config import settings
from app.db import get_db
from app.dependencies import get_current_user, require_operator
from app.file_storage import storage, validate_upload
from app.models import (
    AdmissionCampaign,
    AdmissionInvitation,
    ApplicationAccessSession,
    ApplicationFile,
    ApplicationStatusEvent,
    BillingPeriod,
    Dormitory,
    Payment,
    PaymentAdjustment,
    PublicRateLimit,
    Resident,
    ResidencePeriod,
    Room,
    StudentApplication,
    SystemSetting,
    User,
    utcnow,
)
from app.residency import assert_room_available, record_room_assignment
from app.schemas import (
    ApplicationApproveIn,
    ApplicationDraftIn,
    ApplicationFileOut,
    ApplicationNoteIn,
    ApplicationOut,
    ApplicationQueueOut,
    ApplicationRejectIn,
    ApplicationRequestInfoIn,
    ApplicationStatusEventOut,
    ApplicationStatusIn,
    ApplicationSubmitIn,
    AdmissionSummaryOut,
    CampaignCreate,
    CampaignOut,
    DormitoryCreate,
    DormitoryOut,
    DormitoryUpdate,
    InvitationCreate,
    InvitationExchangeIn,
    InvitationOut,
    PageInfo,
    PublicApplicationOut,
    PublicCampaignOut,
    PublicSessionOut,
    PublicStatusAccessIn,
    PublicStatusAccessOut,
    PublicStatusOut,
)

staff_router = APIRouter(prefix="/api")
public_router = APIRouter(prefix="/api/public")
logger = logging.getLogger(__name__)
SESSION_COOKIE = "dormflow.application"
SESSION_MAX_AGE = 60 * 60 * 24 * 30
PHONE_FIELDS = {"phone", "emergency_phone"}
EDITABLE_FIELDS = {
    "first_name_latin", "last_name_latin", "middle_name_latin", "first_name_cyrillic", "last_name_cyrillic",
    "middle_name_cyrillic", "birth_date", "nationality", "gender", "phone", "email", "address",
    "emergency_name", "emergency_phone", "institution", "faculty", "course", "study_group", "study_start",
    "study_end", "requested_move_in", "requested_move_out", "preferences", "additional_data",
}


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _require_staff(user: User) -> User:
    if user.role not in {"ADMIN", "OPERATOR"}:
        raise HTTPException(status_code=403, detail="Bu amal uchun ruxsatingiz yo‘q.")
    return user


def _rate_limit(db: Session, request: Request, scope: str, limit: int, window_seconds: int) -> None:
    now = utcnow()
    window_number = int(now.timestamp()) // window_seconds
    window_start = datetime.fromtimestamp(window_number * window_seconds, UTC)
    source = request.client.host if request.client else "unknown"
    bucket = hmac.new(settings.jwt_secret.encode("utf-8"), f"{scope}:{source}:{window_number}".encode("utf-8"), hashlib.sha256).hexdigest()
    values = {"bucket_hash": bucket, "window_start": window_start, "hits": 1}
    dialect = db.get_bind().dialect.name
    if dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert

        statement = insert(PublicRateLimit).values(**values).on_conflict_do_update(
            index_elements=[PublicRateLimit.bucket_hash], set_={"hits": PublicRateLimit.hits + 1}
        ).returning(PublicRateLimit.hits)
    elif dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert

        statement = insert(PublicRateLimit).values(**values).on_conflict_do_update(
            index_elements=[PublicRateLimit.bucket_hash], set_={"hits": PublicRateLimit.hits + 1}
        ).returning(PublicRateLimit.hits)
    else:
        entry = db.scalar(select(PublicRateLimit).where(PublicRateLimit.bucket_hash == bucket).with_for_update())
        if entry:
            entry.hits += 1
            hits = entry.hits
        else:
            db.add(PublicRateLimit(**values))
            hits = 1
        db.commit()
        if hits > limit:
            raise HTTPException(status_code=429, detail="So‘rovlar soni ko‘payib ketdi. Birozdan keyin urinib ko‘ring.")
        return
    hits = db.scalar(statement) or 1
    if window_number % 100 == 0:
        db.execute(delete(PublicRateLimit).where(PublicRateLimit.window_start < now - timedelta(days=2)))
    db.commit()
    if hits > limit:
        raise HTTPException(status_code=429, detail="So‘rovlar soni ko‘payib ketdi. Birozdan keyin urinib ko‘ring.")


def _invitation_status(invitation: AdmissionInvitation, now: datetime | None = None) -> str:
    current = now or utcnow()
    if invitation.revoked_at:
        return "REVOKED"
    if invitation.paused_at:
        return "PAUSED"
    if _aware(invitation.expires_at) <= current:
        return "EXPIRED"
    if invitation.submission_count >= invitation.max_submissions:
        return "EXHAUSTED"
    return "ACTIVE"


def _invite_out(invitation: AdmissionInvitation, link: str | None = None) -> InvitationOut:
    return InvitationOut(
        id=invitation.id,
        campaign_id=invitation.campaign_id,
        dormitory_id=invitation.dormitory_id,
        expires_at=invitation.expires_at,
        max_submissions=invitation.max_submissions,
        submission_count=invitation.submission_count,
        paused_at=invitation.paused_at,
        revoked_at=invitation.revoked_at,
        created_at=invitation.created_at,
        status=_invitation_status(invitation),
        link=link,
    )


def _event(db: Session, application: StudentApplication, to_status: str, actor: User | None, reason: str = "") -> None:
    old_status = application.status
    application.status = to_status
    db.add(ApplicationStatusEvent(
        application_id=application.id,
        actor_id=actor.id if actor else None,
        from_status=old_status,
        to_status=to_status,
        reason=reason,
    ))


def _phone(value: str) -> str:
    digits = "".join(character for character in value if character.isdigit())
    if len(digits) == 9:
        return f"+998{digits}"
    if len(digits) == 12 and digits.startswith("998"):
        return f"+{digits}"
    if value.strip().startswith("+") and 8 <= len(digits) <= 15:
        return f"+{digits}"
    if not digits and not value.strip():
        return ""
    raise HTTPException(status_code=422, detail="Telefon raqamini xalqaro formatda tekshiring.")


def _validate_extra(application: StudentApplication, values: dict, db: Session) -> None:
    campaign = db.get(AdmissionCampaign, application.campaign_id)
    allowed = {field.get("key") for field in (campaign.custom_fields if campaign else [])}
    extras = values.get("additional_data", application.additional_data or {})
    if not isinstance(extras, dict) or set(extras) - allowed:
        raise HTTPException(status_code=422, detail="Qo‘shimcha maydonlar ro‘yxatini tekshiring.")
    definitions = {field["key"]: field for field in (campaign.custom_fields if campaign else [])}
    for key, value in extras.items():
        definition = definitions[key]
        if definition.get("kind") == "select" and value not in definition.get("options", []):
            raise HTTPException(status_code=422, detail="Tanlangan qo‘shimcha maydon qiymati noto‘g‘ri.")
        if definition.get("kind") == "checkbox" and not isinstance(value, bool):
            raise HTTPException(status_code=422, detail="Belgilash maydoni noto‘g‘ri.")
        if value is not None and not isinstance(value, (str, bool)):
            raise HTTPException(status_code=422, detail="Qo‘shimcha maydon qiymati noto‘g‘ri.")


def _apply_values(db: Session, application: StudentApplication, payload: ApplicationDraftIn, *, partial: bool) -> None:
    values = payload.model_dump(exclude_unset=partial)
    if partial and application.status == "NEEDS_INFO":
        requested = set(application.requested_fields or [])
        for name in set(values) - {"additional_data"}:
            if name not in requested:
                raise HTTPException(status_code=403, detail="Faqat so‘ralgan maydonlarni o‘zgartirish mumkin.")
        if "additional_data" in values and "additional_data" not in requested:
            current = application.additional_data or {}
            updated = values["additional_data"]
            changed = {key for key in set(current) | set(updated) if current.get(key) != updated.get(key)}
            if "additional_data" not in requested and (changed - requested or not (set(updated) & requested)):
                raise HTTPException(status_code=403, detail="Faqat so‘ralgan maydonlarni o‘zgartirish mumkin.")
        if not values:
            raise HTTPException(status_code=403, detail="Faqat so‘ralgan maydonlarni o‘zgartirish mumkin.")
    _validate_extra(application, values, db)
    for field in set(values) & PHONE_FIELDS:
        values[field] = _phone(values[field])
    for field in values:
        setattr(application, field, values[field])
    application.updated_at = utcnow()


def _public_application(application: StudentApplication) -> PublicApplicationOut:
    return PublicApplicationOut.model_validate(application)


def _application(application: StudentApplication) -> ApplicationOut:
    return ApplicationOut.model_validate(application)


def _student_session(request: Request, db: Session, csrf_token: str | None = None) -> tuple[StudentApplication, ApplicationAccessSession]:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Ariza sessiyasi tugagan. Kirish kodini qayta kiriting.")
    session = db.scalar(
        select(ApplicationAccessSession).where(
            ApplicationAccessSession.token_hash == _digest(token),
            ApplicationAccessSession.revoked_at.is_(None),
        )
    )
    if not session or _aware(session.expires_at) <= utcnow():
        raise HTTPException(status_code=401, detail="Ariza sessiyasi tugagan. Kirish kodini qayta kiriting.")
    if csrf_token is not None and not hmac.compare_digest(session.csrf_hash, _digest(csrf_token)):
        raise HTTPException(status_code=403, detail="Xavfsizlik tekshiruvi bajarilmadi.")
    application = db.get(StudentApplication, session.application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Ariza topilmadi.")
    return application, session


def _student_write_session(request: Request, db: Session, csrf_token: str | None) -> tuple[StudentApplication, ApplicationAccessSession]:
    if not csrf_token:
        raise HTTPException(status_code=403, detail="Xavfsizlik tekshiruvi bajarilmadi.")
    return _student_session(request, db, csrf_token)


def _set_student_session(response: Response, db: Session, application: StudentApplication) -> str:
    raw_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    db.add(ApplicationAccessSession(
        application_id=application.id,
        token_hash=_digest(raw_token),
        csrf_hash=_digest(csrf_token),
        expires_at=utcnow() + timedelta(seconds=SESSION_MAX_AGE),
    ))
    db.commit()
    response.set_cookie(
        SESSION_COOKIE,
        raw_token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        path="/api/public",
    )
    return csrf_token


def _rotate_csrf(session: ApplicationAccessSession, db: Session) -> str:
    csrf_token = secrets.token_urlsafe(32)
    session.csrf_hash = _digest(csrf_token)
    db.commit()
    return csrf_token


def _public_campaign(campaign: AdmissionCampaign) -> PublicCampaignOut:
    return PublicCampaignOut(
        name=campaign.name,
        custom_fields=campaign.custom_fields,
        document_types=campaign.document_types,
        consent_version=campaign.consent_version,
        consent_text=campaign.consent_text,
        ai_processing_available=document_processing_available(),
        ai_processing_issue=document_processing_issue(),
        local_ocr_available=local_ocr_available(),
        external_ai_processing_available=openrouter_document_processing_available(),
    )


def _application_status(application: StudentApplication) -> PublicStatusOut:
    return PublicStatusOut(
        reference=application.reference,
        status=application.status,
        requested_fields=application.requested_fields,
        review_reason=application.review_reason,
    )


@staff_router.get("/dormitories", response_model=list[DormitoryOut])
def list_dormitories(include_inactive: bool = False, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[DormitoryOut]:
    _require_staff(user)
    if include_inactive and user.role != "OPERATOR":
        raise HTTPException(status_code=403, detail="Faol emas yotoqxonalar royxatini faqat operator koradi.")
    query = select(Dormitory)
    if not include_inactive:
        query = query.where(Dormitory.is_active.is_(True))
    rows = db.scalars(query.order_by(Dormitory.is_default.desc(), Dormitory.name)).all()
    return [DormitoryOut.model_validate(row) for row in rows]


@staff_router.post("/dormitories", response_model=DormitoryOut, status_code=201)
def create_dormitory(payload: DormitoryCreate, db: Session = Depends(get_db), user: User = Depends(require_operator)) -> DormitoryOut:
    row = Dormitory(name=payload.name.strip(), address=payload.address.strip())
    db.add(row)
    audit(db, user, "DORMITORY_CREATED", "Dormitory", row.id)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Bu yotoqxona nomi mavjud.") from None
    db.refresh(row)
    return DormitoryOut.model_validate(row)


@staff_router.patch("/dormitories/{dormitory_id}", response_model=DormitoryOut)
def update_dormitory(dormitory_id: UUID, payload: DormitoryUpdate, db: Session = Depends(get_db), user: User = Depends(require_operator)) -> DormitoryOut:
    row = db.get(Dormitory, dormitory_id)
    if not row:
        raise HTTPException(status_code=404, detail="Yotoqxona topilmadi.")
    values = payload.model_dump(exclude_unset=True)
    if values.get("is_active") is False:
        if row.is_default:
            raise HTTPException(status_code=409, detail="Asosiy yotoqxonani faolsizlantirib bolmaydi.")
        active_rooms = db.scalar(select(func.count(Room.id)).where(Room.dormitory_id == row.id, Room.is_active.is_(True))) or 0
        active_campaigns = db.scalar(select(func.count(AdmissionCampaign.id)).where(AdmissionCampaign.dormitory_id == row.id, AdmissionCampaign.status == "ACTIVE")) or 0
        pending_applications = db.scalar(select(func.count(StudentApplication.id)).where(StudentApplication.dormitory_id == row.id, StudentApplication.status.in_(("SUBMITTED", "IN_REVIEW", "NEEDS_INFO")))) or 0
        if active_rooms or active_campaigns or pending_applications:
            raise HTTPException(status_code=409, detail="Avval arizalarni korib chiqing, kampaniyalarni yoping va xonalarni arxivlang.")
    for key, value in values.items():
        setattr(row, key, value.strip() if isinstance(value, str) else value)
    audit(db, user, "DORMITORY_UPDATED", "Dormitory", row.id, {"changed_fields": sorted(values)})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Bu yotoqxona nomi mavjud.") from None
    db.refresh(row)
    return DormitoryOut.model_validate(row)


@staff_router.get("/admissions/campaigns", response_model=list[CampaignOut])
def list_campaigns(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[CampaignOut]:
    _require_staff(user)
    rows = db.scalars(select(AdmissionCampaign).order_by(AdmissionCampaign.created_at.desc())).all()
    return [CampaignOut.model_validate(row) for row in rows]


@staff_router.post("/admissions/campaigns", response_model=CampaignOut, status_code=201)
def create_campaign(payload: CampaignCreate, db: Session = Depends(get_db), user: User = Depends(require_operator)) -> CampaignOut:
    dormitory = db.get(Dormitory, payload.dormitory_id)
    if not dormitory or not dormitory.is_active:
        raise HTTPException(status_code=404, detail="Yotoqxona topilmadi.")
    keys = [field.key for field in payload.custom_fields]
    if len(keys) != len(set(keys)):
        raise HTTPException(status_code=422, detail="Qo‘shimcha maydon kalitlari takrorlanmasligi kerak.")
    row = AdmissionCampaign(
        name=payload.name.strip(), dormitory_id=payload.dormitory_id, custom_fields=[field.model_dump() for field in payload.custom_fields],
        document_types=list(dict.fromkeys(item.strip().upper() for item in payload.document_types if item.strip())),
        consent_version=payload.consent_version.strip(), consent_text=payload.consent_text.strip(), created_by=user.id,
    )
    db.add(row)
    db.flush()
    audit(db, user, "ADMISSION_CAMPAIGN_CREATED", "AdmissionCampaign", row.id)
    db.commit()
    db.refresh(row)
    return CampaignOut.model_validate(row)


@staff_router.patch("/admissions/campaigns/{campaign_id}/status", response_model=CampaignOut)
def change_campaign_status(campaign_id: UUID, status_value: Literal["ACTIVE", "PAUSED", "CLOSED"], db: Session = Depends(get_db), user: User = Depends(require_operator)) -> CampaignOut:
    campaign = db.get(AdmissionCampaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Qabul kampaniyasi topilmadi.")
    if status_value == "ACTIVE":
        dormitory = db.get(Dormitory, campaign.dormitory_id)
        if not dormitory or not dormitory.is_active:
            raise HTTPException(status_code=409, detail="Nofaol yotoqxona uchun kampaniyani ochib bolmaydi.")
    campaign.status = status_value
    audit(db, user, "ADMISSION_CAMPAIGN_STATUS_CHANGED", "AdmissionCampaign", campaign.id, {"status": status_value})
    db.commit()
    db.refresh(campaign)
    return CampaignOut.model_validate(campaign)


@staff_router.get("/admissions/invitations", response_model=list[InvitationOut])
def list_invitations(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[InvitationOut]:
    _require_staff(user)
    rows = db.scalars(select(AdmissionInvitation).order_by(AdmissionInvitation.created_at.desc()).limit(500)).all()
    return [_invite_out(row) for row in rows]


@staff_router.post("/admissions/invitations", response_model=InvitationOut, status_code=201)
def create_invitation(payload: InvitationCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> InvitationOut:
    _require_staff(user)
    campaign = db.get(AdmissionCampaign, payload.campaign_id)
    if not campaign or campaign.status != "ACTIVE":
        raise HTTPException(status_code=422, detail="Faol qabul kampaniyasini tanlang.")
    expires_at = _aware(payload.expires_at)
    if expires_at <= utcnow():
        raise HTTPException(status_code=422, detail="Taklif havolasining muddati kelajakda bo‘lishi kerak.")
    raw_token = secrets.token_urlsafe(32)
    row = AdmissionInvitation(
        token_hash=_digest(raw_token), campaign_id=campaign.id, dormitory_id=campaign.dormitory_id,
        expires_at=expires_at, max_submissions=payload.max_submissions, created_by=user.id,
    )
    db.add(row)
    db.flush()
    audit(db, user, "INVITATION_CREATED", "AdmissionInvitation", row.id, {"campaign_id": str(campaign.id), "max_submissions": row.max_submissions})
    db.commit()
    db.refresh(row)
    link = f"{settings.public_app_base_url}/apply#{raw_token}"
    return _invite_out(row, link)


@staff_router.post("/admissions/invitations/{invitation_id}/pause", response_model=InvitationOut)
def pause_invitation(invitation_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> InvitationOut:
    _require_staff(user)
    row = db.get(AdmissionInvitation, invitation_id)
    if not row:
        raise HTTPException(status_code=404, detail="Taklif topilmadi.")
    if row.revoked_at:
        raise HTTPException(status_code=409, detail="Bekor qilingan taklifni pauzaga qo‘yib bo‘lmaydi.")
    row.paused_at = utcnow()
    audit(db, user, "INVITATION_PAUSED", "AdmissionInvitation", row.id)
    db.commit()
    db.refresh(row)
    return _invite_out(row)


@staff_router.post("/admissions/invitations/{invitation_id}/resume", response_model=InvitationOut)
def resume_invitation(invitation_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> InvitationOut:
    _require_staff(user)
    row = db.get(AdmissionInvitation, invitation_id)
    if not row:
        raise HTTPException(status_code=404, detail="Taklif topilmadi.")
    if row.revoked_at or _aware(row.expires_at) <= utcnow() or row.submission_count >= row.max_submissions:
        raise HTTPException(status_code=409, detail="Ushbu taklifni davom ettirib bo‘lmaydi.")
    row.paused_at = None
    audit(db, user, "INVITATION_RESUMED", "AdmissionInvitation", row.id)
    db.commit()
    db.refresh(row)
    return _invite_out(row)


@staff_router.post("/admissions/invitations/{invitation_id}/revoke", response_model=InvitationOut)
def revoke_invitation(invitation_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> InvitationOut:
    _require_staff(user)
    row = db.get(AdmissionInvitation, invitation_id)
    if not row:
        raise HTTPException(status_code=404, detail="Taklif topilmadi.")
    if not row.revoked_at:
        row.revoked_at = utcnow()
        audit(db, user, "INVITATION_REVOKED", "AdmissionInvitation", row.id)
        db.commit()
        db.refresh(row)
    return _invite_out(row)


@staff_router.get("/admissions/applications", response_model=PageInfo)
def list_applications(
    status_filter: str = Query(default="all", alias="status"),
    campaign_id: UUID | None = None,
    dormitory_id: UUID | None = None,
    assigned_to: UUID | None = None,
    q: str = "",
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PageInfo:
    _require_staff(user)
    query = select(StudentApplication)
    if status_filter != "all":
        query = query.where(StudentApplication.status == status_filter.upper())
    if campaign_id:
        query = query.where(StudentApplication.campaign_id == campaign_id)
    if dormitory_id:
        query = query.where(StudentApplication.dormitory_id == dormitory_id)
    if assigned_to:
        query = query.where(StudentApplication.assigned_to == assigned_to)
    if q.strip():
        term = f"%{q.strip()}%"
        query = query.where(or_(StudentApplication.reference.ilike(term), StudentApplication.first_name_latin.ilike(term), StudentApplication.last_name_latin.ilike(term), StudentApplication.phone.ilike(term)))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(StudentApplication.created_at.desc()).offset(skip).limit(limit)).all()
    items = [ApplicationQueueOut(
        id=row.id, reference=row.reference, status=row.status,
        first_name_latin=row.first_name_latin, last_name_latin=row.last_name_latin,
        phone=row.phone, campaign_id=row.campaign_id, dormitory_id=row.dormitory_id,
        assigned_to=row.assigned_to, created_at=row.created_at,
    ) for row in rows]
    return PageInfo(items=items, total=total, skip=skip, limit=limit)


@staff_router.get("/admissions/applications/{application_id}", response_model=ApplicationOut)
def get_application(application_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> ApplicationOut:
    _require_staff(user)
    application = db.scalar(select(StudentApplication).options(selectinload(StudentApplication.files), selectinload(StudentApplication.events)).where(StudentApplication.id == application_id))
    if not application:
        raise HTTPException(status_code=404, detail="Ariza topilmadi.")
    return _application(application)


@staff_router.post("/admissions/applications/{application_id}/assign-to-me", response_model=ApplicationOut)
def assign_application(application_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> ApplicationOut:
    _require_staff(user)
    application = db.get(StudentApplication, application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Ariza topilmadi.")
    if application.status in {"APPROVED", "REJECTED", "CANCELLED", "ARCHIVED"}:
        raise HTTPException(status_code=409, detail="Yakunlangan arizani biriktirib bo‘lmaydi.")
    application.assigned_to = user.id
    audit(db, user, "APPLICATION_ASSIGNED", "StudentApplication", application.id)
    db.commit()
    return get_application(application_id, db, user)


@staff_router.put("/admissions/applications/{application_id}/notes", response_model=ApplicationOut)
def update_application_notes(application_id: UUID, payload: ApplicationNoteIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> ApplicationOut:
    _require_staff(user)
    application = db.get(StudentApplication, application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Ariza topilmadi.")
    application.internal_notes = payload.internal_notes.strip()
    audit(db, user, "APPLICATION_NOTE_UPDATED", "StudentApplication", application.id)
    db.commit()
    return get_application(application_id, db, user)


@staff_router.get("/admissions/applications/{application_id}/duplicates")
def find_application_duplicates(application_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict[str, object]]:
    _require_staff(user)
    application = db.get(StudentApplication, application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Ariza topilmadi.")
    candidates = db.scalars(select(Resident).where(Resident.is_archived.is_(False)).order_by(Resident.created_at.desc()).limit(500)).all()
    phone = _phone(application.phone) if application.phone else ""
    matches = [resident for resident in candidates if phone and resident.phone and _phone(resident.phone) == phone]
    if not matches:
        name = (application.first_name_latin.strip().casefold(), application.last_name_latin.strip().casefold())
        matches = [resident for resident in candidates if (resident.first_name.casefold(), resident.last_name.casefold()) == name]
    matches = matches[:10]
    histories = db.scalars(
        select(BillingPeriod)
        .where(BillingPeriod.resident_id.in_([resident.id for resident in matches]))
        .order_by(BillingPeriod.end_date.desc(), BillingPeriod.created_at.desc())
    ).all() if matches else []
    latest_period_by_resident: dict[UUID, BillingPeriod] = {}
    for period in histories:
        latest_period_by_resident.setdefault(period.resident_id, period)
    return [{
        "id": resident.id,
        "first_name": resident.first_name,
        "last_name": resident.last_name,
        "phone": resident.phone,
        "room_number": resident.room.number if resident.room else None,
        "agreed_price": resident.agreed_price if resident.agreed_price is not None else (latest_period_by_resident.get(resident.id).charge_amount if resident.id in latest_period_by_resident else None),
        "payment_period_days": resident.payment_period_days or (latest_period_by_resident.get(resident.id).period_days if resident.id in latest_period_by_resident else None),
    } for resident in matches]


@staff_router.post("/admissions/applications/{application_id}/request-info", response_model=ApplicationOut)
def request_application_info(application_id: UUID, payload: ApplicationRequestInfoIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> ApplicationOut:
    _require_staff(user)
    application = db.scalar(select(StudentApplication).where(StudentApplication.id == application_id).with_for_update())
    if not application:
        raise HTTPException(status_code=404, detail="Ariza topilmadi.")
    if application.status not in {"SUBMITTED", "IN_REVIEW", "NEEDS_INFO"}:
        raise HTTPException(status_code=409, detail="Ushbu arizada aniqlik so‘rab bo‘lmaydi.")
    campaign = db.get(AdmissionCampaign, application.campaign_id)
    allowed = EDITABLE_FIELDS | {item.get("key") for item in (campaign.custom_fields if campaign else [])} | {"photo"}
    allowed |= {"document:" + item for item in (campaign.document_types if campaign else [])}
    if any(field not in allowed for field in payload.fields):
        raise HTTPException(status_code=422, detail="Aniqlashtiriladigan maydonlar ro‘yxati noto‘g‘ri.")
    application.requested_fields = list(dict.fromkeys(payload.fields))
    application.review_reason = payload.reason.strip()
    application.assigned_to = user.id
    _event(db, application, "NEEDS_INFO", user, payload.reason.strip())
    audit(db, user, "APPLICATION_INFO_REQUESTED", "StudentApplication", application.id, {"fields": application.requested_fields})
    db.commit()
    return get_application(application_id, db, user)


@staff_router.post("/admissions/applications/{application_id}/start-review", response_model=ApplicationOut)
def start_application_review(application_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> ApplicationOut:
    _require_staff(user)
    application = db.scalar(select(StudentApplication).where(StudentApplication.id == application_id).with_for_update())
    if not application:
        raise HTTPException(status_code=404, detail="Ariza topilmadi.")
    if application.status == "IN_REVIEW":
        return get_application(application_id, db, user)
    if application.status != "SUBMITTED":
        raise HTTPException(status_code=409, detail="Tekshiruv faqat yuborilgan arizadan boshlanadi.")
    application.assigned_to = user.id
    _event(db, application, "IN_REVIEW", user)
    audit(db, user, "APPLICATION_REVIEW_STARTED", "StudentApplication", application.id)
    db.commit()
    return get_application(application_id, db, user)


@staff_router.post("/admissions/applications/{application_id}/reject", response_model=ApplicationOut)
def reject_application(application_id: UUID, payload: ApplicationRejectIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> ApplicationOut:
    _require_staff(user)
    application = db.scalar(select(StudentApplication).options(joinedload(StudentApplication.files)).where(StudentApplication.id == application_id).with_for_update())
    if not application:
        raise HTTPException(status_code=404, detail="Ariza topilmadi.")
    if application.status == "REJECTED":
        return _application(application)
    if application.status not in {"SUBMITTED", "IN_REVIEW", "NEEDS_INFO"}:
        raise HTTPException(status_code=409, detail="Ushbu arizani rad etib bo‘lmaydi.")
    application.review_reason = payload.reason.strip()
    application.terminal_at = utcnow()
    retention = settings.file_retention_days
    if retention:
        for attachment in application.files:
            attachment.delete_after = application.terminal_at + timedelta(days=retention)
    _event(db, application, "REJECTED", user, payload.reason.strip())
    audit(db, user, "APPLICATION_REJECTED", "StudentApplication", application.id)
    db.commit()
    return get_application(application_id, db, user)


@staff_router.post("/admissions/applications/{application_id}/approve", response_model=ApplicationOut)
def approve_application(application_id: UUID, payload: ApplicationApproveIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> ApplicationOut:
    _require_staff(user)
    application = db.scalar(select(StudentApplication).where(StudentApplication.id == application_id).with_for_update())
    if not application:
        raise HTTPException(status_code=404, detail="Ariza topilmadi.")
    if application.status == "APPROVED" and application.resident_id:
        return get_application(application_id, db, user)
    if application.status not in {"SUBMITTED", "IN_REVIEW", "NEEDS_INFO"}:
        raise HTTPException(status_code=409, detail="Ushbu arizani tasdiqlab bo‘lmaydi.")
    room = db.get(Room, payload.room_id)
    if not room or room.dormitory_id != application.dormitory_id:
        raise HTTPException(status_code=422, detail="Ariza uchun tanlangan yotoqxonadan xona tanlang.")
    resident = db.get(Resident, payload.resident_id) if payload.resident_id else None
    if payload.resident_id and not resident:
        raise HTTPException(status_code=404, detail="Bog'lanadigan yashovchi topilmadi.")
    latest_billing_period = db.scalar(
        select(BillingPeriod)
        .where(BillingPeriod.resident_id == resident.id)
        .order_by(BillingPeriod.end_date.desc(), BillingPeriod.created_at.desc())
        .limit(1)
    ) if resident else None
    has_open_billing_period = bool(resident and db.scalar(
        select(BillingPeriod.id)
        .where(BillingPeriod.resident_id == resident.id, BillingPeriod.status == "OPEN")
        .limit(1)
    ))
    existing_terms = bool(latest_billing_period)
    if payload.agreed_price is not None and user.role != "OPERATOR" and not settings.admins_can_adjust_billing:
        raise HTTPException(status_code=403, detail="Kelishilgan narxni faqat operator belgilaydi.")
    general = db.get(SystemSetting, "general")
    general_values = general.value if general and isinstance(general.value, dict) else {}
    default_period_days = int(general_values.get("default_period_days", 30))
    if existing_terms:
        agreed_price = resident.agreed_price if resident.agreed_price is not None else latest_billing_period.charge_amount
        payment_period_days = resident.payment_period_days or latest_billing_period.period_days or default_period_days
        if payload.agreed_price is not None and payload.agreed_price != agreed_price:
            raise HTTPException(status_code=409, detail="Mavjud yashovchining tarifini avval Yashovchilar bo‘limida yangilang.")
        if payload.payment_period_days is not None and payload.payment_period_days != payment_period_days:
            raise HTTPException(status_code=409, detail="Mavjud yashovchining to‘lov davrini avval Yashovchilar bo‘limida yangilang.")
    else:
        agreed_price = payload.agreed_price if payload.agreed_price is not None else (resident.agreed_price if resident and resident.agreed_price is not None else room.price)
        payment_period_days = payload.payment_period_days or (resident.payment_period_days if resident and resident.payment_period_days else default_period_days)
        if agreed_price is None or agreed_price < 0:
            raise HTTPException(status_code=422, detail="Xona narxini belgilang yoki tasdiqlash oynasida yashovchi narxini kiriting.")
        if payment_period_days <= 0:
            raise HTTPException(status_code=422, detail="To‘lov davri musbat kunlarda bo‘lishi kerak.")
    assert_room_available(db, room.id, payload.move_in, payload.move_out, exclude_resident_id=resident.id if resident else None)
    if resident and resident.is_archived:
        resident.is_archived = False
        resident.archived_at = None
    if not resident:
        resident = Resident(
            first_name=application.first_name_latin.strip(),
            last_name=application.last_name_latin.strip(),
            phone=application.phone or None,
            room_id=None,
            check_in_date=None,
            payment_period_days=payment_period_days,
            agreed_price=agreed_price,
            notes="",
        )
        db.add(resident)
        db.flush()
        audit(db, user, "RESIDENT_CREATED_FROM_APPLICATION", "Resident", resident.id, {"application_id": str(application.id)})
    record_room_assignment(db, resident, room.id, payload.move_in, payload.move_out, user)
    if not has_open_billing_period:
        resident.payment_period_days = payment_period_days
        resident.agreed_price = agreed_price
        billing_period = create_initial_period(
            db,
            resident,
            payload.move_in,
            payload.move_in + timedelta(days=payment_period_days),
            user,
        )
        audit(db, user, "BILLING_PERIOD_CREATED_FROM_APPLICATION", "BillingPeriod", billing_period.id, {
            "application_id": str(application.id),
            "resident_id": str(resident.id),
            "amount": str(billing_period.charge_amount),
            "period_days": billing_period.period_days,
        })
    if payload.resident_id is None:
        notify(db, "Yangi yashovchi", f"{resident.first_name} {resident.last_name} arizadan yashovchilar ro'yxatiga qo'shildi.", "RESIDENT", resident.id, user.id)
    application.resident_id = resident.id
    application.approved_room_id = room.id
    application.approved_move_in = payload.move_in
    application.approved_move_out = payload.move_out
    application.review_reason = payload.reason.strip()
    application.assigned_to = user.id
    application.terminal_at = utcnow()
    retention = settings.file_retention_days
    if retention:
        attachments = db.scalars(select(ApplicationFile).where(
            ApplicationFile.application_id == application.id,
            ApplicationFile.deleted_at.is_(None),
        )).all()
        for attachment in attachments:
            attachment.delete_after = application.terminal_at + timedelta(days=retention)
    _event(db, application, "APPROVED", user, payload.reason.strip())
    audit(db, user, "APPLICATION_APPROVED", "StudentApplication", application.id, {"resident_id": str(resident.id), "room_id": str(room.id)})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Ariza yoki xona holati o‘zgardi. Yangilab qayta tekshiring.") from None
    return get_application(application_id, db, user)


@staff_router.post("/admissions/applications/{application_id}/tracking-code")
def reissue_tracking_code(application_id: UUID, payload: ApplicationStatusIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, str]:
    _require_staff(user)
    application = db.get(StudentApplication, application_id)
    if not application or application.status == "DRAFT":
        raise HTTPException(status_code=404, detail="Yuborilgan ariza topilmadi.")
    raw_code = secrets.token_urlsafe(24)
    application.tracking_code_hash = _digest(raw_code)
    audit(db, user, "APPLICATION_TRACKING_CODE_REISSUED", "StudentApplication", application.id)
    db.commit()
    return {"access_code": raw_code}


@staff_router.get("/admissions/summary", response_model=AdmissionSummaryOut)
def admission_summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> AdmissionSummaryOut:
    _require_staff(user)
    statuses = ("DRAFT", "SUBMITTED", "IN_REVIEW", "NEEDS_INFO", "APPROVED", "REJECTED", "CANCELLED", "ARCHIVED")
    grouped = db.execute(
        select(StudentApplication.status, func.count(StudentApplication.id))
        .group_by(StudentApplication.status)
    ).all()
    by_status = {status: 0 for status in statuses}
    by_status.update({status: count for status, count in grouped})
    local_now = datetime.now(ZoneInfo(settings.timezone))
    month_start = local_now.date().replace(day=1)
    month_start_utc = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    applications_this_month = db.scalar(
        select(func.count(StudentApplication.id)).where(
            StudentApplication.status != "DRAFT",
            StudentApplication.created_at >= month_start_utc,
        )
    ) or 0
    approved_this_month = db.scalar(
        select(func.count(StudentApplication.id)).where(
            StudentApplication.status == "APPROVED",
            StudentApplication.terminal_at >= month_start_utc,
        )
    ) or 0
    resident_ids = set(db.scalars(
        select(StudentApplication.resident_id)
        .where(StudentApplication.status == "APPROVED", StudentApplication.resident_id.is_not(None))
        .distinct()
    ).all())

    open_periods = db.scalars(
        select(BillingPeriod).where(
            BillingPeriod.status == "OPEN",
            BillingPeriod.resident_id.in_(resident_ids),
        )
    ).all() if resident_ids else []
    expected_payments = sum((period.charge_amount for period in open_periods), Decimal("0.00"))

    next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
    monthly_payments = db.scalars(
        select(Payment).where(Payment.resident_id.in_(resident_ids), Payment.payment_date >= month_start, Payment.payment_date < next_month)
    ).all() if resident_ids else []
    period_payments = db.scalars(
        select(Payment).where(Payment.billing_period_id.in_([period.id for period in open_periods]))
    ).all() if open_periods else []
    relevant_payments = {payment.id: payment for payment in [*monthly_payments, *period_payments]}
    adjustments = db.scalars(
        select(PaymentAdjustment).where(PaymentAdjustment.payment_id.in_(relevant_payments))
    ).all() if relevant_payments else []
    adjustments_by_payment: dict[UUID, Decimal] = {}
    for adjustment in adjustments:
        adjustments_by_payment[adjustment.payment_id] = adjustments_by_payment.get(adjustment.payment_id, Decimal("0.00")) + adjustment.amount_delta
    paid_by_period: dict[UUID, Decimal] = {}
    for payment in period_payments:
        if payment.billing_period_id is not None:
            paid_by_period[payment.billing_period_id] = paid_by_period.get(payment.billing_period_id, Decimal("0.00")) + payment.amount + adjustments_by_payment.get(payment.id, Decimal("0.00"))
    outstanding_debt = sum((
        max(Decimal("0.00"), period.charge_amount - max(Decimal("0.00"), paid_by_period.get(period.id, Decimal("0.00"))))
        for period in open_periods
    ), Decimal("0.00"))
    actual_revenue_this_month = sum(
        (max(Decimal("0.00"), payment.amount + adjustments_by_payment.get(payment.id, Decimal("0.00"))) for payment in monthly_payments),
        Decimal("0.00"),
    )
    return AdmissionSummaryOut(
        total_applications=sum(count for status, count in by_status.items() if status != "DRAFT"),
        applications_this_month=applications_this_month,
        pending_applications=sum(by_status[status] for status in ("SUBMITTED", "IN_REVIEW", "NEEDS_INFO")),
        approved_applications=by_status["APPROVED"],
        approved_this_month=approved_this_month,
        rejected_applications=by_status["REJECTED"],
        linked_residents=len(resident_ids),
        expected_payments=expected_payments,
        outstanding_debt=outstanding_debt,
        actual_revenue_this_month=actual_revenue_this_month,
        by_status=by_status,
    )


@staff_router.get("/admissions/settings")
def admission_settings(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, int | bool | str | None]:
    _require_staff(user)
    storage_ready = storage.configured()
    general = db.get(SystemSetting, "general")
    default_period_days = (general.value if general and isinstance(general.value, dict) else {}).get("default_period_days", 30)
    return {
        "storage_backend": storage.backend,
        "storage_configured": storage_ready,
        "retention_days": settings.file_retention_days,
        "default_period_days": default_period_days,
        "billing_change_allowed": settings.admins_can_adjust_billing,
        "uploads_enabled": storage_ready and (settings.environment != "production" or settings.file_retention_days is not None),
        "ai_configured": document_processing_available(),
        "ai_configuration_issue": document_processing_issue(),
        "local_ocr_configured": local_ocr_available(),
        "external_ai_configured": openrouter_document_processing_available(),
        "antivirus_configured": False,
    }


@staff_router.get("/admissions/applications/{application_id}/files/{file_id}")
def download_application_file(application_id: UUID, file_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_staff(user)
    attachment = db.scalar(select(ApplicationFile).where(ApplicationFile.id == file_id, ApplicationFile.application_id == application_id, ApplicationFile.deleted_at.is_(None)))
    if not attachment:
        raise HTTPException(status_code=404, detail="Fayl topilmadi.")
    audit(db, user, "APPLICATION_FILE_DOWNLOADED", "ApplicationFile", attachment.id, {"kind": attachment.kind, "document_type": attachment.document_type})
    db.commit()
    if storage.backend == "s3":
        try:
            return RedirectResponse(storage.signed_download_url(attachment.object_key), status_code=302)
        except Exception:
            raise HTTPException(status_code=503, detail="Fayl omboriga ulanib bo‘lmadi.") from None
    if storage.backend == "postgres":
        content = storage.read(attachment.object_key, db)
        if content is None:
            raise HTTPException(status_code=404, detail="Fayl topilmadi.")
        return Response(
            content=content,
            media_type=attachment.content_type,
            headers={"Content-Disposition": f'attachment; filename="{attachment.original_name}"'},
        )
    path = storage.local_path(attachment.object_key)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Fayl topilmadi.")
    return FileResponse(path, media_type=attachment.content_type, filename=attachment.original_name, content_disposition_type="attachment")


@staff_router.get("/admissions/applications/{application_id}/files/{file_id}/signed-url")
def signed_application_file_url(application_id: UUID, file_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, str]:
    _require_staff(user)
    if storage.backend != "s3" or not storage.configured():
        raise HTTPException(status_code=409, detail="Imzolangan havola faqat sozlangan S3 omborida mavjud.")
    attachment = db.scalar(select(ApplicationFile).where(ApplicationFile.id == file_id, ApplicationFile.application_id == application_id, ApplicationFile.deleted_at.is_(None)))
    if not attachment:
        raise HTTPException(status_code=404, detail="Fayl topilmadi.")
    audit(db, user, "APPLICATION_FILE_SIGNED_URL_ISSUED", "ApplicationFile", attachment.id, {"kind": attachment.kind, "document_type": attachment.document_type})
    db.commit()
    try:
        return {"url": storage.signed_download_url(attachment.object_key)}
    except Exception:
        raise HTTPException(status_code=503, detail="Fayl omboriga ulanmadi.") from None


@staff_router.delete("/admissions/applications/{application_id}/files/{file_id}", status_code=204)
def delete_application_file(application_id: UUID, file_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Response:
    _require_staff(user)
    attachment = db.scalar(select(ApplicationFile).where(ApplicationFile.id == file_id, ApplicationFile.application_id == application_id, ApplicationFile.deleted_at.is_(None)))
    if not attachment:
        raise HTTPException(status_code=404, detail="Fayl topilmadi.")
    audit(db, user, "APPLICATION_FILE_DELETED", "ApplicationFile", attachment.id, {"kind": attachment.kind, "document_type": attachment.document_type})
    storage.delete(attachment.object_key, db=db)
    attachment.deleted_at = utcnow()
    attachment.extracted_data = {}
    attachment.ai_status = "DELETED"
    db.commit()
    return Response(status_code=204)


@public_router.post("/invitations/exchange", response_model=PublicSessionOut)
def exchange_invitation(payload: InvitationExchangeIn, request: Request, response: Response, db: Session = Depends(get_db)) -> PublicSessionOut:
    _rate_limit(db, request, "invite", 40, 3600)
    token = payload.token
    draft_key = payload.draft_key
    token_hash = _digest(token)
    invitation = db.scalar(select(AdmissionInvitation).where(AdmissionInvitation.token_hash == token_hash).with_for_update())
    if not invitation or _invitation_status(invitation) != "ACTIVE":
        raise HTTPException(status_code=404, detail="Taklif havolasi muddati tugagan yoki bekor qilingan.")
    idempotency_hash = _digest(f"{invitation.id}:{draft_key}")
    application = db.scalar(select(StudentApplication).where(StudentApplication.exchange_key_hash == idempotency_hash))
    campaign = db.get(AdmissionCampaign, invitation.campaign_id)
    dormitory = db.get(Dormitory, invitation.dormitory_id)
    if not campaign or campaign.status != "ACTIVE" or not dormitory or not dormitory.is_active:
        raise HTTPException(status_code=404, detail="Qabul kampaniyasi faol emas.")
    if application is None:
        application = StudentApplication(
            reference=f"DF-{utcnow():%y%m}-{secrets.token_hex(3).upper()}",
            invitation_id=invitation.id,
            exchange_key_hash=idempotency_hash,
            campaign_id=campaign.id,
            dormitory_id=invitation.dormitory_id,
            consent_version=campaign.consent_version,
        )
        db.add(application)
        db.flush()
        _event(db, application, "DRAFT", None)
        audit(db, None, "APPLICATION_DRAFT_CREATED", "StudentApplication", application.id)
    csrf_token = _set_student_session(response, db, application)
    return PublicSessionOut(csrf_token=csrf_token, campaign=_public_campaign(campaign), application=_public_application(application))


@public_router.post("/application/access-code", response_model=PublicStatusAccessOut)
def exchange_access_code(payload: PublicStatusAccessIn, request: Request, response: Response, db: Session = Depends(get_db)) -> PublicStatusAccessOut:
    _rate_limit(db, request, "access-code", 8, 900)
    application = db.scalar(select(StudentApplication).where(StudentApplication.tracking_code_hash == _digest(payload.access_code)))
    if not application:
        raise HTTPException(status_code=404, detail="Kirish kodi yoki ariza topilmadi.")
    csrf_token = _set_student_session(response, db, application)
    return PublicStatusAccessOut(csrf_token=csrf_token, status=_application_status(application))


@public_router.get("/application", response_model=PublicSessionOut)
def get_public_application(request: Request, db: Session = Depends(get_db)) -> PublicSessionOut:
    application, student_session = _student_session(request, db)
    campaign = db.get(AdmissionCampaign, application.campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Qabul kampaniyasi topilmadi.")
    return PublicSessionOut(csrf_token=_rotate_csrf(student_session, db), campaign=_public_campaign(campaign), application=_public_application(application))


@public_router.patch("/application", response_model=PublicApplicationOut)
def update_public_application(payload: ApplicationDraftIn, request: Request, db: Session = Depends(get_db), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> PublicApplicationOut:
    _rate_limit(db, request, "draft-save", 120, 3600)
    application, _ = _student_write_session(request, db, csrf_token)
    if application.status not in {"DRAFT", "NEEDS_INFO"}:
        raise HTTPException(status_code=409, detail="Yuborilgan arizani hozir tahrirlab bo‘lmaydi.")
    _apply_values(db, application, payload, partial=True)
    audit(db, None, "APPLICATION_DRAFT_UPDATED", "StudentApplication", application.id, {"changed_fields": sorted(payload.model_fields_set)})
    db.commit()
    db.refresh(application)
    return _public_application(application)


@public_router.get("/application/files", response_model=list[ApplicationFileOut])
def list_public_application_files(request: Request, db: Session = Depends(get_db)) -> list[ApplicationFileOut]:
    application, _ = _student_session(request, db)
    rows = db.scalars(select(ApplicationFile).where(ApplicationFile.application_id == application.id, ApplicationFile.deleted_at.is_(None)).order_by(ApplicationFile.uploaded_at)).all()
    return [_public_file_out(row) for row in rows]


def _public_file_out(row: ApplicationFile) -> ApplicationFileOut:
    return ApplicationFileOut.model_validate(row)


async def _run_file_extraction(
    db: Session,
    row: ApplicationFile,
    content: bytes,
    allow_external_ai: bool = False,
) -> None:
    """Run local OCR or the separately consented external model."""
    result = await extract_identity_document(
        content,
        row.content_type,
        allow_external_ai=allow_external_ai,
    )
    try:
        # The conditional update makes deletion/replacement win even when it
        # races the provider response; a late result cannot restore erased PII.
        db.execute(
            update(ApplicationFile)
            .where(
                ApplicationFile.id == row.id,
                ApplicationFile.deleted_at.is_(None),
                ApplicationFile.ai_status == "PROCESSING",
            )
            .values(ai_status=result.status, extracted_data=result.data)
            .execution_options(synchronize_session=False)
        )
        db.commit()
        db.refresh(row)
    except Exception as exc:
        db.rollback()
        logger.warning("Could not save document extraction result: %s", type(exc).__name__)


def _schedule_file_extraction(
    background_tasks: BackgroundTasks,
    db: Session,
    row: ApplicationFile,
    content: bytes,
    allow_external_ai: bool = False,
) -> None:
    background_tasks.add_task(_run_file_extraction, db, row, content, allow_external_ai)


@public_router.post("/application/files", response_model=ApplicationFileOut, status_code=201)
async def upload_public_file(
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    kind: Literal["PHOTO", "DOCUMENT"] = Form(...),
    document_type: str = Form(default=""),
    upload: UploadFile = File(...),
    db: Session = Depends(get_db),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    ai_processing_consent: bool = Header(default=False, alias="X-AI-Processing-Consent"),
    external_ai_consent: bool = Header(default=False, alias="X-External-AI-Consent"),
) -> ApplicationFileOut:
    _rate_limit(db, request, "upload", 40, 3600)
    application, _ = _student_write_session(request, db, csrf_token)
    if application.status not in {"DRAFT", "NEEDS_INFO"}:
        raise HTTPException(status_code=409, detail="Ushbu arizaga fayl qo‘shib bo‘lmaydi.")
    if not storage.configured() or (settings.environment == "production" and settings.file_retention_days is None):
        raise HTTPException(status_code=503, detail="Fayl ombori yoki saqlash muddati sozlanmagan.")
    campaign = db.get(AdmissionCampaign, application.campaign_id)
    if kind == "DOCUMENT" and (not campaign or document_type not in campaign.document_types):
        raise HTTPException(status_code=422, detail="Hujjat turini kampaniya ro‘yxatidan tanlang.")
    if kind == "PHOTO" and application.status == "NEEDS_INFO" and "photo" not in application.requested_fields:
        raise HTTPException(status_code=403, detail="Suratni yangilash so‘ralmagan.")
    content = await upload.read(settings.file_max_bytes + 1)
    content_type, safe_name = validate_upload(upload, content)
    if kind == "PHOTO" and not content_type.startswith("image/"):
        raise HTTPException(status_code=415, detail="Yashovchi surati uchun rasm faylini tanlang.")
    if kind == "DOCUMENT" and "document:" + document_type not in application.requested_fields and application.status == "NEEDS_INFO":
        raise HTTPException(status_code=403, detail="Ushbu hujjatni yangilash so‘ralmagan.")
    suffix = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "application/pdf": ".pdf"}[content_type]
    ai_status = "NOT_CONFIGURED"
    extracted_data: dict[str, str] = {}
    should_extract = False
    allow_external_ai = False
    if kind == "DOCUMENT":
        local_ocr_ready = local_ocr_available()
        external_ai_requested = (
            external_ai_consent
            and openrouter_processing_issue() is None
        )
        processing_issue = document_processing_issue()
        if processing_issue:
            ai_status = processing_issue
        elif not ai_processing_consent:
            ai_status = "CONSENT_REQUIRED"
        elif local_ocr_ready or external_ai_requested:
            application.ai_processing_consented_at = utcnow()
            ai_status = "PROCESSING"
            should_extract = True
            allow_external_ai = external_ai_requested
        else:
            ai_status = "CONSENT_REQUIRED"
    object_key = f"admissions/{application.id}/{uuid4().hex}{suffix}"
    replacement_query = select(ApplicationFile).where(
        ApplicationFile.application_id == application.id,
        ApplicationFile.kind == kind,
        ApplicationFile.deleted_at.is_(None),
    )
    if kind == "DOCUMENT":
        replacement_query = replacement_query.where(ApplicationFile.document_type == document_type)
    previous_files = db.scalars(replacement_query).all()
    existing_count = db.scalar(select(func.count(ApplicationFile.id)).where(ApplicationFile.application_id == application.id, ApplicationFile.deleted_at.is_(None))) or 0
    if existing_count >= 10 and not previous_files:
        raise HTTPException(status_code=409, detail="Arizaga maksimum 10 ta fayl biriktirish mumkin.")
    try:
        replaced_at = utcnow()
        for previous in previous_files:
            previous.deleted_at = replaced_at
            previous.delete_after = replaced_at
            previous.extracted_data = {}
            previous.ai_status = "DELETED"
        uploaded_at = utcnow()
        retention = settings.file_retention_days
        row = ApplicationFile(
            application_id=application.id,
            kind=kind,
            document_type=document_type if kind == "DOCUMENT" else "",
            object_key=object_key,
            original_name=safe_name,
            content_type=content_type,
            size_bytes=len(content),
            scan_status="NOT_CONFIGURED",
            ai_status=ai_status,
            extracted_data=extracted_data,
            delete_after=uploaded_at + timedelta(days=retention) if application.status == "DRAFT" and retention else None,
            uploaded_at=uploaded_at,
        )
        db.add(row)
        db.flush()
        storage.put(object_key, content, content_type, db=db)
        if storage.backend == "postgres":
            for previous in previous_files:
                storage.delete(previous.object_key, db=db)
        audit(db, None, "APPLICATION_FILE_UPLOADED", "ApplicationFile", row.id, {"kind": kind, "document_type": row.document_type})
        if should_extract:
            audit(db, None, "APPLICATION_AI_PROCESSING_CONSENTED", "StudentApplication", application.id, {
                "provider": "OpenRouter" if allow_external_ai else "local_tesseract",
                "external_ai": allow_external_ai,
                "route": settings.openrouter_model if allow_external_ai else None,
            })
        if previous_files:
            audit(db, None, "APPLICATION_FILE_REPLACED", "ApplicationFile", row.id, {"kind": kind, "document_type": row.document_type})
        db.commit()
        db.refresh(row)
    except Exception:
        db.rollback()
        if storage.backend != "postgres":
            try:
                storage.delete(object_key, db=db)
            except Exception:
                pass
        raise
    if storage.backend != "postgres":
        for previous in previous_files:
            try:
                storage.delete(previous.object_key, db=db)
            except Exception:
                # The replacement row is committed; the scheduled purge retries the old private object.
                continue
    if should_extract:
        _schedule_file_extraction(background_tasks, db, row, content, allow_external_ai)
    return _public_file_out(row)


@public_router.post(
    "/application/files/{file_id}/extract",
    response_model=ApplicationFileOut,
    status_code=202,
)
def retry_public_file_extraction(
    file_id: UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    ai_processing_consent: bool = Header(default=False, alias="X-AI-Processing-Consent"),
    external_ai_consent: bool = Header(default=False, alias="X-External-AI-Consent"),
) -> ApplicationFileOut:
    _rate_limit(db, request, "ai-extraction", 20, 3600)
    application, _ = _student_write_session(request, db, csrf_token)
    if application.status not in {"DRAFT", "NEEDS_INFO"}:
        raise HTTPException(status_code=409, detail="Yakunlangan ariza hujjatini qayta tahlil qilib bo‘lmaydi.")
    if not ai_processing_consent:
        raise HTTPException(status_code=403, detail="AI tahlilini boshlash uchun alohida rozilik bering.")
    row = db.scalar(select(ApplicationFile).where(
        ApplicationFile.id == file_id,
        ApplicationFile.application_id == application.id,
        ApplicationFile.deleted_at.is_(None),
    ))
    if not row or row.kind != "DOCUMENT":
        raise HTTPException(status_code=404, detail="Hujjat topilmadi.")
    processing_issue = document_processing_issue()
    # A retry explicitly chooses one backend: with a fresh external-provider
    # consent, do not silently fall back to local OCR if OpenRouter is not ready.
    allow_external_ai = external_ai_consent and openrouter_processing_issue() is None
    if processing_issue and not (external_ai_consent and local_ocr_available()):
        detail = (
            "Mahalliy OCR yoki maxfiylik talablariga mos AI xizmati sozlanmagan."
        )
        raise HTTPException(status_code=503, detail=detail)
    if row.ai_status == "PROCESSING":
        raise HTTPException(status_code=409, detail="Hujjat hozir tahlil qilinmoqda.")
    if row.ai_status in {"COMPLETED", "NO_FIELDS"}:
        return _public_file_out(row)

    content = storage.read(row.object_key, db)
    if not content:
        raise HTTPException(status_code=503, detail="Saqlangan hujjatni o‘qib bo‘lmadi.")
    if len(content) > settings.file_max_bytes:
        raise HTTPException(status_code=413, detail="Hujjat hajmi ruxsat etilgan chegaradan oshdi.")

    if not local_ocr_available() and not allow_external_ai:
        raise HTTPException(
            status_code=403,
            detail="Mahalliy OCR mavjud emas. Tashqi AI tahliliga alohida rozilik bering.",
        )
    application.ai_processing_consented_at = utcnow()
    row.ai_status = "PROCESSING"
    row.extracted_data = {}
    audit(db, None, "APPLICATION_AI_PROCESSING_CONSENTED", "StudentApplication", application.id, {
        "provider": "OpenRouter" if allow_external_ai else "local_tesseract",
        "external_ai": allow_external_ai,
        "route": settings.openrouter_model if allow_external_ai else None,
    })
    db.commit()
    db.refresh(row)
    _schedule_file_extraction(background_tasks, db, row, content, allow_external_ai)
    return _public_file_out(row)


@public_router.post("/application/submit")
def submit_public_application(payload: ApplicationSubmitIn, request: Request, response: Response, db: Session = Depends(get_db), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict[str, str]:
    _rate_limit(db, request, "submit", 30, 3600)
    application, _ = _student_write_session(request, db, csrf_token)
    application = db.scalar(select(StudentApplication).where(StudentApplication.id == application.id).with_for_update().execution_options(populate_existing=True))
    if not application:
        raise HTTPException(status_code=404, detail="Ariza topilmadi.")
    if application.status in {"SUBMITTED", "IN_REVIEW"}:
        return {"reference": application.reference, "status": application.status, "access_code": ""}
    if application.status in {"APPROVED", "REJECTED", "CANCELLED", "ARCHIVED"}:
        raise HTTPException(status_code=409, detail="Ariza yakunlangan.")
    if not payload.consent:
        raise HTTPException(status_code=422, detail="Arizani yuborish uchun rozilikni tasdiqlang.")
    campaign = db.get(AdmissionCampaign, application.campaign_id)
    missing = [name for name, value in {
        "first_name_latin": application.first_name_latin,
        "last_name_latin": application.last_name_latin,
        "birth_date": application.birth_date,
        "phone": application.phone,
        "institution": application.institution,
    }.items() if value in (None, "")]
    for field in (campaign.custom_fields if campaign else []):
        if field.get("required") and not application.additional_data.get(field.get("key")):
            missing.append(field.get("key", "custom"))
    if missing:
        raise HTTPException(status_code=422, detail="Majburiy maydonlarni to‘ldiring: " + ", ".join(missing))
    if application.email:
        try:
            TypeAdapter(EmailStr).validate_python(application.email)
        except ValidationError:
            raise HTTPException(status_code=422, detail="Elektron pochta manzilini tekshiring.") from None
    if not application.phone.startswith("+"):
        application.phone = _phone(application.phone)
    files = db.scalars(select(ApplicationFile).where(ApplicationFile.application_id == application.id, ApplicationFile.deleted_at.is_(None))).all()
    if application.status == "NEEDS_INFO":
        requested_at = db.scalar(
            select(ApplicationStatusEvent.created_at)
            .where(ApplicationStatusEvent.application_id == application.id, ApplicationStatusEvent.to_status == "NEEDS_INFO")
            .order_by(ApplicationStatusEvent.created_at.desc())
            .limit(1)
        )
        requested_files = [field for field in application.requested_fields if field == "photo" or field.startswith("document:")]
        missing_updates = []
        for field in requested_files:
            kind = "PHOTO" if field == "photo" else "DOCUMENT"
            document_type = "" if kind == "PHOTO" else field.removeprefix("document:")
            if not requested_at or not any(
                item.kind == kind
                and (kind == "PHOTO" or item.document_type == document_type)
                and _aware(item.uploaded_at) > _aware(requested_at)
                for item in files
            ):
                missing_updates.append(field)
        if missing_updates:
            raise HTTPException(status_code=422, detail="Sorilgan fayllarni qayta yuklang: " + ", ".join(missing_updates) + ", ".join(missing_updates))
    if not any(item.kind == "PHOTO" for item in files):
        raise HTTPException(status_code=422, detail="Yashovchi suratini biriktiring.")
    missing_documents = [doc for doc in (campaign.document_types if campaign else []) if not any(item.kind == "DOCUMENT" and item.document_type == doc for item in files)]
    if missing_documents:
        raise HTTPException(status_code=422, detail="Kerakli hujjatlarni biriktiring: " + ", ".join(missing_documents))
    for attachment in files:
        attachment.delete_after = None
    first_submission = application.status == "DRAFT"
    if first_submission:
        if not campaign or campaign.status != "ACTIVE":
            raise HTTPException(status_code=409, detail="Qabul kampaniyasi faol emas.")
        invitation = db.scalar(select(AdmissionInvitation).where(AdmissionInvitation.id == application.invitation_id).with_for_update())
        if not invitation or _invitation_status(invitation) != "ACTIVE":
            raise HTTPException(status_code=409, detail="Taklif havolasidagi yuborish limiti tugagan.")
        invitation.submission_count += 1
    application.consent_version = campaign.consent_version if campaign else application.consent_version
    application.consented_at = utcnow()
    application.requested_fields = []
    application.review_reason = ""
    if application.status in {"DRAFT", "NEEDS_INFO"}:
        application.assigned_to = None
        _event(db, application, "SUBMITTED", None)
    access_code = ""
    if first_submission:
        access_code = secrets.token_urlsafe(24)
        application.tracking_code_hash = _digest(access_code)
    audit(db, None, "APPLICATION_SUBMITTED", "StudentApplication", application.id)
    db.commit()
    return {"reference": application.reference, "status": application.status, "access_code": access_code}


@public_router.get("/application/status", response_model=PublicStatusOut)
def public_application_status(request: Request, db: Session = Depends(get_db)) -> PublicStatusOut:
    application, _ = _student_session(request, db)
    return _application_status(application)


@public_router.post("/application/respond", response_model=PublicApplicationOut)
def respond_to_request(payload: ApplicationDraftIn, request: Request, db: Session = Depends(get_db), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> PublicApplicationOut:
    _rate_limit(db, request, "clarification", 30, 3600)
    application, _ = _student_write_session(request, db, csrf_token)
    if application.status != "NEEDS_INFO":
        raise HTTPException(status_code=409, detail="Arizada qo‘shimcha ma’lumot so‘ralmagan.")
    _apply_values(db, application, payload, partial=True)
    audit(db, None, "APPLICATION_CLARIFICATION_RECEIVED", "StudentApplication", application.id, {"changed_fields": sorted(payload.model_fields_set)})
    db.commit()
    db.refresh(application)
    return _public_application(application)

