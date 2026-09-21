from aiogram import Bot, types
from aiogram.types import (
    BotCommandScopeAllChatAdministrators,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
)


async def set_default_commands(bot: Bot):
    commands = [
        types.BotCommand(command="start", description="Botni ishga tushurish"),
        types.BotCommand(command="help", description="Yordam"),
        types.BotCommand(command="exit", description="Bosh menyuga qaytish"),
    ]
    # Remove legacy global/group scopes so Telegram does not show the command
    # menu in groups. Commands are intentionally available only in private chat.
    await bot.delete_my_commands()
    await bot.delete_my_commands(scope=BotCommandScopeAllGroupChats())
    await bot.delete_my_commands(scope=BotCommandScopeAllChatAdministrators())
    await bot.set_my_commands(
        commands,
        scope=BotCommandScopeAllPrivateChats(),
    )
