"""Hostel lease agreement shown to applicants before they submit an application.

The wording follows the organisation's "Hostelda yashash (ijara) shartnomasi" template and is
published in Uzbek Latin.  Details that are only known after review (room, bed, monthly amount,
move-out date) are described as being fixed on approval instead of being invented here.
The accepted text is identified by ``CONTRACT_VERSION`` plus a SHA-256 of the static clauses, so a
later edit of the template can never be mistaken for what the applicant accepted.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date

CONTRACT_VERSION = "2026-11"
CONTRACT_TITLE = "HOSTELDA YASHASH (IJARA) SHARTNOMASI"
CONTRACT_CITY = "Toshkent shahri"
MONTHS_UZ = (
    "yanvar", "fevral", "mart", "aprel", "may", "iyun",
    "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr",
)
LESSOR = {
    "name": "\"RS Best\" MChJ",
    "address": "Toshkent shahri, Shayxontohur tumani, Ibn Sino 1-mavzesi, 8a-uy",
    "phone": "+998 70 529 90 00",
    "tin": "313327620",
    "account": "20208000207536487001",
    "bank": "\"DAVR BANK\" XATB",
}

_PART_ONE: tuple[dict[str, object], ...] = (
    {"title": "1. SHARTNOMA PREDMETI", "clauses": (
        "1.1. Ijara beruvchi Ijara oluvchiga hostelda yashash uchun xona va undagi o‘rinni vaqtincha foydalanishga beradi. Xona raqami va o‘rin arizani ko‘rib chiqish yakunida tasdiqlanadi va qabul qilish-topshirish dalolatnomasida ko‘rsatiladi.",
        "1.2. Hostel manzili: Toshkent shahri, Shayxontohur tumani, Ibn Sino 1-mavzesi, 8a-uy.",
        "1.3. Ijara oluvchi xona va hostelning umumiy foydalanish joylaridan belgilangan tartibda foydalanish huquqiga ega.",
        "1.4. Xona va undagi jihozlar Tomonlar tomonidan qabul qilish-topshirish dalolatnomasi asosida topshirilishi mumkin.",
    )},
    {"title": "2. SHARTNOMA MUDDATI", "clauses": (
        "2.1. Mazkur shartnoma ariza tasdiqlanib, ko‘chib kirish sanasi belgilangan kundan boshlab, tomonlar kelishgan muddat tugaguniga qadar amal qiladi. Ariza tasdiqlanmasa, shartnoma kuchga kirmaydi.",
        "2.2. Tomonlarning o‘zaro kelishuviga asosan shartnoma muddati uzaytirilishi mumkin.",
    )},
    {"title": "3. IJARA HAQI VA TO‘LOV TARTIBI", "clauses": (
        "3.1. Hostelda yashash uchun oylik to‘lov miqdori tasdiqlangan xona tarifiga qarab belgilanadi va ariza tasdiqlanganda Ijara oluvchiga ma’lum qilinadi.",
        "3.2. To‘lov belgilangan to‘lov davri tugashidan oldin amalga oshiriladi.",
        "3.3. To‘lov shakli: naqd pul, bank o‘tkazmasi yoki plastik karta orqali.",
        "3.4. Kommunal va boshqa xizmatlar ijara haqiga kiritilganmi yoki alohida to‘lanadimi, bu ariza tasdiqlanganda Ijara oluvchiga yetkaziladi.",
        "3.5. Qo‘shimcha to‘lovlar Tomonlarning kelishuvi bilan belgilanadi.",
    )},
    {"title": "4. IJARA BERUVCHINING HUQUQ VA MAJBURIYATLARI", "clauses": (
        "4.1. Ijara beruvchi talabaga yashash uchun belgilangan joyni o‘z vaqtida taqdim etishi, sanitariya va xavfsizlik talablariga rioya etilishini ta’minlashi, umumiy foydalanish joylarining holatini nazorat qilishi va ichki tartib-qoidalar bilan talabani tanishtirishi shart.",
        "4.2. Ijara beruvchi shartnoma shartlari buzilgan taqdirda qonunchilik va mazkur shartnoma talablariga muvofiq chora ko‘rish huquqiga ega. Agar Ijara oluvchi tomonidan ichki tartib-qoidalar buzilsa, Ijara beruvchi shartnomani bir tomonlama bekor qilishi mumkin; avvaldan to‘langan ijara to‘lovi qaytarilmaydi va to‘liq oylik hisobiga olinadi.",
    )},
)

_PART_TWO: tuple[dict[str, object], ...] = (
    {"title": "5. IJARA OLUVCHINING HUQUQ VA MAJBURIYATLARI", "clauses": (
        "5.1. Ijara oluvchi ijara haqini belgilangan muddatda to‘lashi, xona va hosteldagi mol-mulkni e’tiborli saqlashi, ichki tartib-qoidalarga, tozalik, sanitariya va yong‘in xavfsizligi talablariga rioya qilishi, boshqa talabalarning tinchligiga xalaqit bermasligi shart.",
        "5.2. Ijara oluvchi Ijara beruvchining roziligisiz xonada yashash huquqini boshqa shaxsga bermasligi shart.",
        "5.3. Ijara oluvchi mol-mulkka zarar yetkazgan taqdirda yetkazilgan zararni qonunchilik va Tomonlar kelishuviga muvofiq qoplaydi.",
    )},
    {"title": "6. HOSTEL ICHKI TARTIBI", "clauses": (
        "6.1. Hostelda yashovchilar umumiy tartib-qoidalarga rioya qilishlari shart.",
        "6.2. Tungi vaqtda boshqa yashovchilarning dam olishiga xalaqit beruvchi shovqin va boshqa harakatlarga yo‘l qo‘yilmaydi.",
        "6.3. Hostel hududida xavfsizlik, sanitariya va yong‘in xavfsizligi talablariga rioya qilinishi shart.",
        "6.4. Hostel hududida taqiqlangan buyumlardan foydalanishga yo‘l qo‘yilmaydi.",
        "6.5. Mehmonlarni qabul qilish tartibi hostelning ichki qoidalari asosida belgilanadi.",
    )},
    {"title": "7. SHARTNOMANI BEKOR QILISH", "clauses": (
        "7.1. Shartnoma Tomonlarning o‘zaro kelishuviga asosan muddatidan oldin bekor qilinishi mumkin.",
        "7.2. Tomonlardan biri shartnoma shartlarini jiddiy ravishda buzgan taqdirda, ikkinchi tomon qonunchilikda belgilangan tartibda shartnomani bekor qilishni talab qilish huquqiga ega.",
        "7.3. Ijara oluvchi hosteldan chiqib ketishdan oldin Ijara beruvchini kamida 3 kun oldin xabardor qiladi.",
        "7.4. Shartnoma bekor qilinganda Ijara oluvchi qarzdorliklarini to‘liq to‘laydi va unga berilgan mol-mulkni qaytarib topshiradi.",
    )},
    {"title": "8. TOMONLARNING JAVOBGARLIGI", "clauses": (
        "8.1. Tomonlar mazkur shartnoma shartlarini bajarmaslik yoki lozim darajada bajarmaslik uchun amaldagi qonunchilikka muvofiq javobgar bo‘ladilar.",
        "8.2. Nizolar, avvalo, muzokaralar yo‘li bilan hal qilinadi.",
        "8.3. Muzokaralar orqali hal qilish imkoni bo‘lmagan nizolar qonunchilikda belgilangan tartibda hal etiladi.",
    )},
    {"title": "9. YAKUNIY QOIDALAR", "clauses": (
        "9.1. Mazkur shartnoma ikki nusxada tuziladi va har ikki nusxa bir xil yuridik kuchga ega. Elektron shaklda tasdiqlangan nusxa ham Ijara oluvchining roziligini bildiradi.",
        "9.2. Shartnomaga kiritiladigan o‘zgartish va qo‘shimchalar Tomonlarning yozma kelishuvi asosida amalga oshiriladi.",
        "9.3. Ijara oluvchi mazkur shartnomani imzolash orqali hostelning ichki tartib-qoidalari bilan tanishganligini tasdiqlaydi va to‘liq shartnoma shartlariga roziligini bildiradi.",
    )},
)

CONTRACT_SECTIONS: tuple[dict[str, object], ...] = _PART_ONE + _PART_TWO


def contract_hash() -> str:
    """Fingerprint of the exact static wording that applicants accept."""
    payload = json.dumps(
        {"version": CONTRACT_VERSION, "title": CONTRACT_TITLE, "lessor": LESSOR, "sections": CONTRACT_SECTIONS},
        ensure_ascii=False, sort_keys=True, default=list,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def date_text(value: date) -> str:
    return f"«{value.day}» {MONTHS_UZ[value.month - 1]} {value.year} yil"


def render_contract(*, reference: str, tenant_name: str, tenant_phone: str, on: date) -> dict[str, object]:
    """Return the contract as plain JSON-serialisable data for the web form and the Telegram bot."""
    tenant = tenant_name.strip() or "—"
    parties = {
        "title": "10. TOMONLARNING REKVIZITLARI VA IMZOLARI",
        "clauses": (
            f"IJARA BERUVCHI: {LESSOR['name']}. Manzil: {LESSOR['address']}. Telefon: {LESSOR['phone']}. STIR: {LESSOR['tin']}. Hisob raqami: {LESSOR['account']}. Bank: {LESSOR['bank']}.",
            f"IJARA OLUVCHI (TALABA): F.I.Sh.: {tenant}. Telefon: {tenant_phone.strip() or '—'}. Pasport/ID ma’lumotlari arizaga biriktirilgan hujjatlar bo‘yicha tekshiriladi.",
            f"Sana: {date_text(on)}.",
        ),
    }
    return {
        "version": CONTRACT_VERSION,
        "hash": contract_hash(),
        "title": CONTRACT_TITLE,
        "number": f"№ {reference}",
        "date": date_text(on),
        "city": CONTRACT_CITY,
        "sections": [{"title": item["title"], "clauses": list(item["clauses"])} for item in (*CONTRACT_SECTIONS, parties)],
    }


def contract_plain_text(contract: dict[str, object]) -> str:
    """Flatten a rendered contract for chat messages and plain-text download."""
    lines = [str(contract["title"]), f"{contract['number']} · {contract['date']} · {contract['city']}", ""]
    for section in contract["sections"]:  # type: ignore[union-attr]
        lines.append(str(section["title"]))
        lines.extend(str(clause) for clause in section["clauses"])
        lines.append("")
    return "\n".join(lines).strip()

