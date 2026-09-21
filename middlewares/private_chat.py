from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message


class PrivateChatMiddleware(BaseMiddleware):
    """Silently ignore incoming messages and button presses outside private chats."""

    async def __call__(self, handler, event, data):
        if isinstance(event, Message):
            if event.chat.type != "private":
                return None
        elif isinstance(event, CallbackQuery):
            if event.message and event.message.chat.type != "private":
                return None
        return await handler(event, data)
