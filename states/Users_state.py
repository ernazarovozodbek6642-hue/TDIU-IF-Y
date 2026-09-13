from aiogram.fsm.state import State, StatesGroup


class Users(StatesGroup):
    full_name = State()
    group_name = State()
    passport_number = State()
    birth_date = State()
    phone_number = State()
    location = State()
    dormitory = State()
    image = State()


class EDIT_PROFILE(StatesGroup):
    waiting_value = State()
    waiting_photo = State()


class RegistrationReview(StatesGroup):
    rejection_reason = State()
