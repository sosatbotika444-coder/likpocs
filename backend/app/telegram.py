"""Telegram integration: server-side outbox, link codes and per-role message policy.

The API never talks to Telegram directly.  It writes rows to ``telegram_outbox``; the separate
``python -m app.telegram_bot`` worker (aiogram) delivers them.  Nothing here runs unless
``TELEGRAM_BOT_TOKEN`` is configured, and the token is never sent to the browser.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Notification, StudentApplication, TelegramAccount, TelegramLinkCode, TelegramOutbox, User, utcnow

# Payment/balance text must never reach ADMIN or INVESTOR chats, mirroring the web notification rules.
FINANCIAL_KINDS = frozenset({"PAYMENT", "BILLING", "DUE_TODAY", "DUE_SOON", "OVERDUE"})
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
MAX_TEXT = 3500


class NotificationAdapter(Protocol):
    async def send(self, recipient: str, message: str) -> None: ...


class TelegramAdapter:
    def __init__(self, sender: Callable[[str, str], Awaitable[None]] | None = None) -> None:
        self._sender = sender

    async def send(self, recipient: str, message: str) -> None:
        if self._sender is None:
            raise RuntimeError("Telegram integratsiyasi sozlanmagan.")
        await self._sender(recipient, message)


def telegram_configured() -> bool:
    return bool(settings.telegram_bot_token.strip())


def bot_username() -> str:
    return settings.telegram_bot_username.strip().lstrip("@")


def telegram_invitation_link(raw_token: str) -> str | None:
    """Deep link that opens the bot with an invitation token (Telegram allows 64 payload characters)."""
    name = bot_username()
    payload = f"inv_{raw_token}"
    if not name or len(payload) > 64:
        return None
    return f"https://t.me/{name}?start={payload}"


def code_digest(code: str) -> str:
    return hashlib.sha256(code.strip().upper().encode("utf-8")).hexdigest()


def enqueue(db: Session, chat_id: int, text: str, kind: str = "INFO") -> None:
    if not telegram_configured():
        return
    db.add(TelegramOutbox(chat_id=chat_id, kind=kind[:32], text=text[:MAX_TEXT]))


def queue_for_user(db: Session, user: User, title: str, message: str, kind: str = "INFO") -> None:
    """Queue a staff notification for the user's linked chat, applying role redaction."""
    if not telegram_configured() or not user.is_active or user.role == "INVESTOR":
        return
    if kind in FINANCIAL_KINDS and user.role != "OPERATOR":
        return
    account = db.scalar(select(TelegramAccount).where(TelegramAccount.user_id == user.id, TelegramAccount.is_active.is_(True)))
    if account:
        enqueue(db, account.chat_id, f"{title}\n{message}", kind)


def mirror_notification(db: Session, item: Notification) -> None:
    """Called for every personal web notification so Telegram stays in sync with the bell icon."""
    if item.user_id is None or not telegram_configured():
        return
    user = db.get(User, item.user_id)
    if user:
        queue_for_user(db, user, item.title, item.message, item.kind)


def queue_for_application(db: Session, application_id: UUID, text: str, kind: str = "APPLICATION") -> None:
    if not telegram_configured():
        return
    account = db.scalar(select(TelegramAccount).where(TelegramAccount.application_id == application_id, TelegramAccount.is_active.is_(True)))
    if account:
        enqueue(db, account.chat_id, text, kind)


APPLICATION_STATUS_TEXT = {
    "IN_REVIEW": "Arizangiz xodim tomonidan ko‘rib chiqilmoqda.",
    "NEEDS_INFO": "Arizangiz bo‘yicha qo‘shimcha ma’lumot so‘raldi. Saytdagi arizangizni kirish kodi bilan oching.",
    "APPROVED": "Tabriklaymiz! Arizangiz tasdiqlandi. Xona va to‘lov tafsilotlari bilan xodim bog‘lanadi.",
    "REJECTED": "Afsuski, arizangiz rad etildi.",
}


def notify_application_status(db: Session, application: StudentApplication, to_status: str, reason: str = "") -> None:
    """Tell the applicant's bot chat about a status change; silent when no chat is linked."""
    text = APPLICATION_STATUS_TEXT.get(to_status)
    if not text:
        return
    message = f"Ariza {application.reference}\n{text}"
    if reason.strip() and to_status in {"NEEDS_INFO", "REJECTED"}:
        message += f"\nSabab: {reason.strip()}"
    queue_for_application(db, application.id, message, "APPLICATION_STATUS")


def notify_staff_of_application(db: Session, application: StudentApplication) -> None:
    """Web bell + Telegram alert for every active operator/administrator."""
    from app.audit import notify

    name = f"{application.first_name_latin} {application.last_name_latin}".strip() or application.reference
    staff = db.scalars(select(User).where(User.is_active.is_(True), User.role.in_(("OPERATOR", "ADMIN")))).all()
    for member in staff:
        notify(db, "Yangi ariza yuborildi", f"{application.reference} · {name}", "APPLICATION", application.id, member.id)


def create_link_code(db: Session, user: User) -> tuple[str, datetime]:
    """Issue a short-lived one-time code; only its hash is stored and older unused codes are revoked."""
    db.execute(delete(TelegramLinkCode).where(TelegramLinkCode.user_id == user.id, TelegramLinkCode.used_at.is_(None)))
    code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
    expires_at = utcnow() + timedelta(minutes=settings.telegram_link_minutes)
    db.add(TelegramLinkCode(code_hash=code_digest(code), user_id=user.id, expires_at=expires_at))
    return code, expires_at


def consume_link_code(db: Session, code: str) -> User | None:
    row = db.scalar(select(TelegramLinkCode).where(TelegramLinkCode.code_hash == code_digest(code)).with_for_update())
    if not row or row.used_at is not None:
        return None
    expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
    if expires <= utcnow():
        return None
    user = db.get(User, row.user_id)
    if not user or not user.is_active:
        return None
    row.used_at = utcnow()
    return user
