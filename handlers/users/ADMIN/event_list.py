from utils.access import can_view_event
from html import escape
from keyboards.inline.Admin_keyboard_in import permitted_event_keyboard
from aiogram import Router, F

from aiogram.types import CallbackQuery, Message

from filters.is_admin import IsAdmin
from keyboards.inline.Admin_keyboard_in import (
    generate_event_by_month, generate_month_buttons,
    event_actions_keyboard, manual_attendance_keyboard
)
from loader import dp, db, bot
from utils.announcements import send_event_result
from utils.logger_channel import log_action
from utils.misc.funcsion import format_user
from utils.misc.upload_image import send_event_media

router = Router()
router.message.filter(IsAdmin())


async def _can_manage_event(event, user_id: int) -> bool:
    return await can_view_event(db, user_id, event)


def _append_name_section(text: str, title: str, rows, limit: int = 3900) -> str:
    if not rows:
        return text
    header = f"\n\n{title}\n"
    if len(text) + len(header) + 40 > limit:
        return text + f"\n\n{title} {len(rows)} ta (ro'yxat xabarga sig'madi)"
    text += header
    added = 0
    for row in rows:
        line = f"• {escape(str(row['full_name']))}\n"
        if len(text) + len(line) + 40 > limit:
            break
        text += line
        added += 1
    if added < len(rows):
        text += f"… va yana {len(rows) - added} ta"
    return text


@router.message(F.text == "📋Tadbirlar ro'yxati")
async def list_of_event(msg: Message):
    await msg.answer("Tadbirlar otkazilgan oyni tanglang", reply_markup=await generate_month_buttons(msg.from_user.id))


@router.callback_query(F.data == "backmonths")
async def back_to_months(call: CallbackQuery):
    await call.message.delete()
    await call.message.answer("Tadbirlar otkazilgan oyni tanglang", reply_markup=await generate_month_buttons(call.from_user.id))
    await call.answer()


@router.callback_query(F.data.startswith('month_'))
async def event_by_month(call: CallbackQuery):
    await call.answer()
    month = call.data.split('_')[1]
    event_keyboard = await generate_event_by_month(month, call.from_user.id)
    await call.message.delete()
    await call.message.answer(text="Tadbirni tanlang", reply_markup=event_keyboard)


async def _render_event_info(event_id: int):
    info = await db.get_event_full_info(event_id)
    event = info["event"]
    registered = info['registered']
    attended = info["attended"]
    not_attended = info["not_attended"]
    pending = info["pending"]

    responsible_person_name = "Tayinlanmagan"
    if event['responsible_person']:
        responsible_user = await db.get_user(event['responsible_person'])
        if responsible_user:
            responsible_person_name = await format_user(responsible_user)

    media_responsible_name = "Tayinlanmagan"
    if event['media_responsible']:
        media_user = await db.get_user(event['media_responsible'])
        if media_user:
            media_responsible_name = await format_user(media_user)

    method_labels = {"manual": "Qo'lda (Manual)", "photo": "2-bosqichli (tugma+rasm)"}
    status_text = "🔒 Yakunlangan" if event["is_closed"] else ("⏳ Tasdiqlash kutilmoqda" if event["approval_status"] == "pending" else "🟢 Faol")

    text = (
        f"📌 <b>{escape(str(event['event_name']))}</b> — {status_text}\n\n"
        f"📝 Ta'rif: {escape(str(event['description'] or ''))}\n"
        f"🗓 Sana: {event['date']}\n"
        f"⏰ Vaqt: {event['time']}\n"
        f"⭐ Ball: {event['score']} | 🚫 Jarima: {event['penalty_score']}\n"
        f"🔎 Tasdiqlash: {method_labels.get(event['verification_method'], event['verification_method'])}\n"
        f"👤 Mas'ul: {responsible_person_name}\n"
        f"🎥 Media: {media_responsible_name}\n\n"
    )

    location = str(event["location"] or "")
    if location.startswith("text:"):
        text += f"📍 Manzil: {escape(location[5:])}\n"
    elif location.startswith("geo:"):
        try:
            longitude, latitude = location[4:].split(".:", 1)
            text += f'📍 <a href="https://maps.google.com/?q={escape(latitude)},{escape(longitude)}">Xaritada ochish</a>\n'
        except ValueError:
            pass
    elif location:
        text += f"📍 Manzil: {escape(location)}\n"
    text += f"🟦 <b>Ro'yxatdan o'tganlar ({len(registered)}):</b>\n"
    text += f"🟩 <b>Tasdiqlangan:</b> {len(attended)}\n"
    text += f"⬜ <b>Kutilmoqda:</b> {len(pending)}\n"
    text += f"🟥 <b>Kelmagan/rad etilgan:</b> {len(not_attended)}\n"

    return text, event, registered


@router.callback_query(F.data.startswith('event:'))
async def event_by_id(call: CallbackQuery):
    event_id = int(call.data.split(':')[-1])
    event = await db.get_event(event_id)
    if not event or not await _can_manage_event(event, call.from_user.id):
        await call.answer("Ruxsat yo'q", show_alert=True)
        return
    text, event, _ = await _render_event_info(event_id)
    await call.message.delete()
    await call.message.answer(
        text, reply_markup=await permitted_event_keyboard(event, call.from_user.id)
    )
    await call.answer()


@router.callback_query(F.data.startswith('evattend:'))
async def event_attendance_list(call: CallbackQuery):
    event_id = int(call.data.split(':')[-1])
    event = await db.get_event(event_id)
    if not event or not await _can_manage_event(event, call.from_user.id):
        await call.answer("Ruxsat yo'q", show_alert=True)
        return
    info = await db.get_event_full_info(event_id)
    if not info["registered"]:
        await call.answer("Ro'yxatdan o'tganlar yo'q", show_alert=True)
        return
    await call.message.delete()
    await call.message.answer(
        "Talabani bosib, tasdiqlash holatini o'zgartiring:\n"
        "⬜ - kutilmoqda, ✅ - tasdiqlangan, 🚫 - kelmagan/rad etilgan",
        reply_markup=manual_attendance_keyboard(event_id, info["registered"])
    )
    await call.answer()


@router.callback_query(F.data.startswith('toggleattend:'))
async def toggle_attendance(call: CallbackQuery):
    _, event_id, user_id = call.data.split(':')
    event_id, user_id = int(event_id), int(user_id)
    event = await db.get_event(event_id)
    if not event or not await _can_manage_event(event, call.from_user.id):
        await call.answer("Ruxsat yo'q", show_alert=True)
        return

    event_user = await db.get_event_user(event_id, user_id)
    student = await db.get_user(user_id)
    if not event_user or not student or event_user["is_waitlist"] or event_user["status"] == "withdrawn":
        await call.answer("Ishtirokchi topilmadi yoki holati o‘zgargan", show_alert=True)
        return
    if event_user["status"] == "confirmed":
        changed = await db.unconfirm_attendance_manual(event_id, user_id)
        new_status = "⬜ kutilmoqda"
    else:
        changed = await db.confirm_attendance_manual(event_id, user_id, confirmed_by=call.from_user.id)
        new_status = "✅ tasdiqlandi"

    if not changed:
        await call.answer("Holat allaqachon o‘zgargan", show_alert=True)
        return

    info = await db.get_event_full_info(event_id)
    await call.message.edit_reply_markup(reply_markup=manual_attendance_keyboard(event_id, info["registered"]))
    await log_action(bot, call.from_user,
                      f"Qatnashuv o'zgartirildi (tadbir {event_id}): {student['full_name']} → {new_status}")
    await call.answer()


@router.callback_query(F.data.startswith('eventmedia:'))
async def event_media(call: CallbackQuery):
    event_id = int(call.data.split(':')[-1])
    event = await db.get_event(event_id)
    if not event or not await _can_manage_event(event, call.from_user.id):
        await call.answer("Ruxsat yo'q", show_alert=True)
        return

    media = await db.get_event_media(event_id)
    if not media:
        await call.answer("Bu tadbir uchun hozircha rasm yuklanmagan", show_alert=True)
        return

    await call.answer()
    await send_event_media(bot, call.from_user.id, media)


@router.callback_query(F.data.startswith('evclose:'))
async def close_event_handler(call: CallbackQuery):
    event_id = int(call.data.split(':')[-1])
    event = await db.get_event(event_id)
    if not event or not await _can_manage_event(event, call.from_user.id):
        await call.answer("Ruxsat yo'q", show_alert=True)
        return

    event, penalized = await db.close_event(event_id)

    penalty_threshold = int(await db.get_setting("penalty_threshold", "3") or 0)

    excluded_now = []
    if penalty_threshold > 0:
        for row in penalized:
            user = await db.get_user(row["user_id"])
            if user and user["penalty_count"] >= penalty_threshold and not user["is_excluded"]:
                await db.set_excluded(row["user_id"], True)
                excluded_now.append(user)

    text = f"🔒 <b>{escape(str(event['event_name']))}</b> tadbiri yakunlandi.\n\n"
    if penalized:
        text = _append_name_section(text, "🚫 Jarima berilgan talabalar:", penalized)
    else:
        text += "Barcha ro'yxatdagi talabalar tasdiqlangan ✅"

    if excluded_now:
        text = _append_name_section(
            text, "⛔ <b>Chetlatilganlar</b> (jarima chegarasiga yetdi):", excluded_now
        )

    await call.message.delete()
    await call.message.answer(text)
    await send_event_result(bot, db, event)
    await log_action(bot, call.from_user,
                      f"Tadbir yakunlandi: <b>{event['event_name']}</b> (ID {event_id}) — "
                      f"jarima: {len(penalized)} ta, chetlatildi: {len(excluded_now)} ta")
