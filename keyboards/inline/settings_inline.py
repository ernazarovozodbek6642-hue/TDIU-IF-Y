from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

SETTINGS_LABELS = {
    "reminder_delay_minutes": "⏰ Eslatma vaqti (daqiqa)",
    "penalty_threshold": "🚫 Chetlatish uchun jarima chegarasi",
    "once_per_student": "🏆 Bir marta g'olib bo'lish qoidasi",
    "top_n_winners": "🏅 Oy talabalari soni (TOP-N)",
    "required_media_count": "📸 Media uchun kamida nechta rasm",
}


def settings_menu_keyboard(settings: dict):
    builder = InlineKeyboardBuilder()
    for key, label in SETTINGS_LABELS.items():
        value = settings.get(key, "-")
        builder.add(InlineKeyboardButton(text=f"{label}: {value}", callback_data=f"setting:{key}"))
    builder.add(InlineKeyboardButton(text="◀️ Ortga", callback_data="settings:back"))
    builder.adjust(1)
    return builder.as_markup()


def once_per_student_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ Yoqilgan", callback_data="setval:once_per_student:true"))
    builder.add(InlineKeyboardButton(text="❌ O'chirilgan", callback_data="setval:once_per_student:false"))
    builder.add(InlineKeyboardButton(text="◀️ Ortga", callback_data="settings:back"))
    builder.adjust(2)
    return builder.as_markup()
