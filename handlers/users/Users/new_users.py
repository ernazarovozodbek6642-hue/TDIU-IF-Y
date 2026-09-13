import logging
import re
from datetime import datetime
from html import escape

from aiogram import Router, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from data.config import SUPER_ADMIN_ID
from keyboards.default.ADMIN_Keyboard import back_menu
from keyboards.default.Users_KEyboard import user_register, phone_number, user_main_menu
from keyboards.inline.user_inline import (
    confirmation_user, open_events_keyboard, my_active_events_keyboard, event_media_keyboard,
    edit_profile_keyboard, EDIT_PROFILE_FIELDS, dormitory_keyboard, student_review_keyboard
)
from loader import dp, db, bot
from states.Users_state import Users, EDIT_PROFILE, RegistrationReview
from utils.announcements import update_event_announcement
from utils.misc.funcsion import get_current_month_year, is_member_of_any_group
from utils.access import get_access
from utils.misc.upload_image import send_event_media, upload_photo_to_channel

router = Router()

STATUS_LABELS = {
    "pending": "⬜ Kutilmoqda",
    "confirmed": "✅ Tasdiqlangan",
    "rejected": "❌ Rad etilgan",
    "not_attended": "🚫 Kelmadingiz",
}


async def _join_event(target_bot, user_id: int, event_id: int):
    event = await db.get_event(event_id)
    if not event or event["is_closed"] or event["approval_status"] != "approved":
        await target_bot.send_message(user_id, "Bu tadbir uchun ro'yxatdan o'tish yopilgan")
        return

    user = await db.get_user(user_id)
    if not user:
        await target_bot.send_message(user_id, "Avval ro'yxatdan o'tib, arizangiz tasdiqlanishini kuting.")
        return
    if user and user["is_excluded"]:
        await target_bot.send_message(
            user_id,
            "⛔ Siz jarima chegarasiga yetganingiz sababli tadbirlarga yozilishdan chetlatilgansiz.\n"
            "Batafsil ma'lumot uchun adminga murojaat qiling."
        )
        return

    row, slot = await db.register_user_to_event(event_id, user_id)
    if slot == "forbidden":
        await target_bot.send_message(user_id, "Ro'yxatdan o'tish uchun profilingiz tasdiqlangan bo'lishi kerak.")
        return
    if slot == "full":
        await target_bot.send_message(
            user_id,
            f"😔 Afsuski, '{escape(str(event['event_name']))}' tadbirida asosiy va zaxira ro'yxatlar to'lgan."
        )
        return
    if slot == "waitlist":
        await target_bot.send_message(
            user_id,
            f"🔁 Siz '{escape(str(event['event_name']))}' tadbiriga <b>zaxira</b> ro'yxatiga yozildingiz.\n"
            f"Asosiy ro'yxatda joy bo'shasa, sizga xabar beramiz."
        )
    else:
        await target_bot.send_message(
            user_id, f"✅ Siz '{escape(str(event['event_name']))}' tadbirining asosiy ro'yxatiga yozildingiz!"
        )
    await update_event_announcement(target_bot, db, event_id)


@router.message(CommandStart())
async def start_user(msg: Message, command: CommandObject, state: FSMContext):
    await state.clear()
    access = await get_access(db, msg.from_user.id)
    if not access.role and not await is_member_of_any_group(bot, db, msg.from_user.id):
        await msg.answer(
            "⛔ Siz <b>Fakultet faollari</b> guruhida yo‘qsiz.\nBosh koordinatorga murojaat qiling."
        )
        return

    payload = command.args
    event_id = None
    if payload and payload.startswith("event_"):
        try:
            event_id = int(payload.split("_", 1)[1])
        except ValueError:
            event_id = None

    existing = await db.get_user_any_status(msg.from_user.id)
    if existing and existing["registration_status"] == "pending":
        await msg.answer("⏳ Arizangiz Super admin yoki Bosh koordinator tasdig‘ini kutmoqda.")
        return
    if existing and existing["registration_status"] == "rejected":
        reason = escape(existing["rejection_reason"] or "Sabab ko‘rsatilmagan")
        await msg.answer(
            f"❌ Arizangiz bekor qilingan.\n<b>Sabab:</b> {reason}\n\n"
            "Ma’lumotlarni tuzatib qayta ro‘yxatdan o‘tishingiz mumkin.",
            reply_markup=user_register,
        )
        return
    if not existing:
        if event_id:
            await state.update_data(pending_event_id=event_id)
        await msg.answer(text="Assalomu aleykum hurmatli faol!\n"
                              "Botdan foydalanish uchun to'liq royxatdan o'ting👇", reply_markup=user_register)
        return

    await msg.answer(text="Siz ro'yxatdan o'tgansiz", reply_markup=user_main_menu)
    if event_id:
        await _join_event(bot, msg.from_user.id, event_id)


@router.message(F.text == "🏠 Bosh Menyu")
async def back_menu_handler(msg: Message, state: FSMContext):
    await state.clear()
    if not await db.get_user(msg.from_user.id):
        await msg.answer(text="Botdan foydalanish uchun to'liq royxatdan o'ting👇", reply_markup=user_register)
    else:
        await msg.answer(text="Menyuni tanlang", reply_markup=user_main_menu)


@router.message(F.text == "📝 Ro'yxatdan o'tish")
async def register(msg: Message, state: FSMContext):
    await msg.answer(text="Familya, ism va o'tangizni ismini yozing📝\n"
                          "<b>Namuna:</b> <i>Ernazarov Ozodbek Ilhom o'g'li</i>")
    await state.set_state(Users.full_name)


@router.message(Users.full_name)
async def full_name(msg: Message, state: FSMContext):
    value = (msg.text or "").strip()
    if not 2 <= len(value) <= 150:
        await msg.answer("F.I.Sh 2–150 belgidan iborat bo'lsin.")
        return
    await state.update_data(full_name=value)
    await msg.answer(text="Guruhingizni kiriting👇\n"
                          "<b>Namuna:</b> <i>IRB-82/25</i>", reply_markup=back_menu)
    await state.set_state(Users.group_name)


@router.message(Users.group_name)
async def group_name(msg: Message, state: FSMContext):
    value = (msg.text or "").strip()
    if not 1 <= len(value) <= 100:
        await msg.answer("Guruh nomi 1–100 belgidan iborat bo'lsin.")
        return
    await state.update_data(group_name=value)
    await msg.answer(text="Passport seriya va raqamini kiriting👇\n"
                          "<b>Namuna:</b> <i>AD 5079121</i>", reply_markup=back_menu)
    await state.set_state(Users.passport_number)


@router.message(Users.passport_number)
async def passport_info(msg: Message, state: FSMContext):
    value = (msg.text or "").strip()
    if not 3 <= len(value) <= 50:
        await msg.answer("Passport ma'lumoti 3–50 belgidan iborat bo'lsin.")
        return
    await state.update_data(passport_info=value)
    await msg.answer(
        "Tug‘ilgan sanangizni kiriting.\n<b>Format:</b> <i>KK-OO-YYYY</i>\n"
        "<b>Namuna:</b> <i>25-12-2005</i>",
        reply_markup=back_menu,
    )
    await state.set_state(Users.birth_date)


@router.message(Users.birth_date)
async def birth_date(msg: Message, state: FSMContext):
    value = (msg.text or "").strip()
    try:
        parsed = datetime.strptime(value, "%d-%m-%Y").date()
    except ValueError:
        await msg.answer("Sana noto‘g‘ri. KK-OO-YYYY formatida kiriting, masalan: 25-12-2005")
        return
    if parsed.year < 1900 or parsed > datetime.now().date():
        await msg.answer("Tug‘ilgan sana 1900-yildan bugungi kungacha bo‘lishi kerak")
        return
    await state.update_data(birth_date=parsed.isoformat())
    await msg.answer(text="O'z telefon raqamingizni kiriting.\nBo'lmasam  pastdagi tugmachani bosing🔘\n"
                          "<b>Namuna:</b> <i>998979072609</i>", reply_markup=phone_number)
    await state.set_state(Users.phone_number)


@router.message(Users.phone_number, F.contact)
async def phone_number_(msg: Message, state: FSMContext):
    if msg.contact.user_id and msg.contact.user_id != msg.from_user.id:
        await msg.answer("Iltimos, o'zingizga tegishli telefon raqamini yuboring", reply_markup=phone_number)
        return
    normalized_phone = re.sub(r"[^0-9]", "", msg.contact.phone_number or "")
    if not re.fullmatch(r"998\d{9}", normalized_phone):
        await msg.answer("Telefon raqami 998XXXXXXXXX formatida bo'lishi kerak", reply_markup=phone_number)
        return
    await state.update_data(phone_number=normalized_phone)
    await msg.answer(text="Asl manzilingizni kiriting\n"
                          "<b>Namuna:</b> <i>Sirdaryo viloyati, Oqoltin tumani, Andijon MFY</i>",
                     reply_markup=back_menu)
    await state.set_state(Users.location)


@router.message(Users.phone_number)
async def phone_number_text(msg: Message, state: FSMContext):
    pattern = r"^998\d{9}$"
    if msg.text and re.match(pattern, msg.text):
        await state.update_data(phone_number=msg.text)
        await msg.answer(text="Asl manzilingizni kiriting📍\n"
                              "<b>Namuna:</b> <i>Sirdaryo viloyati, Oqoltin tumani, Andijon MFY</i>",
                         reply_markup=back_menu)
        await state.set_state(Users.location)
    else:
        await msg.answer(
            text="Telefon raqamingizni noto'g'ri farmatda kiritdingiz!\n Siz pastdagi tugmachani bosib yuborsangiz "
                 "bo'ladi🔘\n"
                 "<b>Namuna:</b> <i>998979072609</i>", reply_markup=phone_number)


@router.message(Users.location)
async def location_of_user(msg: Message, state: FSMContext):
    value = (msg.text or "").strip()
    if not 2 <= len(value) <= 255:
        await msg.answer("Manzil 2–255 belgidan iborat bo'lsin.")
        return
    await state.update_data(location=value)
    await msg.answer("🏠 TTJda turasizmi?", reply_markup=dormitory_keyboard)
    await state.set_state(Users.dormitory)


@router.callback_query(Users.dormitory, F.data.in_({"dormitory:yes", "dormitory:no"}))
async def dormitory_answer(call: CallbackQuery, state: FSMContext):
    lives_in_dormitory = call.data == "dormitory:yes"
    await state.update_data(lives_in_dormitory=lives_in_dormitory)
    await call.message.edit_text(f"🏠 TTJda turasizmi? {'✅ Ha' if lives_in_dormitory else '❌ Yo‘q'}")
    await call.message.answer(
        "📸 Iltimos, yuzingiz aniq va ravon ko'rinadigan rasmni yuboring.\n\n"
        "⚠️ <b>Eslatma:</b> Rasm oddiy formatda bo'lishi kerak, fayl sifatida emas.\n\n"
        "✅ Ushbu rasm siz ekanligingizni tasdiqlash uchun kerak, shuning uchun yuborishdan oldin "
        "uni yana bir bor tekshirib chiqing.",
        reply_markup=back_menu,
    )
    await state.set_state(Users.image)
    await call.answer()


@router.message(Users.image, F.photo)
async def image(msg: Message, state: FSMContext):
    data = await state.get_data()
    if not data.get("birth_date"):
        await msg.answer(
            "Ro‘yxatdan o‘tish yangilandi. Tug‘ilgan sanangizni KK-OO-YYYY formatida kiriting."
        )
        await state.set_state(Users.birth_date)
        return
    caption = (
        f"👤 <b>To'liq ismi:</b> <i>{escape(str(data.get('full_name', '')))}</i>\n\n"
        f"📚 <b>Guruh nomi:</b> <i>{escape(str(data.get('group_name', '')))}</i>\n\n"
        f"🆔 <b>Passport ma'lumoti:</b> <i>{escape(str(data.get('passport_info', '')))}</i>\n\n"
        f"🎂 <b>Tug‘ilgan sana:</b> <i>{datetime.fromisoformat(data['birth_date']).strftime('%d-%m-%Y')}</i>\n\n"
        f"📞 <b>Telefon raqami:</b> <i>{escape(str(data.get('phone_number', '')))}</i>\n\n"
        f"📍 <b>Manzil:</b> <i>{escape(str(data.get('location', '')))}</i>\n\n"
        f"🏠 <b>TTJda turadi:</b> <i>{'Ha' if data.get('lives_in_dormitory') else 'Yo‘q'}</i>\n\n"
    )
    photo_file_id, photo_message_id = await upload_photo_to_channel(
        bot, msg.photo[-1], caption=f"👤 {msg.from_user.id} - {escape(str(data.get('full_name') or ''))}"
    )
    await state.update_data(photo_file_id=photo_file_id, photo_message_id=photo_message_id)
    await msg.answer_photo(photo=photo_file_id, caption=caption, reply_markup=confirmation_user)


@router.callback_query(F.data == "conu:confirm")
async def confirm_user(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    required = ("full_name", "group_name", "passport_info", "birth_date", "phone_number", "location", "photo_file_id")
    if any(not data.get(key) for key in required) or "lives_in_dormitory" not in data:
        await call.answer("Ro'yxatdan o'tish ma'lumotlari to'liq emas", show_alert=True)
        return
    await db.add_user(
        user_id=call.from_user.id,
        user_name=call.from_user.username,
        full_name=data.get("full_name"),
        passport_number=data.get("passport_info"),
        birth_date=datetime.fromisoformat(data.get("birth_date")).date(),
        phone_number=str(data.get("phone_number")),
        location=data.get("location"),
        group_name=data.get("group_name"),
        profile_photo_file_id=data.get("photo_file_id"),
        profile_photo_message_id=data.get("photo_message_id"),
        lives_in_dormitory=data.get("lives_in_dormitory"),
        registration_status="pending",
    )
    await call.message.delete()
    await call.message.answer("⏳ Arizangiz yuborildi. Super admin yoki Bosh koordinator tasdig‘ini kuting.")

    review_caption = (
        "🆕 <b>Yangi talaba arizasi</b>\n\n"
        f"👤 <b>F.I.Sh:</b> {escape(str(data.get('full_name', '')))}\n"
        f"📚 <b>Guruh:</b> {escape(str(data.get('group_name', '')))}\n"
        f"🆔 <b>Passport:</b> {escape(str(data.get('passport_info', '')))}\n"
        f"🎂 <b>Tug‘ilgan sana:</b> {datetime.fromisoformat(data['birth_date']).strftime('%d-%m-%Y')}\n"
        f"📞 <b>Telefon:</b> {escape(str(data.get('phone_number', '')))}\n"
        f"📍 <b>Manzil:</b> {escape(str(data.get('location', '')))}\n"
        f"🏠 <b>TTJda turadi:</b> {'Ha' if data.get('lives_in_dormitory') else 'Yo‘q'}\n"
        f"🆔 <b>Telegram ID:</b> <code>{call.from_user.id}</code>"
    )
    reviewers = {SUPER_ADMIN_ID}
    for admin in await db.list_admin_access():
        if admin["role"] == "chief" and admin["active"]:
            reviewers.add(admin["user_id"])
    for reviewer_id in reviewers:
        try:
            await bot.send_photo(
                reviewer_id, data.get("photo_file_id"), caption=review_caption,
                reply_markup=student_review_keyboard(call.from_user.id),
            )
        except Exception:
            logging.exception("Student application notification failed for %s", reviewer_id)

    await state.clear()
    await call.answer("Ariza yuborildi")


async def _reviewer_allowed(user_id: int) -> bool:
    access = await get_access(db, user_id)
    return access.role in {"super", "chief"}


@router.message(F.text == "🆕 Yangi talabalar")
async def pending_students(msg: Message):
    if msg.chat.type != "private":
        await msg.answer("Talabalar arizalarini faqat bot bilan shaxsiy chatda ko'rish mumkin.")
        return
    if not await _reviewer_allowed(msg.from_user.id):
        await msg.answer("Bu amal uchun ruxsatingiz yo‘q")
        return
    users = await db.get_pending_users()
    if not users:
        await msg.answer("Hozir tasdiqlash kutilayotgan talaba yo‘q.")
        return
    await msg.answer(f"⏳ Tasdiqlash kutilayotgan arizalar: {len(users)} ta")
    for user in users:
        caption = (
            "🆕 <b>Yangi talaba arizasi</b>\n\n"
            f"👤 <b>F.I.Sh:</b> {escape(user['full_name'])}\n"
            f"📚 <b>Guruh:</b> {escape(user['group_name'] or '')}\n"
            f"🆔 <b>Passport:</b> {escape(user['passport_number'] or '')}\n"
            f"🎂 <b>Tug‘ilgan sana:</b> {user['birth_date'].strftime('%d-%m-%Y') if user['birth_date'] else 'Kiritilmagan'}\n"
            f"📞 <b>Telefon:</b> {escape(user['phone_number'] or '')}\n"
            f"📍 <b>Manzil:</b> {escape(user['location'] or '')}\n"
            f"🏠 <b>TTJda turadi:</b> {'Ha' if user['lives_in_dormitory'] else 'Yo‘q'}\n"
            f"🆔 <b>Telegram ID:</b> <code>{user['user_id']}</code>"
        )
        if user['profile_photo_file_id']:
            await msg.answer_photo(
                user['profile_photo_file_id'], caption=caption,
                reply_markup=student_review_keyboard(user['user_id']),
            )
        else:
            await msg.answer(caption, reply_markup=student_review_keyboard(user['user_id']))


@router.callback_query(F.data.startswith("studentapprove:"))
async def approve_student(call: CallbackQuery):
    if not await _reviewer_allowed(call.from_user.id):
        await call.answer("Bu amal uchun ruxsatingiz yo‘q", show_alert=True)
        return
    user_id = int(call.data.split(":", 1)[1])
    user = await db.review_user_registration(user_id, "approved", call.from_user.id)
    if not user:
        await call.answer("Bu ariza allaqachon ko‘rib chiqilgan", show_alert=True)
        return
    await call.message.edit_reply_markup(reply_markup=None)
    await call.message.reply(f"✅ Talaba tasdiqlandi: <b>{escape(user['full_name'])}</b>")
    try:
        await bot.send_message(user_id, "✅ Ro‘yxatdan o‘tishingiz tasdiqlandi. /start buyrug‘ini yuboring.")
    except Exception:
        logging.exception("Approval notification failed for student %s", user_id)
    await call.answer("Tasdiqlandi")


@router.callback_query(F.data.startswith("studentreject:"))
async def reject_student_start(call: CallbackQuery, state: FSMContext):
    if not await _reviewer_allowed(call.from_user.id):
        await call.answer("Bu amal uchun ruxsatingiz yo‘q", show_alert=True)
        return
    user_id = int(call.data.split(":", 1)[1])
    user = await db.get_user_any_status(user_id)
    if not user or user["registration_status"] != "pending":
        await call.answer("Bu ariza allaqachon ko‘rib chiqilgan", show_alert=True)
        return
    await state.update_data(
        review_user_id=user_id, review_message_chat=call.message.chat.id,
        review_message_id=call.message.message_id,
    )
    await state.set_state(RegistrationReview.rejection_reason)
    await call.message.answer(f"❌ <b>{escape(user['full_name'])}</b> arizasini bekor qilish sababini yozing:")
    await call.answer()


@router.message(RegistrationReview.rejection_reason)
async def reject_student_reason(msg: Message, state: FSMContext):
    if not await _reviewer_allowed(msg.from_user.id):
        await state.clear()
        await msg.answer("Bu amal uchun ruxsatingiz yo‘q")
        return
    reason = (msg.text or "").strip()
    if len(reason) < 3:
        await msg.answer("Bekor qilish sababini kamida 3 ta belgi bilan yozing.")
        return
    data = await state.get_data()
    user_id = data.get("review_user_id")
    user = await db.review_user_registration(user_id, "rejected", msg.from_user.id, reason)
    if not user:
        await state.clear()
        await msg.answer("Bu ariza allaqachon ko‘rib chiqilgan.")
        return
    try:
        await bot.edit_message_reply_markup(
            data.get("review_message_chat"), data.get("review_message_id"), reply_markup=None
        )
    except Exception:
        pass
    await state.clear()
    await msg.answer(
        f"❌ Ariza bekor qilindi: <b>{escape(user['full_name'])}</b>\n"
        f"<b>Sabab:</b> {escape(reason)}"
    )
    try:
        await bot.send_message(
            user_id,
            f"❌ Ro‘yxatdan o‘tish arizangiz bekor qilindi.\n<b>Sabab:</b> {escape(reason)}\n\n"
            "Ma’lumotlarni tuzatib qayta ro‘yxatdan o‘tishingiz mumkin.",
            reply_markup=user_register,
        )
    except Exception:
        logging.exception("Rejection notification failed for student %s", user_id)


@router.callback_query(F.data == "conu:again")
async def again_register(call: CallbackQuery, state: FSMContext):
    await call.message.delete()
    await call.message.answer(text="Qayta ro'yxatdan o'tish.\n\n"
                                   "Familya, ism va o'tangizni ismini yozing📝\n"
                                   "<b>Namuna:</b> <i>Ernazarov Ozodbek Ilhom o'g'li</i>")
    await state.set_state(Users.full_name)
    await call.answer()


@router.callback_query(F.data == "conu:back")
async def registration_back(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.delete()
    await call.message.answer("Menyuni tanlang", reply_markup=user_register)
    await call.answer()


# ----------------- FOYDALANUVCHI MENYUSI -----------------

@router.message(F.text == "👤 Mening profilim")
async def my_profile(msg: Message):
    user = await db.get_user(msg.from_user.id)
    if not user:
        await msg.answer("Siz hali ro'yxatdan o'tmagansiz", reply_markup=user_register)
        return
    text = (
        f"👤 <b>To'liq ismi:</b> {escape(str(user['full_name'] or ''))}\n"
        f"📚 <b>Guruh:</b> {escape(str(user['group_name'] or ''))}\n"
        f"📞 <b>Telefon:</b> {escape(str(user['phone_number'] or ''))}\n"
        f"🎂 <b>Tug‘ilgan sana:</b> {user['birth_date'].strftime('%d-%m-%Y') if user['birth_date'] else 'Kiritilmagan'}\n"
        f"📍 <b>Manzil:</b> {escape(str(user['location'] or ''))}\n"
        f"🏠 <b>TTJda turadi:</b> {'Ha' if user['lives_in_dormitory'] else 'Yo‘q'}\n"
        f"🚫 <b>Jarimalar soni:</b> {user['penalty_count']}\n"
    )
    if user["profile_photo_file_id"]:
        await msg.answer_photo(photo=user["profile_photo_file_id"], caption=text, reply_markup=edit_profile_keyboard())
    else:
        await msg.answer(text, reply_markup=edit_profile_keyboard())


@router.callback_query(F.data.startswith("editprofile:"))
async def edit_profile_start(call: CallbackQuery, state: FSMContext):
    field = call.data.split(":")[-1]
    if field not in EDIT_PROFILE_FIELDS:
        await call.answer("Noto'g'ri maydon", show_alert=True)
        return
    label = EDIT_PROFILE_FIELDS.get(field, field)
    await state.update_data(edit_field=field)

    if field == "profile_photo":
        await call.message.answer(f"{label} — yangi rasmni yuboring:")
        await state.set_state(EDIT_PROFILE.waiting_photo)
    else:
        await call.message.answer(f"{label} — yangi qiymatni kiriting:")
        await state.set_state(EDIT_PROFILE.waiting_value)
    await call.answer()


@router.callback_query(F.data == "profile:back")
async def profile_back(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.delete()
    await call.message.answer("Menyuni tanlang", reply_markup=user_main_menu)
    await call.answer()


@router.message(EDIT_PROFILE.waiting_value)
async def edit_profile_value(msg: Message, state: FSMContext):
    data = await state.get_data()
    field = data.get("edit_field")
    if field not in {"full_name", "group_name", "birth_date", "phone_number", "location"}:
        await state.clear()
        await msg.answer("Profil ma'lumoti noto'g'ri", reply_markup=user_main_menu)
        return
    value = (msg.text or "").strip()
    limits = {"full_name": 150, "group_name": 100, "birth_date": 10, "phone_number": 50, "location": 255}
    if not value or len(value) > limits[field]:
        await msg.answer(f"Qiymat bo'sh bo'lmasligi va {limits[field]} belgidan oshmasligi kerak")
        return
    if field == "phone_number" and not re.fullmatch(r"998\d{9}", value):
        await msg.answer("Telefon raqami 998XXXXXXXXX formatida bo'lishi kerak")
        return
    if field == "birth_date":
        try:
            parsed = datetime.strptime(value, "%d-%m-%Y").date()
        except ValueError:
            await msg.answer("Sana noto‘g‘ri. KK-OO-YYYY formatida kiriting")
            return
        if parsed.year < 1900 or parsed > datetime.now().date():
            await msg.answer("Tug‘ilgan sana 1900-yildan bugungi kungacha bo‘lishi kerak")
            return
        value = parsed
    await db.update_user(msg.from_user.id, **{field: value})
    await state.clear()
    await msg.answer("✅ Ma'lumot yangilandi", reply_markup=user_main_menu)


@router.message(EDIT_PROFILE.waiting_photo, F.photo)
async def edit_profile_photo(msg: Message, state: FSMContext):
    photo_file_id, photo_message_id = await upload_photo_to_channel(
        bot, msg.photo[-1], caption=f"👤 {msg.from_user.id} - profil rasmi yangilandi"
    )
    await db.update_user(
        msg.from_user.id,
        profile_photo_file_id=photo_file_id,
        profile_photo_message_id=photo_message_id,
    )
    await state.clear()
    await msg.answer("✅ Rasm yangilandi", reply_markup=user_main_menu)


@router.message(F.text == "📊 Mening ballarim")
async def my_score(msg: Message):
    user = await db.get_user(msg.from_user.id)
    if not user:
        await msg.answer("Siz hali ro'yxatdan o'tmagansiz", reply_markup=user_register)
        return
    month, year = get_current_month_year()
    score = await db.get_user_monthly_score(msg.from_user.id, month, year)
    await msg.answer(f"📊 <b>{month}.{year}</b> oyidagi ballaringiz: <b>{score}</b>")


@router.message(F.text == "🏆 Reyting")
async def rating(msg: Message):
    month, year = get_current_month_year()
    leaderboard = await db.get_monthly_leaderboard(month, year)
    winners = await db.get_all_time_winner_ids()
    if not leaderboard:
        await msg.answer("Bu oyda hali reyting mavjud emas")
        return
    lines = [f"🏆 <b>{month}.{year} oyi reytingi</b>\n"]
    for i, row in enumerate(leaderboard[:20], start=1):
        mark = "🏆 Oy talabasi | " if row["user_id"] in winners else ""
        lines.append(f"{i}. {mark}{escape(str(row['full_name']))} — {row['total_score']} ball")

    user_rank = None
    for i, row in enumerate(leaderboard, start=1):
        if row["user_id"] == msg.from_user.id:
            user_rank = (i, row["total_score"])
            break

    if user_rank and user_rank[0] > 20:
        lines.append(f"...\nSiz: {user_rank[0]}-o'rin — {user_rank[1]} ball")

    await msg.answer("\n".join(lines))


@router.message(F.text == "📅 Tadbirlarim")
async def my_events(msg: Message):
    user = await db.get_user(msg.from_user.id)
    if not user:
        await msg.answer("Siz hali ro'yxatdan o'tmagansiz", reply_markup=user_register)
        return

    joined = await db.get_user_upcoming_events(msg.from_user.id)
    joined_ids = {e["event_id"] for e in joined}

    lines = ["📅 <b>Sizning tadbirlaringiz:</b>\n"]
    if joined:
        for e in joined:
            wl = " (zaxira)" if e["is_waitlist"] and e["status"] == "pending" else ""
            lines.append(
                f"• <b>{escape(str(e['event_name']))}</b> — {e['date']} {e['time']} | "
                f"{STATUS_LABELS.get(e['status'], e['status'])}{wl}"
            )
    else:
        lines.append("— Hali hech qanday tadbirga yozilmagansiz")
    await msg.answer("\n".join(lines))

    active = [e for e in joined if e["status"] == "pending"]
    if active:
        await msg.answer(
            "Tadbir bilan bog'liq amallar:", reply_markup=my_active_events_keyboard(active)
        )

    all_open = await db.get_upcoming_events_open_for_registration()
    not_joined = [e for e in all_open if e["event_id"] not in joined_ids]
    if not_joined:
        await msg.answer(
            "🆕 <b>Ro'yxatdan o'tish mumkin bo'lgan tadbirlar:</b>",
            reply_markup=open_events_keyboard(not_joined)
        )

    confirmed = await db.get_user_confirmed_events(msg.from_user.id)
    media_events = []
    for e in confirmed:
        media = await db.get_event_media(e["event_id"])
        if media:
            media_events.append(e)
    if media_events:
        await msg.answer(
            "🖼 <b>Rasmlari mavjud tadbirlaringiz:</b>", reply_markup=event_media_keyboard(media_events)
        )


@router.callback_query(F.data.startswith("viewmedia:"))
async def view_event_media(call: CallbackQuery):
    event_id = int(call.data.split(":")[-1])
    event_user = await db.get_event_user(event_id, call.from_user.id)
    if not event_user or event_user["status"] != "confirmed":
        await call.answer("Siz bu tadbirga tasdiqlanmagansiz", show_alert=True)
        return

    media = await db.get_event_media(event_id)
    if not media:
        await call.answer("Hozircha rasm yo'q", show_alert=True)
        return

    await call.answer()
    await send_event_media(bot, call.from_user.id, media)


@router.callback_query(F.data == "userback:menu")
async def user_inline_back(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.delete()
    await call.message.answer("Menyuni tanlang", reply_markup=user_main_menu)
    await call.answer()


@router.callback_query(F.data.startswith("joinevent:"))
async def join_event_cb(call: CallbackQuery):
    event_id = int(call.data.split(":")[-1])
    await _join_event(bot, call.from_user.id, event_id)
    await call.answer("Amalga oshirildi")


@router.callback_query(F.data.startswith("withdraw:"))
async def withdraw_cb(call: CallbackQuery):
    event_id = int(call.data.split(":")[-1])
    event = await db.get_event(event_id)
    if not event or event["is_closed"] or event["approval_status"] != "approved":
        await call.answer("Bu tadbir uchun endi o'zgartirish mumkin emas", show_alert=True)
        return

    current = await db.get_event_user(event_id, call.from_user.id)
    if not current or current["status"] != "pending":
        await call.answer("Siz bu tadbirdan avval voz kechgansiz yoki holatni o'zgartirib bo'lmaydi", show_alert=True)
        return
    promoted = await db.withdraw_from_event(event_id, call.from_user.id)
    await call.answer("Siz tadbirdan voz kechdingiz")
    await call.message.answer(f"🚪 Siz '{escape(str(event['event_name']))}' tadbiridan voz kechdingiz")

    if promoted:
        try:
            await bot.send_message(
                promoted["user_id"],
                f"🎉 '{escape(str(event['event_name']))}' tadbirida joy bo'shadi — siz zaxiradan "
                f"asosiy ro'yxatga o'tkazildingiz!"
            )
        except Exception:
            pass

    await update_event_announcement(bot, db, event_id)

