from html import escape

from utils.access import get_access
from data.config import SUPER_ADMIN_ID
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from keyboards.default.ADMIN_Keyboard import back_menu
from keyboards.default.Users_KEyboard import user_main_menu
from keyboards.inline.verification_inline import confirmation_request_keyboard
from loader import dp, db, bot
from states.Admin_state import VERIFY
from utils.logger_channel import log_action
from utils.misc.upload_image import upload_photo_to_channel
from utils.reminders import cancel_reminder, schedule_reminder

router = Router()


@router.callback_query(F.data.startswith("checkin:"))
async def checkin(call: CallbackQuery, state: FSMContext):
    event_id = int(call.data.split(":")[-1])
    event = await db.get_event(event_id)
    if (not event or event["is_closed"] or event["approval_status"] != "approved"
            or event["verification_method"] != "photo"):
        await call.answer("Bu tadbir uchun endi tasdiqlash mumkin emas", show_alert=True)
        return

    event_user = await db.get_event_user(event_id, call.from_user.id)
    if not event_user or event_user["status"] not in {"pending", "rejected"} or event_user["is_waitlist"]:
        await call.answer("Siz allaqachon tasdiqlangansiz yoki bu tadbirga yozilmagansiz", show_alert=True)
        return

    await state.update_data(checkin_event_id=event_id)
    await state.set_state(VERIFY.waiting_photo)
    await call.message.answer(
        "📸 Iltimos, tadbirga kelganingizni tasdiqlovchi rasm yuboring.",
        reply_markup=back_menu
    )
    await call.answer()


@router.message(VERIFY.waiting_photo, F.photo)
async def submit_proof(msg: Message, state: FSMContext):
    data = await state.get_data()
    event_id = data.get("checkin_event_id")
    event = await db.get_event(event_id)
    if (not event or event["is_closed"] or event["approval_status"] != "approved"
            or event["verification_method"] != "photo"):
        await msg.answer("Bu tadbir uchun endi tasdiqlash mumkin emas", reply_markup=user_main_menu)
        await state.clear()
        return
    # Attendance proof is always reviewed by the event responsible person.
    # The media responsible person only uploads event media.
    confirmer_id = event["responsible_person"]
    if confirmer_id and not (await get_access(db, confirmer_id)).can_event(event, "attendance"):
        confirmer_id = SUPER_ADMIN_ID
    if not confirmer_id:
        await msg.answer("Bu tadbir uchun mas'ul shaxs tayinlanmagan, adminga murojaat qiling",
                         reply_markup=user_main_menu)
        await state.clear()
        return

    student = await db.get_user(msg.from_user.id)
    event_user = await db.get_event_user(event_id, msg.from_user.id)
    if not student or not event_user or event_user["status"] not in {"pending", "rejected"} or event_user["is_waitlist"]:
        await msg.answer("Bu tasdiqlash so'rovi endi amal qilmaydi", reply_markup=user_main_menu)
        await state.clear()
        return
    photo_file_id, photo_message_id = await upload_photo_to_channel(
        bot, msg.photo[-1], caption=(
            f"Tasdiqlovchi rasm — {escape(str(student['full_name']))} — "
            f"{escape(str(event['event_name']))}"
        )
    )

    saved = await db.submit_attendance_proof(
        event_id=event_id, user_id=msg.from_user.id,
        proof_photo_file_id=photo_file_id, proof_photo_message_id=photo_message_id,
        confirmer_id=confirmer_id, request_message_id=None,
    )
    if not saved:
        await msg.answer("Bu tasdiqlash so'rovi endi amal qilmaydi", reply_markup=user_main_menu)
        await state.clear()
        return

    caption = (
        f"⏰ <b>Tasdiqlash so'raladi</b>\n\n"
        f"🎉 Tadbir: {escape(str(event['event_name']))}\n"
        f"👤 Talaba: {escape(str(student['full_name']))}\n"
    )
    request_msg = await bot.send_photo(
        confirmer_id, photo_file_id, caption=caption,
        reply_markup=confirmation_request_keyboard(event_id, msg.from_user.id)
    )

    await db.update_verification_reminder(event_id, msg.from_user.id, request_msg.message_id)
    schedule_reminder(bot, db, event_id, msg.from_user.id)

    await msg.answer("✅ Rasmingiz yuborildi, mas'ul shaxs tasdiqlashini kuting", reply_markup=user_main_menu)
    await state.clear()


@router.callback_query(F.data.startswith("proofconfirm:"))
async def proof_confirm(call: CallbackQuery):
    _, event_id, user_id = call.data.split(":")
    event_id, user_id = int(event_id), int(user_id)

    event = await db.get_event(event_id)
    if not event or event["is_closed"] or event["approval_status"] != "approved":
        await call.answer("Tadbir allaqachon yakunlangan — endi tasdiqlash mumkin emas", show_alert=True)
        return
    event_user = await db.get_event_user(event_id, user_id)
    if not event_user or event_user["status"] != "pending":
        await call.answer("Ruxsat yo'q yoki so'rov allaqachon ko'rib chiqilgan", show_alert=True)
        return

    changed = await db.confirm_attendance_photo(event_id, user_id, confirmed_by=call.from_user.id)
    if not changed:
        await call.answer("So'rov allaqachon o'zgargan", show_alert=True)
        return
    cancel_reminder(event_id, user_id)
    student = await db.get_user(user_id)

    await call.message.edit_caption(caption=call.message.caption + "\n\n✅ <b>Tasdiqlandi</b>")
    try:
        await bot.send_message(user_id, f"✅ '{escape(str(event['event_name']))}' tadbiriga qatnashganingiz tasdiqlandi!")
    except Exception:
        pass
    await log_action(bot, call.from_user,
                      f"Rasm tasdiqlandi (tadbir {event_id}): {student['full_name']}")
    await call.answer("Tasdiqlandi")


@router.callback_query(F.data.startswith("proofreject:"))
async def proof_reject(call: CallbackQuery):
    _, event_id, user_id = call.data.split(":")
    event_id, user_id = int(event_id), int(user_id)

    event = await db.get_event(event_id)
    if not event or event["is_closed"] or event["approval_status"] != "approved":
        await call.answer("Tadbir allaqachon yakunlangan — endi o'zgartirish mumkin emas", show_alert=True)
        return

    event_user = await db.get_event_user(event_id, user_id)
    if not event_user or event_user["status"] != "pending":
        await call.answer("Ruxsat yo'q yoki so'rov allaqachon ko'rib chiqilgan", show_alert=True)
        return

    changed = await db.reject_attendance_photo(event_id, user_id)
    if not changed:
        await call.answer("So'rov allaqachon o'zgargan", show_alert=True)
        return
    cancel_reminder(event_id, user_id)
    student = await db.get_user(user_id)

    await call.message.edit_caption(caption=call.message.caption + "\n\n❌ <b>Rad etildi</b>")
    try:
        await bot.send_message(
            user_id,
            f"❌ '{escape(str(event['event_name']))}' tadbiri uchun yuborgan rasmingiz rad etildi. Qaytadan urinib ko'ring."
        )
    except Exception:
        pass
    await log_action(bot, call.from_user,
                      f"Rasm rad etildi (tadbir {event_id}): {student['full_name']}")
    await call.answer("Rad etildi")
