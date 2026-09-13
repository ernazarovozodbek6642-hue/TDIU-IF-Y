from aiogram import Dispatcher

from .throttling import ThrottlingMiddleware


def setup_middlewares(dp: Dispatcher):
    # Message and callback traffic need independent windows. Otherwise a valid
    # button tap immediately after a message is incorrectly treated as spam.
    dp.message.middleware(ThrottlingMiddleware())
    dp.callback_query.middleware(ThrottlingMiddleware())
