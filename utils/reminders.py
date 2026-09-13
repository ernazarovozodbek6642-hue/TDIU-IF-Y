import asyncio
from html import escape
from typing import Dict, Tuple


_reminder_tasks: Dict[Tuple[int, int], asyncio.Task] = {}


def cancel_reminder(event_id: int, user_id: int):
    task = _reminder_tasks.pop((event_id, user_id), None)
    if task and not task.done():
        task.cancel()


def schedule_reminder(bot, db, event_id: int, user_id: int):
    cancel_reminder(event_id, user_id)
    task = asyncio.create_task(_reminder_after_delay(bot, db, event_id, user_id))
    _reminder_tasks[(event_id, user_id)] = task


async def _reminder_after_delay(bot, db, event_id: int, user_id: int):
    key = (event_id, user_id)
    try:
        delay_minutes = int(await db.get_setting("reminder_delay_minutes", "20"))
        await asyncio.sleep(max(1, delay_minutes) * 60)
        row = await db.get_event_user(event_id, user_id)
        if not row or row["status"] != "pending" or not row["confirmer_id"] or not row["proof_photo_file_id"]:
            return

        event = await db.get_event(event_id)
        user = await db.get_user(user_id)
        if not event or event["is_closed"] or not user:
            return

        from utils.access import get_access
        if not (await get_access(db, row["confirmer_id"])).can_event(event, "attendance"):
            return
        from keyboards.inline.verification_inline import confirmation_request_keyboard

        message = await bot.send_photo(
            row["confirmer_id"],
            row["proof_photo_file_id"],
            caption=(
                "⏰ <b>Eslatma:</b> tasdiqlash hali kutilmoqda!\n\n"
                f"🎉 Tadbir: {escape(str(event['event_name']))}\n"
                f"👤 Talaba: {escape(str(user['full_name']))}\n"
            ),
            reply_markup=confirmation_request_keyboard(event_id, user_id),
        )
        await db.update_verification_reminder(event_id, user_id, message.message_id)
    except asyncio.CancelledError:
        raise
    except Exception:
        import logging
        logging.exception("Aniq reminder yuborishda xatolik")
    finally:
        current = asyncio.current_task()
        if _reminder_tasks.get(key) is current:
            _reminder_tasks.pop(key, None)


async def shutdown_reminders():
    tasks = list(_reminder_tasks.values())
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    _reminder_tasks.clear()
