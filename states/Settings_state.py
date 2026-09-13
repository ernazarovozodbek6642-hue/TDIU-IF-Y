from aiogram.fsm.state import State, StatesGroup


class SETTINGS(StatesGroup):
    reminder_delay_minutes = State()
    penalty_threshold = State()
    top_n_winners = State()
