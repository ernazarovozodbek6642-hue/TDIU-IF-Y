import logging
import asyncio
from html import escape


async def _bot_username(bot):
    me = await bot.get_me()
    return me.username


async def build_announcement_text(db, event, bot_username, edit_note=None):
    main_list, waitlist = await db.get_event_participants(event["event_id"])

    lines = [
        "#tadbir",
        f"🎉 <b>{escape(str(event['event_name']))}</b>",
        f"📝 {escape(str(event['description'] or ''))}",
        f"🗓 Sana: {event['date']} | ⏰ {event['time']}",
        f"👥 Kerakli odam soni: {event['participants_count']}",
        f"🔁 Zaxira: {event['waitlist_count']}",
        f"⭐ Ball: {event['score']}",
        _location_line(event.get("location")),
        f"🔗 <a href=\"https://t.me/{escape(str(bot_username))}?start=event_{event['event_id']}\">Ro'yxatdan o'tish</a>",
    ]
    if edit_note:
        # Edit notes can contain an old and a new long description. Keep enough
        # context for administrators without risking Telegram's message limit.
        lines.append(f"\n✏️ <b>Tahrirlandi:</b>\n{escape(str(edit_note)[:500])}")
    lines.extend(["———", "✅ <b>Ro'yxatdan o'tganlar:</b>"])
    if main_list:
        _append_people_with_limit(lines, main_list)
    else:
        lines.append("— hali hech kim yo'q")

    if waitlist:
        lines.append("\n🔁 <b>Zaxira:</b>")
        _append_people_with_limit(lines, waitlist)

    return "\n".join(filter(None, lines))


def _location_line(location):
    value = str(location or "")
    if value.startswith("geo:"):
        try:
            longitude, latitude = value[4:].split(".:", 1)
            return f'📍 <a href="https://maps.google.com/?q={escape(latitude)},{escape(longitude)}">Xaritada ochish</a>'
        except ValueError:
            return ""
    if value.startswith("text:"):
        value = value[5:]
    return f"📍 Manzil: {escape(value)}" if value else ""


def _append_people_with_limit(lines, people, limit=3800):
    added = 0
    for index, person in enumerate(people, 1):
        candidate = f"{index}. {escape(str(person['full_name']))}"
        if len("\n".join(lines + [candidate])) > limit:
            break
        lines.append(candidate)
        added += 1
    if added < len(people):
        lines.append(f"… yana {len(people) - added} kishi")


async def send_event_announcement(bot, db, event):
    if event["approval_status"] != "approved":
        return 0, 0
    groups = await db.get_all_groups()
    if not groups:
        return 0, 0
    bot_username = await _bot_username(bot)
    text = await build_announcement_text(db, event, bot_username)
    existing = {m["group_id"] for m in await db.get_announcement_messages(
        event["event_id"], kind="announcement"
    )}
    sent, failed = 0, 0

    for g in groups:
        if g["group_id"] in existing:
            continue
        for attempt in range(3):
            try:
                msg = await bot.send_message(g["group_id"], text, disable_web_page_preview=True)
                await db.add_announcement_message(event["event_id"], g["group_id"], msg.message_id, kind="announcement")
                sent += 1
                try:
                    await bot.pin_chat_message(g["group_id"], msg.message_id, disable_notification=True)
                except Exception:
                    pass
                break
            except Exception:
                if attempt == 2:
                    failed += 1
                    logging.exception("E'lon xabarini yuborishda xatolik")
                else:
                    await asyncio.sleep(1)
    return sent, failed


async def update_event_announcement(bot, db, event_id, edit_note=None):
    event = await db.get_event(event_id)
    if not event or event["is_closed"] or event["approval_status"] != "approved":
        return
    bot_username = await _bot_username(bot)
    text = await build_announcement_text(db, event, bot_username, edit_note=edit_note)
    messages = await db.get_announcement_messages(event_id, kind="announcement")

    for m in messages:
        try:
            await bot.edit_message_text(
                text, chat_id=m["group_id"], message_id=m["message_id"], disable_web_page_preview=True
            )
        except Exception:
            logging.exception(
                "Tadbir e'lonini tahrirlashda xatolik (event_id=%s, group_id=%s)",
                event_id, m["group_id"],
            )


async def build_result_text(db, event):
    info = await db.get_event_full_info(event["event_id"])
    attended = info["attended"]
    not_attended = info["not_attended"]

    lines = [
        "#tadbir_natija",
        f"🎉 <b>{escape(str(event['event_name']))}</b>",
        f"📝 {escape(str(event['description'] or ''))}",
        f"🗓 Sana: {event['date']} | ⏰ {event['time']}",
        f"⭐ Ball: {event['score']}",
        "———",
        "✅ <b>Kelganlar:</b>",
    ]
    if attended:
        _append_people_with_limit(lines, attended)
    else:
        lines.append("— hech kim yo'q")

    lines.append("\n🚫 <b>Kelmaganlar:</b>")
    if not_attended:
        _append_people_with_limit(lines, not_attended)
    else:
        lines.append("— hech kim yo'q")

    return "\n".join(lines)


async def send_event_result(bot, db, event):
    groups = await db.get_all_groups()
    if not groups:
        return
    text = await build_result_text(db, event)

    for g in groups:
        try:
            msg = await bot.send_message(g["group_id"], text)
            await db.add_announcement_message(event["event_id"], g["group_id"], msg.message_id, kind="result")
            try:
                await bot.pin_chat_message(g["group_id"], msg.message_id, disable_notification=True)
            except Exception:
                pass
        except Exception:
            logging.exception("Natija xabarini yuborishda xatolik")
