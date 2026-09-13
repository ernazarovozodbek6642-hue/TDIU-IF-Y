import logging

from aiogram import Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import ErrorEvent

router = Router()


@router.errors()
async def errors_handler(event: ErrorEvent):
    exc = event.exception

    if isinstance(exc, TelegramBadRequest):
        logging.error("TelegramBadRequest: %s", exc)
        return True

    if isinstance(exc, TelegramAPIError):
        logging.error("TelegramAPIError: %s", exc)
        return True

    logging.error(
        "Unhandled update error (update_id=%s): %s",
        getattr(event.update, "update_id", None), exc,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    try:
        if event.update.callback_query:
            await event.update.callback_query.answer("Xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.", show_alert=True)
        elif event.update.message:
            await event.update.message.answer("Xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.")
    except TelegramAPIError:
        pass
    return True
