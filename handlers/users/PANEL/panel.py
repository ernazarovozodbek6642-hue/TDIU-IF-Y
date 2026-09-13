from utils.access import get_access
from html import escape
from keyboards.inline.Admin_keyboard_in import permitted_event_keyboard
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from filters.is_responsible import IsResponsible
from keyboards.default.ADMIN_Keyboard import back_menu
from keyboards.default.Users_KEyboard import user_main_menu
from keyboards.inline.Admin_keyboard_in import event_actions_keyboard
from loader import dp, db, bot
from states.Admin_state import MEDIA
from utils.logger_channel import log_action
from openpyxl import Workbook
from io import BytesIO
from utils.misc.upload_image import upload_document_to_channel, upload_photo_to_channel
from utils.spreadsheets import safe_excel_value

router = Router()
router.message.filter(IsResponsible())


@router.message(F.text == "🔚 Chiqish")
async def panel_exit(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer(text="Bosh menyu", reply_markup=user_main_menu)


async def _send_my_events(msg: Message, user_id: int):
    access = await get_access(db, user_id)
    events = await db.get_scoped_events(None, user_id)
    events = [e for e in events if access.can_event(e, "reports")]
    if not events:
        await msg.answer("Sizga biriktirilgan faol tadbirlar yo'q")
        return

    for e in events:
        text = (
            f"📌 <b>{escape(str(e['event_name']))}</b>\n\n"
            f"📝 Ta'rif: {escape(str(e['description'] or ''))}\n"
            f"🗓 Sana: {e['date']} | ⏰ {e['time']}\n"
            f"⭐ Ball: {e['score']} | 🚫 Jarima: {e['penalty_score']}\n"
        )
        is_media = user_id == e["media_responsible"]
        await msg.answer(
            text, reply_markup=await permitted_event_keyboard(e, user_id, back_callback="panelevents")
        )


@router.message(F.text == "📋 Mening tadbirlarim")
async def my_events(msg: Message):
    await _send_my_events(msg, msg.from_user.id)


@router.callback_query(F.data == "panelevents")
async def panel_back_to_events(call: CallbackQuery):
    await call.message.delete()
    await _send_my_events(call.message, call.from_user.id)
    await call.answer()


@router.callback_query(F.data.startswith("eventexcel:"))
async def event_excel_report(call: CallbackQuery):
    if call.message.chat.type != "private":
        await call.answer("Hisobot faqat bot bilan shaxsiy chatda beriladi", show_alert=True)
        return
    event_id = int(call.data.split(":")[-1])
    event = await db.get_event(event_id)
    access = await get_access(db, call.from_user.id)
    if not event or not access.can_event(event, "reports"):
        await call.answer("Bu tadbir hisobotiga ruxsat yo‘q", show_alert=True)
        return
    info = await db.get_event_full_info(event_id)
    wb = Workbook()
    ws = wb.active
    ws.title = "Davomat hisoboti"
    ws.append(["№", "F.I.Sh", "Telefon", "Holat", "Zaxira", "Qo‘shilgan sana"])
    for number, row in enumerate(info["registered"], 1):
        ws.append([
            number, safe_excel_value(row["full_name"]), safe_excel_value(row["phone_number"]),
            row["status"], "Ha" if row["is_waitlist"] else "Yo‘q", "",
        ])
    for column in ws.columns:
        ws.column_dimensions[column[0].column_letter].width = 24
    buf = BytesIO()
    wb.save(buf)
    current = await get_access(db, call.from_user.id)
    if not current.can_event(event, "reports"):
        await call.answer("Hisobot ruxsati bekor qilindi", show_alert=True)
        return
    await call.message.answer_document(BufferedInputFile(buf.getvalue(), filename=f"davomat_{event_id}.xlsx"), caption=f"📊 {escape(str(event['event_name']))} tadbirining davomat hisoboti")
    await call.answer("Excel tayyor")
    await log_action(bot, call.from_user, f"Tadbir hisoboti olindi: {event_id}")


@router.callback_query(F.data.startswith("uploadmedia:"))
async def upload_media_start(call: CallbackQuery, state: FSMContext):
    event_id = int(call.data.split(":")[-1])
    event = await db.get_event(event_id)
    access = await get_access(db, call.from_user.id)
    if (not event or event["approval_status"] != "approved"
            or event["media_responsible"] != call.from_user.id
            or not access.can_event(event, "attendance")):
        await call.answer("Ruxsat yo'q", show_alert=True)
        return

    await state.update_data(media_event_id=event_id)
    await state.set_state(MEDIA.uploading)
    await call.message.answer(
        f"📸 '{escape(str(event['event_name']))}' tadbiri uchun rasmlarni yuboring.\n\n"
        f"⚠️ Iloji boricha rasmlarni <b>fayl (📎 document)</b> sifatida yuboring — shunda sifati siqilmaydi. "
        f"Oddiy rasm sifatida yuborsangiz ham qabul qilinadi, lekin Telegram uni siqib yuboradi.\n\n"
        f"Tugatgach <b>/exit</b> yozing.",
        reply_markup=back_menu
    )
    await call.answer()


@router.message(MEDIA.uploading, F.document)
async def upload_media_document(msg: Message, state: FSMContext):
    data = await state.get_data()
    event_id = data.get("media_event_id")
    event = await db.get_event(event_id)
    access = await get_access(db, msg.from_user.id)
    if (not event or event["approval_status"] != "approved"
            or event["media_responsible"] != msg.from_user.id
            or not access.can_event(event, "attendance")):
        await msg.answer("Tadbir topilmadi")
        await state.clear()
        return

    if not (msg.document.mime_type or "").startswith("image/"):
        await msg.answer("Iltimos, faqat rasm faylini yuboring")
        return

    file_id, message_id = await upload_document_to_channel(
        bot, msg.document, caption=f"📸 {escape(str(event['event_name']))} — media"
    )
    await db.add_event_media(event_id, file_id, message_id, uploaded_by=msg.from_user.id, file_type="document")
    await msg.answer("✅ Saqlandi (asl sifatda). Yana rasm yuborishingiz mumkin yoki /exit bilan chiqing.")
    await log_action(bot, msg.from_user, f"Tadbir rasmi yuklandi (tadbir {event_id}, fayl sifatida)")


@router.message(MEDIA.uploading, F.photo)
async def upload_media_photo(msg: Message, state: FSMContext):
    data = await state.get_data()
    event_id = data.get("media_event_id")
    event = await db.get_event(event_id)
    access = await get_access(db, msg.from_user.id)
    if (not event or event["approval_status"] != "approved"
            or event["media_responsible"] != msg.from_user.id
            or not access.can_event(event, "attendance")):
        await msg.answer("Tadbir topilmadi")
        await state.clear()
        return

    file_id, message_id = await upload_photo_to_channel(
        bot, msg.photo[-1], caption=f"📸 {escape(str(event['event_name']))} — media"
    )
    await db.add_event_media(event_id, file_id, message_id, uploaded_by=msg.from_user.id, file_type="photo")
    await msg.answer(
        "✅ Saqlandi (siqilgan holatda). Yana rasm yuborishingiz mumkin yoki /exit bilan chiqing.\n"
        "💡 Sifatni saqlash uchun keyingi safar fayl (📎 document) sifatida yuborishingiz mumkin."
    )
    await log_action(bot, msg.from_user, f"Tadbir rasmi yuklandi (tadbir {event_id}, oddiy rasm)")


