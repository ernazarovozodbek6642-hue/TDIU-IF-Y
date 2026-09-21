from aiogram import Dispatcher

from .private_chat import PrivateChatMiddleware
from .throttling import ThrottlingMiddleware


def setup_middlewares(dp: Dispatcher):
    # The bot publishes announcements to configured groups, but never reacts to
    # incoming group messages or exposes interactive keyboards there.
    dp.message.outer_middleware(PrivateChatMiddleware())
    dp.callback_query.outer_middleware(PrivateChatMiddleware())
    # Message and callback traffic need independent windows. Otherwise a valid
    # button tap immediately after a message is incorrectly treated as spam.
    dp.message.middleware(ThrottlingMiddleware())
    dp.callback_query.middleware(ThrottlingMiddleware())
