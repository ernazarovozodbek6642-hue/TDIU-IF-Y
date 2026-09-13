from utils.access import get_access
from keyboards.default.ADMIN_Keyboard import admin_menu
import asyncio
import logging

from aiogram import Router, F
from aiogram.exceptions import TelegramRetryAfter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from filters.is_admin import IsAdmin
from keyboards.default.ADMIN_Keyboard import back_menu
from loader import dp, db, bot
from states.Admin_state import BROADCAST
from utils.logger_channel import log_action

router = Router()
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


def _confirm_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ Yuborish", callback_data="bcast:send"))
    builder.add(InlineKeyboardButton(text="❌ Bekor qilish", callback_data="bcast:cancel"))
    builder.adjust(2)
    return builder.as_markup()


@router.message(F.text == "✉️Faollarga habar yuborish")
async def broadcast_start(msg: Message, state: FSMContext):
    await state.clear()
    access = await get_access(db, msg.from_user.id)
    if access.role == "assistant":
        events = await db.get_scoped_events(access.direction_id, msg.from_user.id)
        events = [e for e in events if e["approval_status"] == "approved"]
        if not events:
            await msg.answer("Xabar yuborish uchun sizga tegishli tasdiqlangan tadbir yo‘q.")
            return
        builder = InlineKeyboardBuilder()
        for event in events[:50]:
            builder.button(text=str(event["event_name"])[:64], callback_data=f"bcast:event:{event['event_id']}")
        builder.adjust(1)
        await msg.answer("Qaysi tadbir ishtirokchilariga xabar yuborasiz? (so‘nggi 50 ta)", reply_markup=builder.as_markup())
        return
    await state.update_data(bcast_audience="Barcha faollar", bcast_role=access.role)
    await msg.answer("Barcha faollarga yuboriladigan matn, rasm, video yoki faylni yuboring.", reply_markup=back_menu)
    await state.set_state(BROADCAST.waiting_message)


@router.callback_query(F.data.startswith("bcast:event:"))
async def broadcast_event(call: CallbackQuery, state: FSMContext):
    event_id = int(call.data.split(":")[-1])
    event = await db.get_event(event_id)
    access = await get_access(db, call.from_user.id)
    if not event or event["approval_status"] != "approved" or not access.can_event(event, "broadcast"):
        await call.answer("Bu tadbir uchun ruxsat yo‘q.", show_alert=True)
        return
    await state.clear()
    await state.update_data(bcast_event_id=event_id, bcast_audience="Tanlangan tadbir ishtirokchilari", bcast_role=access.role)
    await state.set_state(BROADCAST.waiting_message)
    await call.message.answer("Shu tadbir ishtirokchilariga yuboriladigan xabarni yuboring.", reply_markup=back_menu)
    await call.answer()


@router.message(BROADCAST.waiting_message)
async def broadcast_preview(msg: Message, state: FSMContext):
    await state.update_data(bcast_chat_id=msg.chat.id, bcast_message_id=msg.message_id)
    data = await state.get_data()
    await msg.answer(
        f"Qabul qiluvchilar: {data.get('bcast_audience', 'Tanlanmagan')}. Xabarni yuborishni tasdiqlaysizmi?",
        reply_markup=_confirm_keyboard()
    )


@router.callback_query(F.data == "bcast:cancel")
async def broadcast_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.delete()
    await call.message.answer("Bekor qilindi", reply_markup=await admin_menu(call.from_user.id))
    await call.answer()


@router.callback_query(F.data == "bcast:send")
async def broadcast_send(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    chat_id = data.get("bcast_chat_id")
    message_id = data.get("bcast_message_id")
    await state.clear()

    if not chat_id or not message_id:
        await call.answer("Xabar topilmadi, qaytadan urinib ko'ring", show_alert=True)
        return

    await call.message.edit_text("⏳ Yuborilmoqda...")

    access = await get_access(db, call.from_user.id)
    event_id = data.get("bcast_event_id")
    event = await db.get_event(event_id) if event_id else None
    if (access.role != data.get("bcast_role")
            or (event_id and not access.can_event(event, "broadcast"))
            or (access.role == "assistant" and not event_id)):
        await call.message.answer("Rol yoki yo‘nalish o‘zgargan. Xabarni qaytadan tayyorlang.")
        return
    if event_id:
        users = await db.execute("SELECT user_id FROM event_users WHERE event_id=$1 AND status!='withdrawn'", event_id, fetch=True)
    else:
        users = await db.execute(
            "SELECT user_id FROM users WHERE registration_status='approved'", fetch=True
        )
    sent, failed = 0, 0
    for user in users:
        current = await get_access(db, call.from_user.id)
        if not current.allows("broadcast") or current.role != access.role or (event_id and not current.can_event(event, "broadcast")):
            await call.message.answer("Ruxsat o‘zgargani sababli qolgan xabarlarni yuborish to‘xtatildi.")
            break
        try:
            try:
                await bot.copy_message(user["user_id"], from_chat_id=chat_id, message_id=message_id)
            except TelegramRetryAfter as exc:
                await asyncio.sleep(exc.retry_after)
                await bot.copy_message(user["user_id"], from_chat_id=chat_id, message_id=message_id)
            sent += 1
        except Exception:
            failed += 1
            logging.exception("Broadcast yuborilmadi (user_id=%s)", user["user_id"])
        # Telegram flood limitiga tushmaslik uchun
        await asyncio.sleep(0.05)

    await call.message.answer(
        f"✉️ Yuborish yakunlandi:\n✅ Yetkazildi: {sent}\n❌ Yetkazilmadi: {failed}",
        reply_markup=await admin_menu(call.from_user.id)
    )
    await log_action(bot, call.from_user, f"Broadcast yuborildi: ✅ {sent} ta, ❌ {failed} ta")
    await call.answer()
