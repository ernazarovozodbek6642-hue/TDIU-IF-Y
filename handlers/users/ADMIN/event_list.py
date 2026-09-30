from utils.access import can_view_event
from html import escape
from keyboards.inline.Admin_keyboard_in import permitted_event_keyboard
from aiogram import Router, F
from aiogram.fsm.context import FSMContext

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
from states.Admin_state import ATTENDANCE

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
    elif location.startswith("link:"):
        text += f'📍 <a href="{escape(location[5:])}">Manzilni ochish</a>\n'
    elif location.startswith("geo:"):
        try:
            longitude, latitude = location[4:].split(".:", 1)
            text += f'📍 <a href="https://maps.google.com/?q={escape(latitude)},{escape(longitude)}">Xaritada ochish</a>\n'
        except ValueError:
            pass
    elif location.startswith(("http://", "https://")):
        text += f'📍 <a href="{escape(location)}">Manzilni ochish</a>\n'
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


async def _render_attendance(target, event_id: int, state: FSMContext,
                             page: int = 0, edit: bool = False):
    data = await state.get_data()
    query = (data.get("attendance_query") or "").strip()
    if data.get("attendance_event_id") != event_id:
        query = ""
        await state.update_data(attendance_event_id=event_id, attendance_query="")
    total = int(await db.count_event_participants(event_id, query))
    pages = max(1, (total + 14) // 15)
    page = min(max(0, page), pages - 1)
    users = await db.get_event_participants_page(event_id, 15, page * 15, query)
    query_line = f"\n🔎 Qidiruv: <b>{escape(query)}</b>" if query else ""
    text = (
        "Talabani bosib, tasdiqlash holatini o‘zgartiring:\n"
        "⬜ — kutilmoqda, ✅ — tasdiqlangan, 🚫 — kelmagan/rad etilgan"
        f"{query_line}\nJami: <b>{total}</b> ta"
    )
    markup = manual_attendance_keyboard(event_id, users, page, total, query)
    if edit:
        await target.edit_text(text, reply_markup=markup)
    else:
        await target.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith('evattend:'))
async def event_attendance_list(call: CallbackQuery, state: FSMContext):
    event_id = int(call.data.split(':')[-1])
    event = await db.get_event(event_id)
    if not event or not await _can_manage_event(event, call.from_user.id):
        await call.answer("Ruxsat yo'q", show_alert=True)
        return
    if not await db.count_event_participants(event_id):
        await call.answer("Ro'yxatdan o'tganlar yo'q", show_alert=True)
        return
    await state.update_data(attendance_event_id=event_id, attendance_query="")
    await call.message.delete()
    await _render_attendance(call.message, event_id, state)
    await call.answer()


@router.callback_query(F.data.startswith('attpage:'))
async def attendance_page(call: CallbackQuery, state: FSMContext):
    _, event_id, page = call.data.split(':')
    await _render_attendance(call.message, int(event_id), state, int(page), edit=True)
    await call.answer()


@router.callback_query(F.data.startswith('attsearch:'))
async def attendance_search_start(call: CallbackQuery, state: FSMContext):
    event_id = int(call.data.split(':')[-1])
    await state.update_data(attendance_event_id=event_id)
    await state.set_state(ATTENDANCE.searching)
    await call.message.answer("🔎 Talabaning F.I.Sh, username, guruhi yoki Telegram ID sini kiriting:")
    await call.answer()


@router.message(ATTENDANCE.searching, ~F.text.startswith('/'))
async def attendance_search_query(msg: Message, state: FSMContext):
    query = (msg.text or "").strip()
    if len(query) < 2:
        await msg.answer("Qidiruv uchun kamida 2 ta belgi kiriting.")
        return
    data = await state.get_data()
    event_id = data.get("attendance_event_id")
    await state.set_state(None)
    await state.update_data(attendance_query=query)
    await _render_attendance(msg, event_id, state)


@router.callback_query(F.data.startswith('attall:'))
async def attendance_show_all(call: CallbackQuery, state: FSMContext):
    event_id = int(call.data.split(':')[-1])
    await state.update_data(attendance_event_id=event_id, attendance_query="")
    await _render_attendance(call.message, event_id, state, edit=True)
    await call.answer()


@router.callback_query(F.data == 'attnoop')
async def attendance_noop(call: CallbackQuery):
    await call.answer()


@router.callback_query(F.data.startswith('toggleattend:'))
async def toggle_attendance(call: CallbackQuery, state: FSMContext):
    parts = call.data.split(':')
    _, event_id, user_id = parts[:3]
    event_id, user_id = int(event_id), int(user_id)
    page = int(parts[3]) if len(parts) > 3 else 0
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

    await _render_attendance(call.message, event_id, state, page, edit=True)
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
