import asyncio

import pytest
from sqlalchemy import select

from app import admissions_api as adm
from app import telegram_apply as apply_flow
from app import telegram_staff as staff
from app.config import settings
from app.models import TelegramAccount, TelegramOutbox, User
from app.security import hash_password
from app.telegram import create_link_code
from tests.test_admissions import _headers, _png_bytes, _workflow


@pytest.fixture
def bot_token(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "test-token")


def test_link_code_is_one_time_and_roles_are_enforced(client, database, operator_token, bot_token):
    headers = _headers(operator_token)
    code = client.post("/api/telegram/link-code", headers=headers).json()["code"]
    investor = User(email="i2@example.com", full_name="Inv", password_hash=hash_password("investor-pass-123"), role="INVESTOR", is_active=True)
    database.add(investor)
    database.commit()
    admin = database.scalar(select(User).where(User.role == "ADMIN"))
    assert staff.link_staff(database, 111, 1, "op", "Op", "WRONGCODE") is None
    operator = staff.link_staff(database, 111, 1, "op", "Op", code)
    assert operator.role == "OPERATOR"
    assert staff.link_staff(database, 111, 1, "op", "Op", code) is None
    assert client.get("/api/telegram/status", headers=headers).json()["linked"] is True
    admin_code, _ = create_link_code(database, admin)
    investor_code, _ = create_link_code(database, investor)
    database.commit()
    assert staff.link_staff(database, 222, 2, "ad", "Ad", admin_code)
    assert staff.link_staff(database, 333, 3, "iv", "Iv", investor_code)
    assert "Tushum" in staff.finance_summary(database, operator)
    assert "Tushum" in staff.finance_summary(database, investor)
    with pytest.raises(PermissionError):
        staff.finance_summary(database, admin)
    for fn in (staff.rooms_overview, staff.open_tasks, staff.queue_summary, staff.unread_notifications):
        with pytest.raises(PermissionError):
            fn(database, investor)
    assert "so'm" not in staff.rooms_overview(database, admin)


def test_applicant_flow_signs_contract_and_gets_status_updates(client, database, operator_token, admin_token, bot_token):
    _, _, _, token, _ = _workflow(client, operator_token, admin_token)
    application = apply_flow.start_application(database, 555, 5, "stu", "Student", token)
    answers = (
        ("first_name_latin", "Aziza"), ("last_name_latin", "Karimova"), ("birth_date", "11.04.2005"),
        ("phone", "+998901234567"), ("institution", "National University"), ("requested_move_in", "01.11.2026"),
    )
    for key, value in answers:
        apply_flow.save_answer(database, application, key, value)
    with pytest.raises(ValueError):
        apply_flow.save_answer(database, application, "birth_date", "31.31.2005")
    assert apply_flow.missing_files(database, application) == [("PHOTO", "")]
    apply_flow.attach_file(database, application, "PHOTO", "", _png_bytes(), "p.png")
    assert apply_flow.missing_files(database, application) == []
    with pytest.raises(Exception) as unsigned:
        adm.submit_application(database, application.id, via="TELEGRAM", consent=True, contract_accepted=False, signature_name="")
    assert unsigned.value.status_code == 422
    adm.submit_application(database, application.id, via="TELEGRAM", consent=True, contract_accepted=True, signature_name="Aziza Karimova")
    database.refresh(application)
    assert application.status == "SUBMITTED" and application.contract_signed_via == "TELEGRAM"
    operator = database.scalar(select(User).where(User.role == "OPERATOR"))
    assert "boshlandi" in staff.decide_application(database, operator, application.id, "review")
    texts = [row.text for row in database.scalars(select(TelegramOutbox)).all()]
    assert any("ko‘rib chiqilmoqda" in text for text in texts)
    assert database.scalar(select(TelegramAccount).where(TelegramAccount.chat_id == 555)).application_id == application.id


def test_outbox_marks_sent_and_stops_retrying_blocked_chats(database, bot_token):
    from app import telegram_bot as bot_module

    database.add_all([TelegramOutbox(chat_id=1, text="ok"), TelegramOutbox(chat_id=2, text="blocked")])
    database.commit()

    class FakeBot:
        async def send_message(self, chat_id, text):
            if chat_id == 2:
                raise RuntimeError("Forbidden: bot was blocked by the user")

    async def local(fn, *args, **kwargs):
        return fn(database, *args, **kwargs)

    original = bot_module.db_call
    bot_module.db_call = local
    try:
        assert asyncio.run(bot_module.deliver_outbox(FakeBot())) == 1
    finally:
        bot_module.db_call = original
    rows = {row.chat_id: row for row in database.scalars(select(TelegramOutbox)).all()}
    assert rows[1].sent_at is not None
    assert rows[2].sent_at is None and rows[2].attempts == bot_module.MAX_ATTEMPTS
