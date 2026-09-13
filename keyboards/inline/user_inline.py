from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

confirmation_user = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="Tasdiqlash✅", callback_data="conu:confirm"),
            InlineKeyboardButton(text="Qayta to'ldirish⟳", callback_data="conu:again")
        ],
        [InlineKeyboardButton(text="◀️ Ortga", callback_data="conu:back")]
    ]
)


dormitory_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[[
        InlineKeyboardButton(text="✅ Ha", callback_data="dormitory:yes"),
        InlineKeyboardButton(text="❌ Yo‘q", callback_data="dormitory:no"),
    ]]
)


def student_review_keyboard(user_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"studentapprove:{user_id}"),
        InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"studentreject:{user_id}"),
    ]])


def open_events_keyboard(events):
    builder = InlineKeyboardBuilder()
    for e in events:
        builder.add(InlineKeyboardButton(
            text=f"➕ {e['event_name']} ({e['date']})",
            callback_data=f"joinevent:{e['event_id']}"
        ))
    builder.add(InlineKeyboardButton(text="◀️ Ortga", callback_data="userback:menu"))
    builder.adjust(1)
    return builder.as_markup()


EDIT_PROFILE_FIELDS = {
    "full_name": "👤 F.I.Sh",
    "group_name": "📚 Guruh",
    "birth_date": "🎂 Tug‘ilgan sana",
    "phone_number": "📞 Telefon",
    "location": "📍 Manzil",
    "profile_photo": "🖼 Rasm",
}


def edit_profile_keyboard():
    builder = InlineKeyboardBuilder()
    for key, label in EDIT_PROFILE_FIELDS.items():
        builder.add(InlineKeyboardButton(text=f"✏️ {label}", callback_data=f"editprofile:{key}"))
    builder.add(InlineKeyboardButton(text="◀️ Ortga", callback_data="profile:back"))
    builder.adjust(1)
    return builder.as_markup()


def event_media_keyboard(events):
    builder = InlineKeyboardBuilder()
    for e in events:
        builder.add(InlineKeyboardButton(
            text=f"🖼 {e['event_name']}", callback_data=f"viewmedia:{e['event_id']}"
        ))
    builder.add(InlineKeyboardButton(text="◀️ Ortga", callback_data="userback:menu"))
    builder.adjust(1)
    return builder.as_markup()


def my_active_events_keyboard(events):
    builder = InlineKeyboardBuilder()
    for e in events:
        if e["verification_method"] == "photo":
            builder.add(InlineKeyboardButton(
                text=f"✅ Keldim: {e['event_name']}", callback_data=f"checkin:{e['event_id']}"
            ))
        builder.add(InlineKeyboardButton(
            text=f"🚪 Voz kechish: {e['event_name']}", callback_data=f"withdraw:{e['event_id']}"
        ))
    builder.add(InlineKeyboardButton(text="◀️ Ortga", callback_data="userback:menu"))
    builder.adjust(1)
    return builder.as_markup()
