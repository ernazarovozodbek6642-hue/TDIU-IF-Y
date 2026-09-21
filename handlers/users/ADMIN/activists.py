import math
from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from keyboards.default.ADMIN_Keyboard import admin_menu
from loader import bot, db
from states.Admin_state import ACTIVISTS
from utils.access import get_access
from utils.logger_channel import log_action
from utils.misc.funcsion import get_current_month_year

router = Router()
PAGE_SIZE = 15


def _list_keyboard(users, page: int, total: int):
    builder = InlineKeyboardBuilder()
    for user in users:
        group = f" — {user['group_name']}" if user["group_name"] else ""
        username = f"@{user['user_name']} | " if user["user_name"] else ""
        builder.button(
            text=f"👤 {username}{user['full_name']}{group}"[:64],
            callback_data=f"act:u:{user['user_id']}:{page}",
        )
    pages = max(1, math.ceil(total / PAGE_SIZE))
    if page > 0:
        builder.button(text="◀️ Oldingi", callback_data=f"act:p:{page - 1}")
    builder.button(text=f"{page + 1}/{pages}", callback_data="act:noop")
    if page + 1 < pages:
        builder.button(text="Keyingi ▶️", callback_data=f"act:p:{page + 1}")
    builder.button(text="🔎 Izlash", callback_data="act:search")
    builder.button(text="❌ Yopish", callback_data="act:close")
    builder.adjust(*([1] * len(users)), 3, 2)
    return builder.as_markup()


async def _render_list(target, state: FSMContext, page: int = 0, edit: bool = False):
    data = await state.get_data()
    query = (data.get("activists_query") or "").strip()
    total = int(await db.count_approved_users(query))
    pages = max(1, math.ceil(total / PAGE_SIZE))
    page = min(max(0, page), pages - 1)
    users = await db.get_approved_users_page(PAGE_SIZE, page * PAGE_SIZE, query)
    title = f"🔎 <b>Qidiruv:</b> {escape(query)}\n" if query else "👤 <b>Barcha faollar</b>\n"
    text = f"{title}Jami: <b>{total}</b> ta. Talabani tanlang:"
    markup = _list_keyboard(users, page, total)
    if edit:
        await target.edit_text(text, reply_markup=markup)
    else:
        await target.answer(text, reply_markup=markup)


@router.message(F.text == "👤 Faollar")
async def activists_list(msg: Message, state: FSMContext):
    await state.clear()
    await _render_list(msg, state)


@router.callback_query(F.data.startswith("act:p:"))
async def activists_page(call: CallbackQuery, state: FSMContext):
    page = int(call.data.rsplit(":", 1)[1])
    await _render_list(call.message, state, page, edit=True)
    await call.answer()


@router.callback_query(F.data.startswith("act:u:"))
async def activist_detail(call: CallbackQuery):
    _, _, user_id, page = call.data.split(":")
    user = await db.get_user(int(user_id))
    if not user:
        await call.answer("Faol topilmadi", show_alert=True)
        return
    username = f"@{escape(user['user_name'])}" if user["user_name"] else "—"
    month, year = get_current_month_year()
    score = await db.get_user_monthly_score(user["user_id"], month, year)
    adjustments = await db.get_recent_score_adjustments(user["user_id"])
    text = (
        "👤 <b>Faol ma’lumotlari</b>\n\n"
        f"<b>F.I.Sh:</b> {escape(str(user['full_name']))}\n"
        f"<b>Guruh:</b> {escape(str(user['group_name'] or '—'))}\n"
        f"<b>Username:</b> {username}\n"
        f"<b>Telegram ID:</b> <code>{user['user_id']}</code>\n"
        f"<b>Telefon:</b> {escape(str(user['phone_number'] or '—'))}\n"
        f"<b>Tug‘ilgan sana:</b> {user['birth_date'].strftime('%d-%m-%Y') if user['birth_date'] else '—'}\n"
        f"<b>Manzil:</b> {escape(str(user['location'] or '—'))}\n"
        f"<b>TTJ:</b> {'Ha' if user['lives_in_dormitory'] else 'Yo‘q'}\n"
        f"<b>{month}.{year} bali:</b> {score}\n"
        f"<b>Jarimalar:</b> {user['penalty_count']}\n"
        f"<b>Chetlatilgan:</b> {'Ha' if user['is_excluded'] else 'Yo‘q'}"
    )
    if adjustments:
        text += "\n\n🧾 <b>So‘nggi ball o‘zgarishlari:</b>"
        for row in adjustments:
            sign = "+" if row["amount"] > 0 else ""
            text += (
                f"\n• {row['month']}.{row['year']}: {sign}{row['amount']} — "
                f"{escape(str(row['reason'])[:120])}"
            )
    builder = InlineKeyboardBuilder()
    access = await get_access(db, call.from_user.id)
    if access.allows("manage_scores"):
        builder.button(text="➕ Ball qo‘shish", callback_data=f"act:score:{user_id}:{page}:add")
        builder.button(text="➖ Ball ayirish", callback_data=f"act:score:{user_id}:{page}:sub")
    builder.button(text="◀️ Ro‘yxatga qaytish", callback_data=f"act:p:{page}")
    builder.adjust(2, 1)
    await call.message.edit_text(text, reply_markup=builder.as_markup())
    await call.answer()


@router.callback_query(F.data == "act:search")
async def activists_search_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(ACTIVISTS.searching)
    await call.message.answer("🔎 F.I.Sh, username, guruh yoki Telegram ID ni kiriting:")
    await call.answer()


@router.message(ACTIVISTS.searching, ~F.text.startswith("/"))
async def activists_search(msg: Message, state: FSMContext):
    query = (msg.text or "").strip()
    if len(query) < 2:
        await msg.answer("Qidiruv uchun kamida 2 ta belgi kiriting.")
        return
    await state.set_state(None)
    await state.update_data(activists_query=query)
    await _render_list(msg, state)


@router.callback_query(F.data.startswith("act:score:"))
async def score_adjust_start(call: CallbackQuery, state: FSMContext):
    _, _, user_id, page, operation = call.data.split(":")
    if operation not in {"add", "sub"}:
        await call.answer("Noto‘g‘ri amal", show_alert=True)
        return
    user = await db.get_user(int(user_id))
    if not user:
        await call.answer("Faol topilmadi", show_alert=True)
        return
    await state.update_data(
        score_user_id=int(user_id), score_page=int(page), score_operation=operation,
        score_user_name=user["full_name"],
    )
    await state.set_state(ACTIVISTS.score_amount)
    action = "qo‘shiladigan" if operation == "add" else "ayiriladigan"
    await call.message.answer(
        f"✏️ <b>{escape(str(user['full_name']))}</b> uchun {action} ball miqdorini kiriting:"
    )
    await call.answer()


@router.message(ACTIVISTS.score_amount, ~F.text.startswith("/"))
async def score_adjust_amount(msg: Message, state: FSMContext):
    value = (msg.text or "").strip()
    if not value.isdigit() or not 1 <= int(value) <= 100000:
        await msg.answer("Ball 1–100000 oralig‘idagi musbat son bo‘lishi kerak.")
        return
    data = await state.get_data()
    amount = int(value) * (-1 if data.get("score_operation") == "sub" else 1)
    await state.update_data(score_amount_value=amount)
    await state.set_state(ACTIVISTS.score_reason)
    await msg.answer("📝 Ball o‘zgarishi sababini yozing (kamida 3 ta belgi):")


@router.message(ACTIVISTS.score_reason, ~F.text.startswith("/"))
async def score_adjust_reason(msg: Message, state: FSMContext):
    reason = (msg.text or "").strip()
    if not 3 <= len(reason) <= 500:
        await msg.answer("Izoh 3–500 belgidan iborat bo‘lishi kerak.")
        return
    data = await state.get_data()
    user_id = data.get("score_user_id")
    amount = data.get("score_amount_value")
    user = await db.get_user(user_id)
    if not user or not isinstance(amount, int) or amount == 0:
        await state.clear()
        await msg.answer("Faol yoki ball ma’lumoti topilmadi. Qaytadan urinib ko‘ring.")
        return
    month, year = get_current_month_year()
    saved = await db.add_score_adjustment(
        user_id, amount, reason, msg.from_user.id, month, year,
    )
    if not saved:
        await state.clear()
        await msg.answer("Faol topilmadi yoki uning holati o‘zgargan.")
        return
    score = await db.get_user_monthly_score(user_id, month, year)
    query = data.get("activists_query")
    await state.set_state(None)
    await state.set_data({"activists_query": query} if query else {})
    sign = "+" if amount > 0 else ""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="◀️ Faol ma’lumotiga qaytish",
        callback_data=f"act:u:{user_id}:{data.get('score_page', 0)}",
    )
    await msg.answer(
        f"✅ <b>{escape(str(user['full_name']))}</b>: {sign}{amount} ball saqlandi.\n"
        f"📝 Izoh: {escape(reason)}\n"
        f"📊 {month}.{year} uchun jami ball: <b>{score}</b>",
        reply_markup=builder.as_markup(),
    )
    await log_action(
        bot, msg.from_user,
        f"Faol balli o‘zgartirildi: {user['full_name']} ({user_id}), {sign}{amount}; sabab: {reason}",
    )


@router.callback_query(F.data == "act:noop")
async def activists_noop(call: CallbackQuery):
    await call.answer()


@router.callback_query(F.data == "act:close")
async def activists_close(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.delete()
    await call.message.answer("🛠 Admin paneli", reply_markup=await admin_menu(call.from_user.id))
    await call.answer()
