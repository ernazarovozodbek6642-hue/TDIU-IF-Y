from utils.access import get_access
from io import BytesIO

from aiogram import Router, F
from aiogram.types import BufferedInputFile, Message
from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from filters.is_admin import IsAdmin
from loader import dp, db, bot
from utils.logger_channel import log_action
from utils.misc.funcsion import get_current_month_year
from utils.spreadsheets import safe_excel_value

router = Router()
router.message.filter(IsAdmin())

HEADERS = ["№", "F.I.Sh", "Username", "Guruh", "Tug‘ilgan sana", "Telefon", "Passport", "Manzil", "TTJda turadi",
            "Joriy oy bali", "Jarimalar soni", "Chetlatilgan"]


@router.message(F.text == "📊Faollar ma'lumoti(exel)")
async def export_users(msg: Message):
    access = await get_access(db, msg.from_user.id)
    if msg.chat.type != "private":
        await msg.answer("Shaxsiy ma'lumotlar eksporti faqat bot bilan shaxsiy chatda beriladi.")
        return
    if not access.allows("export_activists"):
        await msg.answer("Barcha faollar ma'lumotlarini eksport qilish uchun ruxsatingiz yo'q.")
        return
    users = await db.get_all_users()
    if not users:
        await msg.answer("Hozircha ro'yxatdan o'tgan faollar yo'q")
        return

    month, year = get_current_month_year()
    leaderboard = await db.get_monthly_leaderboard(month, year)
    scores = {row["user_id"]: row["total_score"] for row in leaderboard}

    wb = Workbook()
    ws = wb.active
    ws.title = f"Faollar {month}.{year}"

    for col, header in enumerate(HEADERS, start=1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True)

    for i, user in enumerate(users, start=1):
        ws.append([
            i,
            safe_excel_value(user["full_name"]),
            safe_excel_value(f"@{user['user_name']}" if user["user_name"] else ""),
            safe_excel_value(user["group_name"]),
            str(user["birth_date"]) if user["birth_date"] else "",
            safe_excel_value(user["phone_number"]),
            safe_excel_value(user["passport_number"]),
            safe_excel_value(user["location"]),
            "Ha" if user["lives_in_dormitory"] else "Yo'q",
            float(scores.get(user["user_id"], 0)),
            user["penalty_count"],
            "Ha" if user["is_excluded"] else "Yo'q",
        ])

    for col in range(1, len(HEADERS) + 1):
        max_len = max(
            len(str(ws.cell(row=r, column=col).value or "")) for r in range(1, ws.max_row + 1)
        )
        ws.column_dimensions[get_column_letter(col)].width = min(max_len + 3, 45)

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    file = BufferedInputFile(buf.read(), filename=f"faollar_{year}-{month:02d}.xlsx")
    await msg.answer_document(file, caption=f"📊 Faollar ma'lumoti — {month}.{year} ({len(users)} ta)")
    await log_action(bot, msg.from_user, f"Excel eksport yuklab olindi ({len(users)} ta faol)")
