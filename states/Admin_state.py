from aiogram.fsm.state import State, StatesGroup


class EVENT(StatesGroup):
    direction = State()
    name_event = State()
    description = State()
    date = State()
    time = State()
    score = State()
    verification_method = State()
    penalty_score = State()
    participants_count = State()
    waitlist_count = State()
    location = State()
    responsible_person = State()
    media_responsible = State()
    media_choice = State()
    confirmation = State()


class VERIFY(StatesGroup):
    waiting_photo = State()


class GROUP(StatesGroup):
    group_id = State()


class MEDIA(StatesGroup):
    uploading = State()


class EDIT_EVENT(StatesGroup):
    waiting_value = State()


class BROADCAST(StatesGroup):
    waiting_message = State()


class WINNERS(StatesGroup):
    selecting = State()


class ACTIVISTS(StatesGroup):
    searching = State()
    score_amount = State()
    score_reason = State()


class ATTENDANCE(StatesGroup):
    searching = State()

