from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

EDIT_FIELD_LABELS = {
    "event_name": "🎉 Nomi",
    "description": "📝 Tavsif",
    "date": "📅 Sana",
    "time": "⏰ Vaqt",
    "score": "⭐ Ball",
    "penalty_score": "🚫 Jarima bali",
    "participants_count": "👥 Qatnashchilar soni",
    "waitlist_count": "🔁 Zaxira soni",
    "location": "📍 Manzil",
    "responsible_person": "👤 Mas'ul shaxs",
    "media_responsible": "🎥 Media mas'ul",
    "verification_method": "🔎 Tasdiqlash usuli",
}

DIGIT_FIELDS = {"score", "penalty_score", "participants_count", "waitlist_count"}
PERSON_FIELDS = {"responsible_person", "media_responsible"}


def edit_event_fields_keyboard(event_id: int):
    builder = InlineKeyboardBuilder()
    for key, label in EDIT_FIELD_LABELS.items():
        builder.add(InlineKeyboardButton(text=f"✏️ {label}", callback_data=f"editfield:{event_id}:{key}"))
    builder.add(InlineKeyboardButton(text="◀️ Ortga", callback_data=f"event:{event_id}"))
    builder.adjust(1)
    return builder.as_markup()


def edit_verification_method_keyboard(event_id: int):
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✋ Qo'lda (Manual)", callback_data=f"editvmethod:{event_id}:manual"))
    builder.add(InlineKeyboardButton(text="📸 2-bosqichli (tugma+rasm)", callback_data=f"editvmethod:{event_id}:photo"))
    builder.add(InlineKeyboardButton(text="◀️ Ortga", callback_data=f"editback:{event_id}"))
    builder.adjust(1)
    return builder.as_markup()


def edit_person_pick_keyboard(event_id: int, field: str, users):
    builder = InlineKeyboardBuilder()
    for u in users:
        builder.add(InlineKeyboardButton(text=u["full_name"], callback_data=f"editpick:{event_id}:{field}:{u['user_id']}"))
    builder.add(InlineKeyboardButton(text="◀️ Ortga", callback_data=f"editback:{event_id}"))
    builder.adjust(1)
    return builder.as_markup()
