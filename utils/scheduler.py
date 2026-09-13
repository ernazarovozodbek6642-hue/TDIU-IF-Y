import asyncio

from utils.access import get_access
import logging
from html import escape
from datetime import datetime

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from data.config import ADMINS
from keyboards.inline.verification_inline import confirmation_request_keyboard
from utils.misc.funcsion import get_prev_month_year
from utils.announcements import send_event_announcement

TASHKENT_TZ = pytz.timezone("Asia/Tashkent")

scheduler = AsyncIOScheduler(timezone=TASHKENT_TZ)
_birthday_job_lock = asyncio.Lock()


async def _check_pending_reminders(bot, db):
    delay_minutes = int(await db.get_setting("reminder_delay_minutes", "20"))
    pending = await db.get_pending_verifications_for_reminder(delay_minutes)

    for row in pending:
        try:
            event_id, user_id = row["event_id"], row["user_id"]
            confirmer_id = row["confirmer_id"]
            proof_photo = row["proof_photo_file_id"]
            target_event = await db.get_event(event_id)
            if not (await get_access(db, confirmer_id)).can_event(target_event, "attendance"):
                continue

            old_message = await db.execute(
                "SELECT request_message_id FROM event_users WHERE event_id=$1 AND user_id=$2",
                event_id, user_id, fetchval=True
            )
            if old_message:
                try:
                    await bot.delete_message(confirmer_id, old_message)
                except Exception:
                    pass

            user = await db.get_user(user_id)
            event = await db.get_event(event_id)
            caption = (
                f"⏰ <b>Eslatma:</b> tasdiqlash hali kutilmoqda!\n\n"
                f"🎉 Tadbir: {escape(str(event['event_name']))}\n"
                f"👤 Talaba: {escape(str(user['full_name']))}\n"
            )
            msg = await bot.send_photo(
                confirmer_id, proof_photo, caption=caption,
                reply_markup=confirmation_request_keyboard(event_id, user_id)
            )
            await db.update_verification_reminder(event_id, user_id, msg.message_id)
        except Exception:
            logging.exception("Eslatma yuborishda xatolik")


async def _remind_missing_media(bot, db):
    required_count = int(await db.get_setting("required_media_count", "3") or 0)
    if required_count <= 0:
        return

    events = await db.get_closed_events_missing_media(required_count)
    for event in events:
        try:
            if not (await get_access(db, event["media_responsible"])).can_event(event, "attendance"):
                continue
            await bot.send_message(
                event["media_responsible"],
                f"📸 <b>Eslatma:</b> '{escape(str(event['event_name']))}' tadbiri yakunlangan.\n"
                f"Siz {event['uploaded_count']}/{required_count} ta rasm yukladingiz.\n\n"
                f"Qolganlarini yuklash uchun <b>/panel</b> buyrug'ini yuboring."
            )
        except Exception:
            logging.exception("Media eslatmasini yuborishda xatolik")


async def _retry_missing_announcements(bot, db):
    for event in await db.get_events_missing_announcements():
        try:
            await send_event_announcement(bot, db, event)
        except Exception:
            logging.exception("Yetkazilmagan tadbir e'lonini qayta yuborishda xatolik")


async def _monthly_winners_job(bot, db):
    """
    Oy boshida adminlarga eslatma yuboradi — g'oliblarni e'lon qilish endi
    faqat admin panel orqali (🏆 Oy talabalari) qo'lda amalga oshiriladi.
    """
    month, year = get_prev_month_year()
    top_n = min(20, int(await db.get_setting("top_n_winners", "5")))

    leaderboard = await db.get_monthly_leaderboard(month, year)
    if not leaderboard:
        return

    preview = "\n".join(
        f"{i}. {escape(str(r['full_name']))} — {r['total_score']} ball" for i, r in enumerate(leaderboard[:top_n], 1)
    )
    text = (
        f"🔔 <b>Eslatma:</b> {month}.{year} oyi yakunlandi.\n"
        f"Oy talabalarini e'lon qilish uchun Admin panel → 🏆 Oy talabalari bo'limiga kiring.\n\n"
        f"TOP-{top_n} nomzodlar:\n{preview}"
    )
    for admin in ADMINS:
        try:
            await bot.send_message(int(admin), text)
        except Exception:
            logging.exception("Adminga oylik eslatma yuborishda xatolik")


def _birthday_message_chunks(users, limit=3800):
    header = "🎉 <b>Bugun tug‘ilgan kun!</b>\n\n"
    footer = "\n🎂 Tug‘ilgan kuningiz muborak bo‘lsin! Sizga sog‘lik, baxt va ulkan zafarlar tilaymiz!"
    chunks = []
    lines, user_ids = [], []
    for user in users:
        line = (
            f"🎈 <a href=\"tg://user?id={int(user['user_id'])}\">"
            f"{escape(str(user['full_name']))}</a>"
        )
        candidate = header + "\n".join(lines + [line]) + footer
        if lines and len(candidate) > limit:
            chunks.append((header + "\n".join(lines) + footer, user_ids))
            lines, user_ids = [], []
        lines.append(line)
        user_ids.append(int(user["user_id"]))
    if lines:
        chunks.append((header + "\n".join(lines) + footer, user_ids))
    return chunks


async def _birthday_job(bot, db, celebration_date=None):
    async with _birthday_job_lock:
        await _birthday_job_locked(bot, db, celebration_date)


async def _birthday_job_locked(bot, db, celebration_date=None):
    today = celebration_date or datetime.now(TASHKENT_TZ).date()
    users = await db.get_birthdays_for_date(today)
    if not users:
        return
    groups = await db.get_all_groups()
    delivered = {
        (row["user_id"], row["group_id"])
        for row in await db.get_birthday_deliveries(today)
    }
    for group in groups:
        pending = [
            user for user in users
            if (user["user_id"], group["group_id"]) not in delivered
        ]
        for text, user_ids in _birthday_message_chunks(pending):
            try:
                message = await bot.send_message(group["group_id"], text)
                await db.record_birthday_deliveries(
                    user_ids, group["group_id"], today, message.message_id
                )
            except Exception:
                logging.exception(
                    "Tug'ilgan kun tabrigini yuborishda xatolik (group_id=%s)",
                    group["group_id"],
                )


def setup_scheduler(bot, db):
    async def maintenance_job():
        """Batch background DB work so a serverless database can sleep between runs."""
        await _check_pending_reminders(bot, db)
        await _retry_missing_announcements(bot, db)
        await _remind_missing_media(bot, db)
        await _birthday_job(bot, db)

    scheduler.add_job(
        maintenance_job,
        CronTrigger(hour="*/2", minute=5, timezone=TASHKENT_TZ),
        id="maintenance_job",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _monthly_winners_job,
        CronTrigger(day=1, hour=0, minute=5, timezone=TASHKENT_TZ),
        args=[bot, db],
        id="monthly_winners_job",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
