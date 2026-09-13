from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def groups_list_keyboard(groups):
    builder = InlineKeyboardBuilder()
    for g in groups:
        title = g["title"] or str(g["group_id"])
        builder.add(InlineKeyboardButton(text=f"❌ {title}"[:64], callback_data=f"delgroup:{g['group_id']}"))
    builder.add(InlineKeyboardButton(text="◀️ Ortga", callback_data="groups:back"))
    builder.adjust(1)
    return builder.as_markup()
