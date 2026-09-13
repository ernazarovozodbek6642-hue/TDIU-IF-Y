from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

user_register = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="📝 Ro'yxatdan o'tish")
        ]
    ], resize_keyboard=True
)

phone_number = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text='📞 Telefon raqam ulashish', request_contact=True)
        ]
    ], resize_keyboard=True
)

user_main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="📅 Tadbirlarim"),
            KeyboardButton(text="📊 Mening ballarim")
        ],
        [
            KeyboardButton(text="🏆 Reyting"),
            KeyboardButton(text="👤 Mening profilim")
        ],
    ], resize_keyboard=True
)
