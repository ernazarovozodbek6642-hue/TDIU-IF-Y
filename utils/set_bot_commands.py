from aiogram import Bot, types


async def set_default_commands(bot: Bot):
    await bot.set_my_commands(
        [
            types.BotCommand(command="start", description="Botni ishga tushurish"),
            types.BotCommand(command="help", description="Yordam"),
            types.BotCommand(command="exit", description="Bosh menyuga qaytish"),
        ]
    )
