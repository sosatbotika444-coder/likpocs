"""aiogram 3 bot (long polling) for visitors, staff and investors.

Run as a separate Railway service:  ``python -m app.telegram_bot``.
All database work is synchronous and runs in a thread; the token is read only from the environment.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message, ReplyKeyboardMarkup
from fastapi import HTTPException
from sqlalchemy import select

from app import admissions_api as adm
from app import telegram_apply as apply_flow
from app import telegram_staff as staff
from app.config import settings
from app.contract import contract_plain_text
from app.db import SessionLocal
from app.models import StudentApplication, TelegramAccount, TelegramOutbox, utcnow

logger = logging.getLogger("telegram_bot")
router = Router()
CHUNK = 3500
MAX_ATTEMPTS = 5


class Apply(StatesGroup):
    answering = State()
    files = State()
    contract = State()
    signature = State()


async def db_call(fn, *args, **kwargs):
    def run():
        with SessionLocal() as db:
            return fn(db, *args, **kwargs)
    return await asyncio.to_thread(run)


def detail(exc: Exception) -> str:
    return str(exc.detail) if isinstance(exc, HTTPException) else str(exc)


def chunks(text: str) -> list[str]:
    parts, current = [], ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > CHUNK and current:
            parts.append(current)
            current = ""
        current += line + "\n"
    return parts + [current] if current.strip() else parts


def button(text: str, data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, callback_data=data)]])


def main_menu(role: str | None, has_application: bool) -> ReplyKeyboardMarkup:
    """Role-scoped persistent buttons. Labels are slash commands, so they reuse the audited handlers."""
    if role == "INVESTOR":
        rows = [["/summary"], ["/help", "/unlink"]]
    elif role == "OPERATOR":
        rows = [["/applications", "/rooms"], ["/residents", "/tasks"], ["/tasknew", "/notifications"], ["/summary", "/help"]]
    elif role == "ADMIN":
        rows = [["/applications", "/rooms"], ["/residents", "/tasks"], ["/tasknew", "/notifications"], ["/help", "/unlink"]]
    elif has_application:
        rows = [["/profile", "/status"], ["/continue", "/edit"], ["/contract", "/help"]]
    else:
        rows = [["/help", "/link"]]
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=item) for item in row] for row in rows],
        resize_keyboard=True,
        input_field_placeholder="Buyruq yoki tugmani tanlang",
    )


def load_context(db, chat_id: int):
    account = staff.get_account(db, chat_id)
    user = staff.staff_user(db, chat_id) if account else None
    application = db.get(StudentApplication, account.application_id) if account and account.application_id else None
    return (user.role, user.full_name) if user else None, (application.id, application.status, application.reference) if application else None


def current_info(chat_id: int):
    return db_call(load_context, chat_id)


async def ask_step(message: Message, state: FSMContext, index: int) -> None:
    await state.set_state(Apply.answering)
    await state.update_data(step=index)
    await message.answer(apply_flow.APPLICATION_STEPS[index][1])


async def ask_files(message: Message, state: FSMContext, app_id) -> None:
    def pending(db):
        application = db.get(StudentApplication, app_id)
        return apply_flow.missing_files(db, application)
    missing = await db_call(pending)
    if not missing:
        await show_contract(message, state, app_id)
        return
    await state.set_state(Apply.files)
    kind, doc = missing[0]
    await state.update_data(kind=kind, doc=doc)
    await message.answer("Yashovchi suratini yuboring (rasm sifatida)." if kind == "PHOTO" else f"Hujjatni yuboring: {doc} (rasm yoki PDF fayl).")


async def show_contract(message: Message, state: FSMContext, app_id) -> None:
    def render(db):
        return contract_plain_text(adm.contract_for_application(db.get(StudentApplication, app_id)))
    text = await db_call(render)
    await message.answer("Ijara shartnomasini diqqat bilan o‘qing:")
    for part in chunks(text):
        await message.answer(part)
    await state.set_state(Apply.contract)
    await message.answer("Shartnoma shartlari bilan to‘liq tanishdingizmi?", reply_markup=button("✅ O‘qidim va roziman", "contract:accept"))


def sender_info(message: Message) -> tuple[int, int | None, str, str]:
    user = message.from_user
    return message.chat.id, user.id if user else None, (user.username or "") if user else "", (user.full_name if user else "")


def start_flow(db, chat_id, tg_id, username, full_name, token):
    application = apply_flow.start_application(db, chat_id, tg_id, username, full_name, token)
    return application.id, application.reference, application.status


@router.message(Command("legacy_start"))
async def cmd_start(message: Message, command: CommandObject, state: FSMContext) -> None:
    await state.clear()
    chat_id, tg_id, username, full_name = sender_info(message)
    payload = (command.args or "").strip()
    if payload.startswith("link_"):
        user = await db_call(staff.link_staff, chat_id, tg_id, username, full_name, payload[5:])
        if user is None:
            await message.answer("Kod noto‘g‘ri yoki muddati tugagan. Saytdagi Sozlamalar bo‘limida yangi kod oling.")
            return
        await message.answer(f"Hisob ulandi: {user.full_name} ({staff.ROLE_UZ[user.role]}).\nBuyruqlar: {', '.join(staff.allowed_commands(user))}")
        return
    if payload.startswith("inv_"):
        try:
            app_id, reference, status = await db_call(start_flow, chat_id, tg_id, username, full_name, payload[4:])
        except Exception as exc:  # noqa: BLE001 - shown to the applicant as a safe message
            await message.answer(detail(exc))
            return
        if status != "DRAFT":
            await message.answer(f"Ariza {reference} allaqachon yuborilgan. Holatni /status orqali ko‘ring.")
            return
        await message.answer(f"Yotoqxonaga ariza ({reference}). Savollarga ketma-ket javob bering. Bekor qilish: /cancel")
        await ask_step(message, state, 0)
        return
    staff_info, app_info = await current_info(chat_id)
    if staff_info:
        await message.answer(f"Salom, {staff_info[1]} ({staff.ROLE_UZ[staff_info[0]]}). /help — buyruqlar ro‘yxati.")
    elif app_info:
        await message.answer(f"Ariza {app_info[2]}. /status — holatni ko‘rish, /continue — davom ettirish.")
    else:
        await message.answer("RS Best Hostel botiga xush kelibsiz.\nAriza berish uchun xodimdan taklif havolasini oling va u orqali botni oching.\nXodim bo‘lsangiz: saytdagi Sozlamalar → Telegram bo‘limidan kod oling va /link KOD yozing.")


@router.message(Command("start"))
async def cmd_start_with_menu(message: Message, command: CommandObject, state: FSMContext) -> None:
    await cmd_start(message, command, state)
    staff_info, application_info = await current_info(message.chat.id)
    await message.answer(
        "Quyidagi tugmalar orqali davom eting.",
        reply_markup=main_menu(staff_info[0] if staff_info else None, application_info is not None),
    )


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    staff_info, application_info = await current_info(message.chat.id)
    await message.answer(
        "Asosiy menyu:",
        reply_markup=main_menu(staff_info[0] if staff_info else None, application_info is not None),
    )


@router.message(Command("link"))
async def cmd_link(message: Message, command: CommandObject) -> None:
    if not command.args:
        await message.answer("Foydalanish: /link KOD")
        return
    chat_id, tg_id, username, full_name = sender_info(message)
    user = await db_call(staff.link_staff, chat_id, tg_id, username, full_name, command.args)
    await message.answer(f"Hisob ulandi: {user.full_name} ({staff.ROLE_UZ[user.role]})." if user else "Kod noto‘g‘ri yoki muddati tugagan.")


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Bekor qilindi. Davom ettirish: /continue")


@router.message(Command("legacy_help"))
async def cmd_help(message: Message) -> None:
    staff_info, _ = await current_info(message.chat.id)
    if not staff_info:
        await message.answer("/start — boshlash\n/status — ariza holati\n/continue — arizani davom ettirish\n/contract — shartnoma matni\n/link KOD — xodim hisobini ulash")
        return
    role = staff_info[0]
    if role == "INVESTOR":
        await message.answer("/summary — joriy oy moliyaviy yakuni\n/unlink — Telegramni uzish")
    else:
        extra = "\n/summary — moliyaviy yakun" if role == "OPERATOR" else ""
        await message.answer("/applications — ochiq arizalar\n/stats — arizalar statistikasi\n/rooms — bo‘sh o‘rinlar\n/tasks — vazifalarim\n/notifications — bildirishnomalar" + extra + "\n/unlink — Telegramni uzish")


@router.message(Command("unlink"))
async def cmd_unlink(message: Message) -> None:
    def work(db, chat_id):
        account = staff.get_account(db, chat_id)
        if account:
            account.is_active = False
            db.commit()
        return account is not None
    await message.answer("Telegram uzildi." if await db_call(work, message.chat.id) else "Ulangan hisob topilmadi.")


@router.message(Command("help"))
async def cmd_help_current(message: Message) -> None:
    staff_info, _ = await current_info(message.chat.id)
    if not staff_info:
        await message.answer(
            "/start - boshlash\n/profile - ariza profilingiz\n/edit - qoralama ma'lumotlarini qayta kiritish\n"
            "/status - ariza holati\n/continue - arizani davom ettirish\n/contract - shartnoma matni\n/link KOD - xodim hisobini ulash"
        )
        return
    if staff_info[0] == "INVESTOR":
        await message.answer("/summary - joriy oy moliyaviy yakuni\n/unlink - Telegramni uzish")
        return
    extra = "\n/summary - moliyaviy yakun" if staff_info[0] == "OPERATOR" else ""
    await message.answer(
        "/applications - ochiq arizalar\n/stats - arizalar statistikasi\n/rooms - bo'sh o'rinlar\n"
        "/residents [qidiruv] - yashovchilar\n/tasks - vazifalarim\n/tasknew MATN - o'zimga vazifa\n"
        "/taskstart KOD - vazifani boshlash\n/taskdone KOD - vazifani tugatish\n/notifications - bildirishnomalar"
        + extra + "\n/unlink - Telegramni uzish"
    )



def load_draft(db, chat_id):
    account = staff.get_account(db, chat_id)
    if not account or not account.application_id:
        return None
    application = db.get(StudentApplication, account.application_id)
    return (application.id, application.status, application.reference) if application else None


@router.message(Command("continue"))
async def cmd_continue(message: Message, state: FSMContext) -> None:
    info = await db_call(load_draft, message.chat.id)
    if not info:
        await message.answer("Faol ariza topilmadi. Taklif havolasi orqali botni oching.")
        return
    if info[1] != "DRAFT":
        await message.answer("Ariza yuborilgan. Holat: /status")
        return
    def next_step(db):
        application = db.get(StudentApplication, info[0])
        for index, (key, _) in enumerate(apply_flow.APPLICATION_STEPS):
            value = getattr(application, key)
            if value in (None, ""):
                return index
        return None
    index = await db_call(next_step)
    if index is None:
        await ask_files(message, state, info[0])
    else:
        await ask_step(message, state, index)


@router.message(StateFilter(Apply.answering), F.text)
async def on_answer(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    index = int(data.get("step", 0))
    info = await db_call(load_draft, message.chat.id)
    if not info:
        await state.clear()
        return
    key = apply_flow.APPLICATION_STEPS[index][0]
    def save(db):
        apply_flow.save_answer(db, db.get(StudentApplication, info[0]), key, message.text or "")
    try:
        await db_call(save)
    except Exception as exc:  # noqa: BLE001
        await message.answer(f"{detail(exc)}\nQayta kiriting:")
        return
    if index + 1 < len(apply_flow.APPLICATION_STEPS):
        await ask_step(message, state, index + 1)
    else:
        await ask_files(message, state, info[0])


async def download(bot: Bot, file_id: str) -> bytes:
    import io
    buffer = io.BytesIO()
    await bot.download(file_id, destination=buffer)
    return buffer.getvalue()


async def store_upload(message: Message, state: FSMContext, bot: Bot, file_id: str, name: str) -> None:
    data = await state.get_data()
    info = await db_call(load_draft, message.chat.id)
    if not info:
        return
    content = await download(bot, file_id)
    def save(db):
        apply_flow.attach_file(db, db.get(StudentApplication, info[0]), data["kind"], data.get("doc", ""), content, name)
    try:
        await db_call(save)
    except Exception as exc:  # noqa: BLE001
        await message.answer(f"{detail(exc)}\nQayta yuboring.")
        return
    await message.answer("Fayl saqlandi.")
    await ask_files(message, state, info[0])


@router.message(StateFilter(Apply.files), F.photo)
async def on_photo(message: Message, state: FSMContext, bot: Bot) -> None:
    await store_upload(message, state, bot, message.photo[-1].file_id, "telegram.jpg")


@router.message(StateFilter(Apply.files), F.document)
async def on_document(message: Message, state: FSMContext, bot: Bot) -> None:
    document = message.document
    if document.file_size and document.file_size > settings.file_max_bytes:
        await message.answer("Fayl hajmi ruxsat etilgan chegaradan oshdi.")
        return
    await store_upload(message, state, bot, document.file_id, document.file_name or "telegram")


@router.callback_query(StateFilter(Apply.contract), F.data == "contract:accept")
async def on_contract_accept(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.set_state(Apply.signature)
    await call.message.answer("Imzo sifatida ism va familiyangizni to‘liq yozing (masalan: Aziza Karimova):")


@router.message(StateFilter(Apply.signature), F.text)
async def on_signature(message: Message, state: FSMContext) -> None:
    info = await db_call(load_draft, message.chat.id)
    if not info:
        await state.clear()
        return
    def submit(db):
        return adm.submit_application(db, info[0], via="TELEGRAM", consent=True, contract_accepted=True, signature_name=message.text or "")
    try:
        result = await db_call(submit)
    except Exception as exc:  # noqa: BLE001
        await message.answer(detail(exc))
        return
    await state.clear()
    await message.answer(
        f"Arizangiz qabul qilindi. Raqami: {result['reference']}\nHolat o‘zgarganda shu yerda xabar olasiz."
        + (f"\nSayt uchun kirish kodi (saqlab qo‘ying): {result['access_code']}" if result["access_code"] else "")
    )


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    info = await db_call(load_draft, message.chat.id)
    if not info:
        await message.answer("Ariza topilmadi.")
        return
    await message.answer(f"Ariza {info[2]}: {staff.STATUS_UZ.get(info[1], info[1])}")


@router.message(Command("contract"))
async def cmd_contract(message: Message) -> None:
    info = await db_call(load_draft, message.chat.id)
    if not info:
        await message.answer("Shartnoma ariza bilan birga ko‘rsatiladi. Avval taklif havolasi orqali ariza boshlang.")
        return
    text = await db_call(lambda db: contract_plain_text(adm.contract_for_application(db.get(StudentApplication, info[0]))))
    for part in chunks(text):
        await message.answer(part)



@router.message(Command("profile"))
async def cmd_profile(message: Message) -> None:
    profile = await db_call(apply_flow.applicant_profile, message.chat.id)
    if not profile:
        await message.answer("Ariza profilingiz topilmadi. Ariza uchun taklif havolasidan foydalaning.")
        return
    full_name = f"{profile['first_name']} {profile['last_name']}".strip() or "—"
    signature = profile["signature_name"] or "hali imzolanmagan"
    await message.answer(
        f"Ariza: {profile['reference']} · {staff.STATUS_UZ.get(profile['status'], profile['status'])}\n"
        f"F.I.Sh.: {full_name}\nTug'ilgan sana: {profile['birth_date'] or '—'}\n"
        f"Telefon: {profile['phone'] or '—'}\nTa'lim muassasasi: {profile['institution'] or '—'}\n"
        f"Ko'chib kirish: {profile['requested_move_in'] or '—'}\nShartnoma imzosi: {signature}"
    )


@router.message(Command("edit"))
async def cmd_edit(message: Message, state: FSMContext) -> None:
    info = await db_call(load_draft, message.chat.id)
    if not info:
        await message.answer("Tahrirlash uchun faol ariza topilmadi.")
        return
    if info[1] != "DRAFT":
        await message.answer("Yuborilgan arizani botdan tahrirlab bo'lmaydi. Xodim bilan bog'laning.")
        return
    await message.answer("Ma'lumotlarni boshidan qayta kiriting. Bekor qilish: /cancel")
    await ask_step(message, state, 0)


def staff_command(fn_name: str):
    """Build a handler that runs ``telegram_staff.<fn_name>(db, user)`` for the linked staff user."""
    async def handler(message: Message) -> None:
        def work(db):
            user = staff.staff_user(db, message.chat.id)
            if user is None:
                return "Avval hisobni ulang: /link KOD"
            try:
                return getattr(staff, fn_name)(db, user)
            except PermissionError as exc:
                return str(exc)
        for part in chunks(await db_call(work)):
            await message.answer(part)
    return handler


router.message.register(staff_command("queue_summary"), Command("stats"))
router.message.register(staff_command("rooms_overview"), Command("rooms"))
router.message.register(staff_command("open_tasks"), Command("tasks"))
router.message.register(staff_command("unread_notifications"), Command("notifications"))
router.message.register(staff_command("finance_summary"), Command("summary"))


@router.message(Command("residents"))
async def cmd_residents(message: Message, command: CommandObject) -> None:
    def work(db):
        user = staff.staff_user(db, message.chat.id)
        if user is None:
            return "Avval hisobni ulang: /link KOD"
        try:
            return staff.residents_overview(db, user, command.args or "")
        except PermissionError as exc:
            return str(exc)
    for part in chunks(await db_call(work)):
        await message.answer(part)


async def run_task_command(message: Message, command: CommandObject, status: str | None = None) -> None:
    def work(db):
        user = staff.staff_user(db, message.chat.id)
        if user is None:
            return "Avval hisobni ulang: /link KOD"
        try:
            if status is None:
                return staff.create_quick_task(db, user, command.args or "")
            return staff.change_task_status(db, user, command.args or "", status)
        except (PermissionError, ValueError) as exc:
            return str(exc)
    await message.answer(await db_call(work))


@router.message(Command("tasknew"))
async def cmd_task_new(message: Message, command: CommandObject) -> None:
    await run_task_command(message, command)


@router.message(Command("taskstart"))
async def cmd_task_start(message: Message, command: CommandObject) -> None:
    await run_task_command(message, command, "IN_PROGRESS")


@router.message(Command("taskdone"))
async def cmd_task_done(message: Message, command: CommandObject) -> None:
    await run_task_command(message, command, "DONE")


@router.message(Command("applications"))
async def cmd_applications(message: Message) -> None:
    def work(db):
        user = staff.staff_user(db, message.chat.id)
        if user is None:
            return "Avval hisobni ulang: /link KOD", []
        try:
            return "", [(item.id, staff.application_card(item), item.status) for item in staff.open_applications(db, user)]
        except PermissionError as exc:
            return str(exc), []
    error, items = await db_call(work)
    if error or not items:
        await message.answer(error or "Ochiq arizalar yo‘q.")
        return
    for app_id, card, status in items:
        rows = []
        if status == "SUBMITTED":
            rows.append(InlineKeyboardButton(text="Tekshirishni boshlash", callback_data=f"app:review:{app_id}"))
        rows.append(InlineKeyboardButton(text="Rad etish", callback_data=f"app:reject:{app_id}"))
        await message.answer(card, reply_markup=InlineKeyboardMarkup(inline_keyboard=[rows]))


@router.callback_query(F.data.startswith("app:"))
async def on_application_action(call: CallbackQuery) -> None:
    from uuid import UUID

    _, action, raw_id = (call.data or "").split(":", 2)
    def work(db):
        user = staff.staff_user(db, call.message.chat.id)
        if user is None:
            return "Avval hisobni ulang: /link KOD"
        try:
            return staff.decide_application(db, user, UUID(raw_id), action)
        except (PermissionError, LookupError, ValueError) as exc:
            return str(exc)
    await call.answer(await db_call(work), show_alert=True)


@router.message(F.text)
async def fallback(message: Message) -> None:
    await message.answer("Tushunmadim. /help — buyruqlar ro‘yxati.")


def claim_outbox(db, limit: int = 20):
    rows = db.scalars(
        select(TelegramOutbox).where(TelegramOutbox.sent_at.is_(None), TelegramOutbox.attempts < MAX_ATTEMPTS)
        .order_by(TelegramOutbox.created_at).limit(limit).with_for_update(skip_locked=True)
    ).all()
    return [(row.id, row.chat_id, row.text) for row in rows]


def mark_outbox(db, outbox_id, error: str) -> None:
    row = db.get(TelegramOutbox, outbox_id)
    if row is None:
        return
    row.attempts += 1
    if error:
        row.last_error = error[:80]
        # Blocked or deleted chats can never succeed; stop retrying and unlink them.
        if "blocked" in error.lower() or "chat not found" in error.lower() or "deactivated" in error.lower():
            row.attempts = MAX_ATTEMPTS
            account = db.scalar(select(TelegramAccount).where(TelegramAccount.chat_id == row.chat_id, TelegramAccount.is_active.is_(True)))
            if account:
                account.is_active = False
    else:
        row.sent_at = utcnow()
    db.commit()


async def deliver_outbox(bot: Bot) -> int:
    sent = 0
    for outbox_id, chat_id, text in await db_call(claim_outbox):
        try:
            await bot.send_message(chat_id, text)
            await db_call(mark_outbox, outbox_id, "")
            sent += 1
        except Exception as exc:  # noqa: BLE001 - only a short category is stored, never message text
            await db_call(mark_outbox, outbox_id, type(exc).__name__ + ": " + str(exc)[:50])
        await asyncio.sleep(0.05)
    return sent


async def outbox_loop(bot: Bot) -> None:
    while True:
        try:
            await deliver_outbox(bot)
        except Exception:  # noqa: BLE001
            logger.exception("Outbox delivery failed")
        await asyncio.sleep(settings.telegram_poll_seconds)


async def run() -> None:
    token = settings.telegram_bot_token.strip()
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN sozlanmagan.")
    bot = Bot(token)
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    worker = asyncio.create_task(outbox_loop(bot))
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await dispatcher.start_polling(bot)
    finally:
        worker.cancel()
        await bot.session.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())


if __name__ == "__main__":
    main()

