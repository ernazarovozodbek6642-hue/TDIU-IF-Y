from aiogram.filters import BaseFilter
from aiogram.types import Message

from loader import db
from utils.access import get_access


class IsResponsible(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        access = await get_access(db, message.from_user.id)
        return access.allows("attendance") or access.allows("upload_media")
