import time
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message


class ThrottlingMiddleware(BaseMiddleware):
    """
    Foydalanuvchi juda tez-tez xabar yuborsa, spamni cheklaydi.
    """

    def __init__(self, limit: float = 0.5):
        self.limit = limit
        self._last_call: Dict[int, float] = {}
        super().__init__()

    async def __call__(
            self,
            handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
            event: Message,
            data: Dict[str, Any],
    ) -> Any:
        user_id = event.from_user.id if event.from_user else None
        if user_id is not None:
            now = time.monotonic()
            # Prevent the per-user cache from growing forever in a long-running bot.
            if len(self._last_call) > 10000:
                cutoff = now - self.limit * 2
                self._last_call = {uid: ts for uid, ts in self._last_call.items() if ts >= cutoff}
            last = self._last_call.get(user_id, 0)
            if now - last < self.limit:
                if isinstance(event, CallbackQuery):
                    await event.answer("Iltimos, biroz kutib turing", show_alert=False)
                else:
                    await event.reply("Iltimos, biroz kutib turing (juda tez-tez yuboryapsiz)!")
                return
            self._last_call[user_id] = now
        return await handler(event, data)
