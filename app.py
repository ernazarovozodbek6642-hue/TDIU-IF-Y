import asyncio
import logging

from loader import dp, bot, db
from data import config
from handlers import setup_routers
from middlewares import setup_middlewares
from utils.notify_admins import on_startup_notify
from utils.set_bot_commands import set_default_commands
from utils.scheduler import scheduler, setup_scheduler
from utils.reminders import shutdown_reminders


async def on_startup():
    if not config.PHOTO_CHANNEL_ID:
        raise RuntimeError("PHOTO_CHANNEL_ID must be configured")
    await db.create()
    await db.acquire_instance_lock()
    await asyncio.wait_for(db.create_tables(), timeout=20)
    await asyncio.wait_for(db.create_access_tables(), timeout=20)
    # External Telegram calls happen only after local configuration and schema
    # validation have completed successfully.
    await set_default_commands(bot)
    setup_scheduler(bot, db)
    # Bot ishga tushgani haqida adminga xabar berish
    await on_startup_notify(bot)


async def on_shutdown():
    await shutdown_reminders()
    if scheduler.running:
        scheduler.shutdown(wait=False)
    await db.close()


async def main():
    logging.basicConfig(level=logging.INFO)
    setup_middlewares(dp)
    setup_routers(dp)
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    await bot.delete_webhook(drop_pending_updates=False)
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
