from keyboards.default.ADMIN_Keyboard import admin_menu
from datetime import datetime as dt
from html import escape

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from filters.is_admin import IsAdmin
from keyboards.default.ADMIN_Keyboard import back_menu
from keyboards.inline.edit_event_inline import (
    EDIT_FIELD_LABELS, DIGIT_FIELDS, PERSON_FIELDS,
    edit_event_fields_keyboard, edit_verification_method_keyboard, edit_person_pick_keyboard
)
from loader import dp, db, bot
from states.Admin_state import EDIT_EVENT
from utils.announcements import update_event_announcement
from utils.logger_channel import log_action
from utils.misc.funcsion import normalize_event_location

router = Router()
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

METHOD_LABELS = {"manual": "Qo'lda (Manual)", "photo": "2-bosqichli (tugma+rasm)"}


def _display_value(event, field: str) -> str:
    if field in PERSON_FIELDS:
        return str(event[field]) if event[field] else "Tayinlanmagan"
    if field == "verification_method":
        return METHOD_LABELS.get(event[field], event[field])
    return str(event[field])


@router.callback_query(F.data.startswith("editevent:"))
async def edit_event_start(call: CallbackQuery):
    event_id = int(call.data.split(":")[-1])
    event = await db.get_event(event_id)
    if not event:
        await call.answer("Tadbir topilmadi", show_alert=True)
        return
    await call.message.delete()
    await call.message.answer(
        f"✏️ <b>{escape(str(event['event_name']))}</b> — qaysi maydonni tahrirlaysiz?",
        reply_markup=edit_event_fields_keyboard(event_id)
    )
    await call.answer()


@router.callback_query(F.data.startswith("editfield:"))
async def edit_field_choose(call: CallbackQuery, state: FSMContext):
    _, event_id, field = call.data.split(":")
    event_id = int(event_id)
    if field not in EDIT_FIELD_LABELS:
        await call.answer("Noto'g'ri maydon", show_alert=True)
        return
    event = await db.get_event(event_id)
    if not event:
        await call.answer("Tadbir topilmadi", show_alert=True)
        return

    if field == "verification_method":
        await call.message.edit_text(
            f"{EDIT_FIELD_LABELS[field]} — yangi usulni tanlang:",
            reply_markup=edit_verification_method_keyboard(event_id)
        )
        await call.answer()
        return

    await call.message.delete()
    if field in PERSON_FIELDS:
        await call.message.answer(
            f"{EDIT_FIELD_LABELS[field]} — qidirish uchun F.I.Sh yozing:", reply_markup=back_menu
        )
    elif field == "date":
        await call.message.answer(
            f"{EDIT_FIELD_LABELS[field]} — yangi sanani kiriting (namuna: 25-12-2025):", reply_markup=back_menu
        )
    elif field == "time":
        await call.message.answer(
            f"{EDIT_FIELD_LABELS[field]} — yangi vaqtni kiriting (namuna: 14:30):", reply_markup=back_menu
        )
    elif field == "location":
        await call.message.answer(
            f"{EDIT_FIELD_LABELS[field]} — oddiy manzil yoki https:// havolani kiriting:", reply_markup=back_menu
        )
    else:
        await call.message.answer(f"{EDIT_FIELD_LABELS[field]} — yangi qiymatni kiriting:", reply_markup=back_menu)

    await state.update_data(edit_event_id=event_id, edit_field=field)
    await state.set_state(EDIT_EVENT.waiting_value)
    await call.answer()


@router.callback_query(F.data.startswith("editvmethod:"))
async def edit_verification_method_pick(call: CallbackQuery):
    _, event_id, method = call.data.split(":")
    event_id = int(event_id)
    if method not in METHOD_LABELS:
        await call.answer("Noto'g'ri tasdiqlash usuli", show_alert=True)
        return
    event = await db.get_event(event_id)
    if not event:
        await call.answer("Tadbir topilmadi", show_alert=True)
        return
    old_display = METHOD_LABELS.get(event["verification_method"])
    await db.update_event(event_id, verification_method=method)
    await call.message.delete()
    await _finish_edit(call.message, call.from_user, event_id, "verification_method",
                        old_display, METHOD_LABELS.get(method))
    await call.answer("Yangilandi ✅")


@router.callback_query(F.data.startswith("editback:"))
async def edit_back(call: CallbackQuery, state: FSMContext):
    event_id = int(call.data.split(":")[-1])
    event = await db.get_event(event_id)
    if not event:
        await call.answer("Tadbir topilmadi", show_alert=True)
        return
    await state.clear()
    await call.message.edit_text(
        f"✏️ <b>{escape(str(event['event_name']))}</b> — qaysi maydonni tahrirlaysiz?",
        reply_markup=edit_event_fields_keyboard(event_id),
    )
    await call.answer()


@router.message(EDIT_EVENT.waiting_value)
async def edit_field_value(msg: Message, state: FSMContext):
    data = await state.get_data()
    event_id = data.get("edit_event_id")
    field = data.get("edit_field")
    event = await db.get_event(event_id)
    if not event or field not in EDIT_FIELD_LABELS:
        await msg.answer("Tadbir yoki tahrir maydoni topilmadi")
        await state.clear()
        return

    old_display = _display_value(event, field)

    if field in PERSON_FIELDS:
        if not msg.text or not msg.text.strip():
            await msg.answer("Qidirish uchun ism kiriting")
            return
        users = await db.search_users(msg.text)
        if not users:
            await msg.answer("Hech kim topilmadi. Boshqa nom bilan qidirib ko'ring")
            return
        await msg.answer(
            "Topilgan natijalardan birini tanlang:",
            reply_markup=edit_person_pick_keyboard(event_id, field, users)
        )
        return

    if field == "date":
        try:
            value = dt.strptime(msg.text, "%d-%m-%Y").date()
        except (TypeError, ValueError):
            await msg.answer("Format noto'g'ri. Namuna: 25-12-2025")
            return
        new_display = msg.text
    elif field == "time":
        try:
            value = dt.strptime(msg.text, "%H:%M").time()
        except (TypeError, ValueError):
            await msg.answer("Format noto'g'ri. Namuna: 14:30")
            return
        new_display = msg.text
    elif field in DIGIT_FIELDS:
        if not msg.text or not msg.text.isdigit():
            await msg.answer("Iltimos, faqat son kiriting")
            return
        value = int(msg.text)
        minimum = 1 if field == "participants_count" else 0
        if not minimum <= value <= 100000:
            await msg.answer(f"Qiymat {minimum}–100000 oralig'ida bo'lsin")
            return
        new_display = msg.text
    else:
        value = (msg.text or "").strip()
        limits = {"event_name": 255, "description": 2000, "location": 255}
        if field not in limits or not value or len(value) > limits[field]:
            await msg.answer("Qiymat bo'sh yoki ruxsat etilgan uzunlikdan katta")
            return
        new_display = value
        if field == "location":
            value = normalize_event_location(value)

    await db.update_event(event_id, **{field: value})
    await state.clear()
    await _finish_edit(msg, msg.from_user, event_id, field, old_display, new_display)


@router.callback_query(F.data.startswith("editpick:"))
async def edit_person_pick(call: CallbackQuery, state: FSMContext):
    _, event_id, field, user_id = call.data.split(":")
    event_id, user_id = int(event_id), int(user_id)
    event = await db.get_event(event_id)
    user = await db.get_user(user_id)
    if not event or field not in PERSON_FIELDS or not user:
        await call.answer("Tadbir, maydon yoki foydalanuvchi topilmadi", show_alert=True)
        return
    old_display = _display_value(event, field)
    await db.update_event(event_id, **{field: user_id})
    await state.clear()
    await call.message.delete()
    await _finish_edit(call.message, call.from_user, event_id, field, old_display, user["full_name"])
    await call.answer("Yangilandi ✅")


async def _finish_edit(msg: Message, actor, event_id: int, field: str, old_display: str, new_display: str):

    label = EDIT_FIELD_LABELS.get(field, field)
    await msg.answer(
        f"✅ {escape(str(label))} yangilandi: {escape(str(old_display))} → {escape(str(new_display))}",
        reply_markup=await admin_menu(actor.id),
    )

    edit_note = f"{label}: {old_display} → {new_display}"
    await update_event_announcement(bot, db, event_id, edit_note=edit_note)
    await log_action(bot, actor, f"Tadbir tahrirlandi (ID {event_id}): {edit_note}")
