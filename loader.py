from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import SimpleEventIsolation

from data import config
from utils.db_api.SQL import Database
from utils.fsm_storage import PostgresStorage

bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
db = Database()
storage = PostgresStorage(db)
dp = Dispatcher(storage=storage, events_isolation=SimpleEventIsolation())
