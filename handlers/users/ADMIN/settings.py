from keyboards.default.ADMIN_Keyboard import admin_menu
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from filters.is_admin import IsAdmin
from keyboards.default.ADMIN_Keyboard import back_menu
from keyboards.inline.settings_inline import settings_menu_keyboard, once_per_student_keyboard, SETTINGS_LABELS
from loader import dp, db, bot
from states.Settings_state import SETTINGS
from utils.logger_channel import log_action

router = Router()
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

DEFAULTS = {
    "reminder_delay_minutes": "20",
    "penalty_threshold": "3",
    "once_per_student": "true",
    "top_n_winners": "5",
    "required_media_count": "3",
}


async def _get_settings_dict():
    values = {}
    for key, default in DEFAULTS.items():
        values[key] = await db.get_setting(key, default)
    return values


@router.message(F.text == "🏠 Bosh Menyu")
async def settings_home(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer(text="Menyuni tanlang", reply_markup=await admin_menu(msg.from_user.id))


@router.message(F.text == "⚙️ Sozlamalar")
async def settings_menu(msg: Message, state: FSMContext):
    await state.clear()
    values = await _get_settings_dict()
    await msg.answer("⚙️ <b>Bot sozlamalari</b>\nO'zgartirish uchun kerakli sozlamani tanlang:",
                     reply_markup=settings_menu_keyboard(values))


@router.callback_query(F.data.startswith("setting:"))
async def settings_choose(call: CallbackQuery, state: FSMContext):
    key = call.data.split(":", 1)[1]
    if key not in SETTINGS_LABELS:
        await call.answer("Noto'g'ri sozlama", show_alert=True)
        return
    await call.answer()
    if key == "once_per_student":
        await call.message.edit_text(
            f"{SETTINGS_LABELS[key]} — holatni tanlang:",
            reply_markup=once_per_student_keyboard()
        )
        return

    await call.message.delete()
    await call.message.answer(f"{SETTINGS_LABELS[key]} uchun yangi qiymatni kiriting (son):", reply_markup=back_menu)
    await state.update_data(setting_key=key)
    await state.set_state(SETTINGS.reminder_delay_minutes)


@router.callback_query(F.data == "settings:back")
async def settings_back(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("Menyuni tanlang")
    await call.message.answer("Admin paneli", reply_markup=await admin_menu(call.from_user.id))
    await call.answer()


@router.callback_query(F.data.startswith("setval:"))
async def settings_set_value(call: CallbackQuery):
    _, key, value = call.data.split(":")
    if key != "once_per_student" or value not in {"true", "false"}:
        await call.answer("Noto'g'ri sozlama qiymati", show_alert=True)
        return
    await db.set_setting(key, value)
    values = await _get_settings_dict()
    await call.message.edit_text(
        "⚙️ <b>Bot sozlamalari</b>\nO'zgartirish uchun kerakli sozlamani tanlang:",
        reply_markup=settings_menu_keyboard(values)
    )
    await log_action(bot, call.from_user, f"Sozlama yangilandi: {SETTINGS_LABELS.get(key, key)} = {value}")
    await call.answer("Saqlandi ✅")


@router.message(SETTINGS.reminder_delay_minutes)
async def settings_input_value(msg: Message, state: FSMContext):
    if not msg.text or not msg.text.isdigit():
        await msg.answer("Iltimos, faqat son kiriting")
        return
    value = int(msg.text)
    data = await state.get_data()
    key = data.get("setting_key")
    limits = {
        "reminder_delay_minutes": (1, 1440),
        "penalty_threshold": (1, 100),
        "top_n_winners": (1, 20),
        "required_media_count": (0, 100),
    }
    if key not in limits or not (limits[key][0] <= value <= limits[key][1]):
        await msg.answer("Qiymat ruxsat etilgan diapazondan tashqarida")
        return
    await db.set_setting(key, str(value))
    await state.clear()
    await msg.answer(f"{SETTINGS_LABELS.get(key, key)} yangilandi: {value} ✅", reply_markup=await admin_menu(msg.from_user.id))
    await log_action(bot, msg.from_user, f"Sozlama yangilandi: {SETTINGS_LABELS.get(key, key)} = {value}")
