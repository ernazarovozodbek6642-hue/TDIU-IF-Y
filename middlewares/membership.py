from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery

from utils.access import get_access
from utils.misc.funcsion import is_member_of_any_group


class MembershipMiddleware(BaseMiddleware):
    """Only registered faculty-group members may use ordinary bot features."""
    async def __call__(self, handler, event, data):
        from loader import db
        access = await get_access(db, event.from_user.id)
        # Administrators retain access so they can manage the bot from private chat.
        if access.role or await is_member_of_any_group(data["bot"], db, event.from_user.id):
            return await handler(event, data)
        text = (
            "⛔ Siz <b>Fakultet faollari</b> guruhida yo‘qsiz.\n"
            "Botdan foydalanish uchun guruhga a’zo bo‘ling va Bosh koordinatorga murojaat qiling."
        )
        if isinstance(event, CallbackQuery):
            await event.answer(text, show_alert=True)
        else:
            await event.answer(text)
        if data.get("state"):
            await data["state"].clear()
        return None
