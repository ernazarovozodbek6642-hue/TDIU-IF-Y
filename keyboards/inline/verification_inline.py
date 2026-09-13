from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def checkin_keyboard(event_id: int):
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ Keldim", callback_data=f"checkin:{event_id}"))
    return builder.as_markup()


def confirmation_request_keyboard(event_id: int, user_id: int):
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"proofconfirm:{event_id}:{user_id}"))
    builder.add(InlineKeyboardButton(text="❌ Rad etish", callback_data=f"proofreject:{event_id}:{user_id}"))
    builder.adjust(2)
    return builder.as_markup()
