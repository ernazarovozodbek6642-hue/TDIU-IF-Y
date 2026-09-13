from keyboards.default.ADMIN_Keyboard import admin_menu
import logging
from html import escape

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from filters.is_admin import IsAdmin
from loader import dp, db, bot
from states.Admin_state import WINNERS
from utils.logger_channel import log_action
from utils.misc.funcsion import get_current_month_year, get_prev_month_year

router = Router()
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


def _month_pick_keyboard():
    cm, cy = get_current_month_year()
    pm, py = get_prev_month_year()
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text=f"📅 Joriy oy ({cm}.{cy})", callback_data=f"wm:{cm}:{cy}"))
    builder.add(InlineKeyboardButton(text=f"📅 O'tgan oy ({pm}.{py})", callback_data=f"wm:{pm}:{py}"))
    builder.adjust(1)
    return builder.as_markup()


def _selection_keyboard(month: int, year: int, candidates, selected_ids):
    builder = InlineKeyboardBuilder()
    for c in candidates:
        mark = "✅" if c["user_id"] in selected_ids else "⬜"
        builder.add(InlineKeyboardButton(
            text=f"{mark} {c['full_name']} — {c['total_score']} ball"[:64],
            callback_data=f"wtog:{month}:{year}:{c['user_id']}"
        ))
    builder.add(InlineKeyboardButton(text="📢 E'lon qilish", callback_data=f"wpub:{month}:{year}"))
    builder.add(InlineKeyboardButton(text="◀️ Ortga", callback_data="wback"))
    builder.adjust(1)
    return builder.as_markup()


def _announced_keyboard(month: int, year: int):
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="🔄 Yetkazilmagan guruhlarga yuborish", callback_data=f"wretry:{month}:{year}"))
    builder.add(InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"wcancel:{month}:{year}"))
    builder.add(InlineKeyboardButton(text="◀️ Ortga", callback_data="wback"))
    builder.adjust(1)
    return builder.as_markup()


def _winner_announcement_text(month: int, year: int, winners):
    lines = ["#oy_talabasi", f"🏆 <b>{month}.{year} oyining eng faol talabalari:</b>", ""]
    for index, winner in enumerate(winners, 1):
        score = winner.get("total_score", winner.get("score", 0))
        lines.append(f"{index}. {escape(str(winner['full_name']))} — {score} ball")
    lines.append("\n🎉 Tabriklaymiz!")
    return "\n".join(lines)


async def _send_missing_winner_announcements(month: int, year: int, text: str):
    delivered = {row["group_id"] for row in await db.get_winner_messages(month, year)}
    sent = failed = 0
    for group in await db.get_all_groups():
        if group["group_id"] in delivered:
            continue
        try:
            msg = await bot.send_message(group["group_id"], text)
            await db.add_winner_message(month, year, group["group_id"], msg.message_id)
            sent += 1
            try:
                await bot.pin_chat_message(group["group_id"], msg.message_id, disable_notification=True)
            except Exception:
                logging.warning("Oy g'oliblari xabarini pin qilib bo'lmadi (group_id=%s)", group["group_id"])
        except Exception:
            failed += 1
            logging.exception("Guruhga oy talabalari e'lonini yuborishda xatolik (group_id=%s)", group["group_id"])
    return sent, failed


@router.message(F.text == "🏆 Oy talabalari")
async def winners_menu(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("🏆 Qaysi oy uchun oy talabalarini boshqarasiz?", reply_markup=_month_pick_keyboard())


@router.callback_query(F.data == "wback")
async def winners_back(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text(
        "🏆 Qaysi oy uchun oy talabalarini boshqarasiz?", reply_markup=_month_pick_keyboard()
    )
    await call.answer()


@router.callback_query(F.data.startswith("wm:"))
async def winners_month(call: CallbackQuery, state: FSMContext):
    _, month, year = call.data.split(":")
    month, year = int(month), int(year)

    existing = await db.get_monthly_winners(month, year)
    if existing:
        lines = [f"🏆 <b>{month}.{year} oyi talabalari (e'lon qilingan):</b>\n"]
        lines += [f"{w['rank']}. {escape(str(w['full_name']))} — {w['score']} ball" for w in existing]
        await call.message.edit_text("\n".join(lines), reply_markup=_announced_keyboard(month, year))
        await call.answer()
        return

    top_n = min(20, int(await db.get_setting("top_n_winners", "5")))
    once_per_student = (await db.get_setting("once_per_student", "true")) == "true"

    leaderboard = await db.get_monthly_leaderboard(month, year)
    if not leaderboard:
        await call.answer("Bu oy uchun reyting ma'lumotlari yo'q", show_alert=True)
        return

    previous_winner_ids = await db.get_all_time_winner_ids() if once_per_student else set()
    candidates = [r for r in leaderboard if r["user_id"] not in previous_winner_ids][:top_n]
    if not candidates:
        await call.answer("Nomzodlar topilmadi (hammasi avval g'olib bo'lgan)", show_alert=True)
        return

    selected = [c["user_id"] for c in candidates]
    await state.set_state(WINNERS.selecting)
    await state.update_data(
        w_month=month, w_year=year, w_selected=selected,
        w_candidates=[
            {"user_id": c["user_id"], "full_name": c["full_name"], "total_score": float(c["total_score"])}
            for c in candidates
        ],
    )
    await call.message.edit_text(
        f"🏆 <b>{month}.{year} oyi — TOP-{len(candidates)} nomzodlar</b>\n\n"
        f"Talabani bosib tanlovdan chiqarish/qo'shish mumkin.\n"
        f"Tayyor bo'lgach «📢 E'lon qilish» tugmasini bosing:",
        reply_markup=_selection_keyboard(month, year, candidates, set(selected))
    )
    await call.answer()


@router.callback_query(WINNERS.selecting, F.data.startswith("wtog:"))
async def winners_toggle(call: CallbackQuery, state: FSMContext):
    _, month, year, user_id = call.data.split(":")
    month, year, user_id = int(month), int(year), int(user_id)

    data = await state.get_data()
    if data.get("w_month") != month or data.get("w_year") != year:
        await call.answer("Eski tugma. Oyni qaytadan tanlang.", show_alert=True)
        await state.clear()
        return
    candidates = data.get("w_candidates", [])
    selected = set(data.get("w_selected", []))

    if user_id in selected:
        selected.discard(user_id)
    else:
        selected.add(user_id)

    await state.update_data(w_selected=list(selected))
    await call.message.edit_reply_markup(
        reply_markup=_selection_keyboard(month, year, candidates, selected)
    )
    await call.answer()


@router.callback_query(WINNERS.selecting, F.data.startswith("wpub:"))
async def winners_publish(call: CallbackQuery, state: FSMContext):
    _, month, year = call.data.split(":")
    month, year = int(month), int(year)

    data = await state.get_data()
    if data.get("w_month") != month or data.get("w_year") != year:
        await call.answer("Eski tugma. Oyni qaytadan tanlang.", show_alert=True)
        await state.clear()
        return
    candidates = data.get("w_candidates", [])
    selected = set(data.get("w_selected", []))
    chosen = [c for c in candidates if c["user_id"] in selected]

    if not chosen:
        await call.answer("Kamida bitta talabani tanlang", show_alert=True)
        return

    current = {r["user_id"]: r for r in await db.get_monthly_leaderboard(month, year)}
    if any(c["user_id"] not in current for c in chosen):
        await call.answer("Reyting o'zgargan. Oyni qaytadan tanlang.", show_alert=True)
        await state.clear()
        return
    chosen = [
        {"user_id": c["user_id"], "full_name": current[c["user_id"]]["full_name"],
         "total_score": float(current[c["user_id"]]["total_score"])}
        for c in chosen
    ]
    once_per_student = (await db.get_setting("once_per_student", "true")) == "true"
    saved = await db.save_monthly_winners_once(month, year, chosen, once_per_student)
    if saved is None:
        await state.clear()
        await call.answer("Bu oy allaqachon e'lon qilingan yoki tanlov qoidasi o'zgargan.", show_alert=True)
        return

    text = _winner_announcement_text(month, year, chosen)
    sent, failed = await _send_missing_winner_announcements(month, year, text)

    for c in chosen:
        try:
            await bot.send_message(
                c["user_id"],
                f"🎉 Tabriklaymiz! Siz {month}.{year} oyining <b>eng faol talabalari</b> qatoriga kirdingiz! 🏆"
            )
        except Exception:
            pass

    await state.clear()
    await call.message.edit_text(
        f"✅ {month}.{year} oyi talabalari e'lon qilindi ({len(chosen)} ta). "
        f"Guruhlarga yuborildi: {sent}, yetkazilmadi: {failed}.\n\n" +
        "\n".join(f"{i}. {escape(str(c['full_name']))}" for i, c in enumerate(chosen, 1))
    )
    await call.message.answer("Menyuni tanlang", reply_markup=await admin_menu(call.from_user.id))
    await log_action(bot, call.from_user, f"Oy talabalari e'lon qilindi: {month}.{year} — {len(chosen)} ta")
    await call.answer("E'lon qilindi ✅")


@router.callback_query(F.data.startswith("wretry:"))
async def winners_retry_delivery(call: CallbackQuery):
    _, month, year = call.data.split(":")
    month, year = int(month), int(year)
    winners = await db.get_monthly_winners(month, year)
    if not winners:
        await call.answer("Bu oy uchun e'lon topilmadi", show_alert=True)
        return
    sent, failed = await _send_missing_winner_announcements(
        month, year, _winner_announcement_text(month, year, winners)
    )
    await call.answer(f"Yuborildi: {sent}, yetkazilmadi: {failed}", show_alert=True)


@router.callback_query(F.data.startswith("wcancel:"))
async def winners_cancel(call: CallbackQuery):
    _, month, year = call.data.split(":")
    month, year = int(month), int(year)

    messages = await db.get_winner_messages(month, year)
    for m in messages:
        try:
            await bot.delete_message(m["group_id"], m["message_id"])
        except Exception:
            pass
    await db.delete_winner_messages(month, year)
    await db.delete_monthly_winners(month, year)

    await call.message.edit_text(
        f"❌ {month}.{year} oyi talabalari bekor qilindi.\n"
        f"Guruhlardagi e'lon xabarlari o'chirildi.",
        reply_markup=_month_pick_keyboard()
    )
    await log_action(bot, call.from_user, f"Oy talabalari bekor qilindi: {month}.{year}")
    await call.answer("Bekor qilindi")
