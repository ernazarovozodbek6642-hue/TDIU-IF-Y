from aiogram.filters import BaseFilter
from aiogram.types import Message

from utils.access import get_access


class IsAdmin(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        from loader import db
        return (await get_access(db, message.from_user.id)).role in {"super", "chief", "assistant"}
