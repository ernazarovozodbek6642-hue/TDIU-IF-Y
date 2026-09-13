from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

panel_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="📋 Mening tadbirlarim")
        ],
        [
            KeyboardButton(text="🔚 Chiqish")
        ],
    ], resize_keyboard=True
)

location = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text='📍 Joylashuvni yuboring', request_location=True)
        ],
        [
            KeyboardButton(text="🏠 Bosh Menyu")
        ],
    ], resize_keyboard=True
)

back_menu = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="🏠 Bosh Menyu")
        ]
    ], resize_keyboard=True
)

async def admin_menu(user_id):
    from loader import db
    from utils.access import get_access
    access = await get_access(db, user_id)
    options = [
        ('create_event', '➕Tadbir yatatish'),
        (None, "📋Tadbirlar ro'yxati"),
        ('approve_event', '⏳ Tasdiqlash kutilmoqda'),
        ('broadcast', '✉️Faollarga habar yuborish'),
        ('reports', "📋 Mening tadbirlarim" if access.role == 'assistant' else "📊Faollar ma'lumoti(exel)"),
        ('winners', '🏆 Oy talabalari'),
    ]
    buttons = [KeyboardButton(text=text) for permission, text in options
               if access.role and (access.allows(permission) if permission else bool(access.permissions))]
    if access.role in {'super', 'chief'}:
        buttons.append(KeyboardButton(text='🆕 Yangi talabalar'))
    if access.role == 'super':
        buttons += [KeyboardButton(text='👥 Adminlar va ruxsatlar'), KeyboardButton(text='🏘 Guruhlar'), KeyboardButton(text='⚙️ Sozlamalar')]
    rows = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    rows.append([KeyboardButton(text='🔚 Chiqish')])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)
