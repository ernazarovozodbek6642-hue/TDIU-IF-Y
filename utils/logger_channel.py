import logging
from html import escape
from datetime import datetime

import pytz

from data import config

TASHKENT_TZ = pytz.timezone("Asia/Tashkent")


async def log_action(bot, actor, action: str):
    """
    Admin/mas'ul shaxs amalini log-kanalga yozadi.
    actor — aiogram User obyekti (yoki None, tizim amali uchun).
    """
    if not config.LOG_CHANNEL_ID:
        return
    t = datetime.now(TASHKENT_TZ).strftime("%d-%m-%Y %H:%M:%S")
    who = f"{escape(actor.full_name)} (<code>{actor.id}</code>)" if actor else "🤖 Tizim"
    text = f"🛡 <b>LOG</b> | {t}\n👤 {who}\n⚙️ {escape(str(action))}"
    try:
        await bot.send_message(config.LOG_CHANNEL_ID, text)
    except Exception:
        logging.exception("Log kanalga yozishda xatolik")
