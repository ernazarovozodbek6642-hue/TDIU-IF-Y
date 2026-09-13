import random
from datetime import datetime
import pytz
from html import escape


async def generate_unique_8_digit_event_id(pool):
    """
    Asyncpg pool orqali events jadvalidagi yagona 8 honali event_id generatsiya qiladi.
    """
    while True:
        unique_id = random.randint(10000000, 99999999)
        exists = await pool.fetchval("SELECT 1 FROM events WHERE event_id=$1", unique_id)
        if not exists:
            return int(unique_id)


async def get_current_time(tz_name: str = "Asia/Tashkent") -> str:
    tz = pytz.timezone(tz_name)
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")


async def format_user(u):
    if u['user_name']:
        return escape(f"@{u['user_name']}")
    else:
        return f"<a href=\"tg://user?id={u['user_id']}\">{escape(str(u['full_name']))}</a>"


def get_current_month_year(tz_name: str = "Asia/Tashkent"):
    tz = pytz.timezone(tz_name)
    now = datetime.now(tz)
    return now.month, now.year


def get_prev_month_year(tz_name: str = "Asia/Tashkent"):
    tz = pytz.timezone(tz_name)
    now = datetime.now(tz)
    if now.month == 1:
        return 12, now.year - 1
    return now.month - 1, now.year


async def is_member_of_any_group(bot, db, user_id: int) -> bool:
    """
    Foydalanuvchi ruxsat berilgan guruhlardan kamida bittasida a'zomi tekshiradi.
    Hech qanday guruh sozlanmagan bo‘lsa, oddiy foydalanuvchiga ruxsat berilmaydi.
    """
    groups = await db.get_all_groups()
    if not groups:
        return False

    for g in groups:
        try:
            member = await bot.get_chat_member(g["group_id"], user_id)
            if member.status in ("member", "administrator", "creator") or (
                    member.status == "restricted" and getattr(member, "is_member", False)):
                return True
        except Exception:
            continue
    return False
