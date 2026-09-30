from datetime import timedelta, datetime
import pytz
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from loader import db


async def generate_next_7_days_keyboard():
    """
    Toshkent vaqti bo'yicha bugundan boshlab 7 kunlik sanalarni inline keyboard tugmalari sifatida yaratadi.
    Har bir tugma callback_data: 'date_DD-MM-YYYY' formatida bo'ladi.
    """
    tz = pytz.timezone("Asia/Tashkent")
    today = datetime.now(tz)

    builder = InlineKeyboardBuilder()
    for i in range(7):
        day = today + timedelta(days=i)
        day_str = day.strftime("%d-%m-%Y")
        builder.add(InlineKeyboardButton(text=day_str, callback_data=f"date_{day_str}"))
    builder.add(InlineKeyboardButton(text="◀️ Ortga", callback_data="eventback:description"))
    builder.adjust(2)
    return builder.as_markup()


async def generate_half_hour_keyboard_7_20():
    """
    07:00 dan 20:00 gacha har yarim soatlik vaqtlar uchun inline keyboard yaratadi.
    Tugma text: 'HH:MM', callback_data: 'time_HH:MM'
    """
    builder = InlineKeyboardBuilder()
    for hour in range(7, 21):
        for minute in [0, 30]:
            if hour == 20 and minute == 30:
                continue
            time_str = f"{hour:02d}:{minute:02d}"
            builder.add(InlineKeyboardButton(text=time_str, callback_data=f"time_{time_str}"))
    builder.add(InlineKeyboardButton(text="◀️ Ortga", callback_data="eventback:date"))
    builder.adjust(3)
    return builder.as_markup()


confirmation_event = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="Tasdiqlash", callback_data="con:confirm"),
            InlineKeyboardButton(text="Qayta yaratish", callback_data="con:again")
        ],
        [InlineKeyboardButton(text="◀️ Ortga", callback_data="con:back")]
    ]
)


def user_pick_keyboard(users, prefix: str):
    builder = InlineKeyboardBuilder()
    for u in users:
        builder.add(InlineKeyboardButton(text=str(u["full_name"])[:64], callback_data=f"{prefix}:{u['user_id']}"))
    builder.add(InlineKeyboardButton(text="◀️ Ortga", callback_data=f"pickback:{prefix}"))
    builder.adjust(1)
    return builder.as_markup()


def media_needed_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ Ha, media mas’ul kerak", callback_data="media_needed:yes"))
    builder.add(InlineKeyboardButton(text="❌ Yo‘q, kerak emas", callback_data="media_needed:no"))
    builder.add(InlineKeyboardButton(text="◀️ Ortga", callback_data="eventback:responsible"))
    builder.adjust(1)
    return builder.as_markup()


def verification_method_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✋ Qo'lda (Manual)", callback_data="vmethod:manual"))
    builder.add(InlineKeyboardButton(text="📸 2-bosqichli (tugma+rasm)", callback_data="vmethod:photo"))
    builder.add(InlineKeyboardButton(text="◀️ Ortga", callback_data="eventback:score"))
    builder.adjust(1)
    return builder.as_markup()


async def generate_month_buttons(user_id):
    """
    Bazadagi mavjud oylar bo'yicha InlineKeyboardMarkup yaratadi.
    """
    sql = """
    SELECT DISTINCT EXTRACT(MONTH FROM date) AS month, EXTRACT(YEAR FROM date) AS year
    FROM events
    ORDER BY year DESC, month DESC;
    """
    from utils.access import get_access
    access = await get_access(db, user_id)
    months = await db.execute(sql, fetch=True)

    builder = InlineKeyboardBuilder()
    for m in months:
        month_int = int(m['month'])
        year_int = int(m['year'])
        builder.add(
            InlineKeyboardButton(
                text=f"{month_int}.{year_int}",
                callback_data=f"month_{month_int}.{year_int}"
            )
        )
    builder.adjust(1)
    return builder.as_markup()


async def generate_event_by_month(date, user_id):
    builder = InlineKeyboardBuilder()
    events = await db.get_events_by_month(int(date.split('.')[0]), int(date.split('.')[1]))
    from utils.access import get_access
    access = await get_access(db, user_id)
    events = [e for e in events if access.in_scope(e, own_event=access.role == "assistant")]
    for i in events:
        closed_mark = "🔒 " if i['is_closed'] else ("⏳ " if i["approval_status"] == "pending" else "")
        builder.add(
            InlineKeyboardButton(text=f"{closed_mark}{i['event_name']}"[:64], callback_data=f"event:{i['event_id']}"))
    builder.add(InlineKeyboardButton(text="◀️ Ortga", callback_data="backmonths"))
    builder.adjust(1)
    return builder.as_markup()


def event_actions_keyboard(event_id: int, is_closed: bool, show_media_upload: bool = False,
                            back_callback: str = "backmonths", show_edit: bool = False):
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ Qatnashuvni belgilash", callback_data=f"evattend:{event_id}"))
    builder.add(InlineKeyboardButton(text="🖼 Rasmlar", callback_data=f"eventmedia:{event_id}"))
    if show_media_upload:
        builder.add(InlineKeyboardButton(text="📸 Rasm yuklash", callback_data=f"uploadmedia:{event_id}"))
    if show_edit and not is_closed:
        builder.add(InlineKeyboardButton(text="✏️ Tahrirlash", callback_data=f"editevent:{event_id}"))
    if not is_closed:
        builder.add(InlineKeyboardButton(text="🔒 Tadbirni yakunlash", callback_data=f"evclose:{event_id}"))
    builder.add(InlineKeyboardButton(text="◀️ Ortga", callback_data=back_callback))
    builder.adjust(1)
    return builder.as_markup()


def manual_attendance_keyboard(event_id: int, users, page: int = 0,
                               total: int = None, query: str = None):
    builder = InlineKeyboardBuilder()
    for u in users:
        mark = "✅" if u["status"] == "confirmed" else ("🚫" if u["status"] in ("not_attended", "rejected") else "⬜")
        username = f"@{u['user_name']} | " if u.get("user_name") else ""
        group = f" — {u['group_name']}" if u.get("group_name") else ""
        builder.add(InlineKeyboardButton(
            text=f"{mark} {username}{u['full_name']}{group}"[:64],
            callback_data=f"toggleattend:{event_id}:{u['user_id']}:{page}"
        ))
    total = len(users) if total is None else total
    pages = max(1, (total + 14) // 15)
    if page > 0:
        builder.add(InlineKeyboardButton(text="◀️ Oldingi", callback_data=f"attpage:{event_id}:{page - 1}"))
    builder.add(InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data="attnoop"))
    if page + 1 < pages:
        builder.add(InlineKeyboardButton(text="Keyingi ▶️", callback_data=f"attpage:{event_id}:{page + 1}"))
    builder.add(InlineKeyboardButton(text="🔎 Izlash", callback_data=f"attsearch:{event_id}"))
    if query:
        builder.add(InlineKeyboardButton(text="📋 Barchasi", callback_data=f"attall:{event_id}"))
    builder.add(InlineKeyboardButton(text="◀️ Ortga", callback_data=f"event:{event_id}"))
    builder.adjust(*([1] * len(users)), 3, 2)
    return builder.as_markup()

async def permitted_event_keyboard(event, user_id, back_callback='backmonths'):
    from utils.access import get_access
    access = await get_access(db, user_id)
    event_id = event['event_id']
    active = not event['is_closed'] and event['approval_status'] == 'approved'
    b = InlineKeyboardBuilder()
    if active and access.can_event(event, 'attendance'):
        b.button(text='✅ Qatnashuvni belgilash', callback_data=f'evattend:{event_id}')
    if (event['approval_status'] == 'approved' and event['media_responsible'] == user_id
            and access.can_event(event, 'upload_media')):
        b.button(text='📸 Rasm yuklash', callback_data=f'uploadmedia:{event_id}')
    if access.can_event(event, 'reports'):
        b.button(text='🖼 Rasmlar', callback_data=f'eventmedia:{event_id}')
        if access.role == 'assistant':
            b.button(text='📊 Excel hisobot', callback_data=f'eventexcel:{event_id}')
    if not event['is_closed'] and access.can_event(event, 'edit_event') and (event['approval_status'] == 'pending' or access.allows('approve_event')):
        b.button(text='✏️ Tahrirlash', callback_data=f'editevent:{event_id}')
    if active and access.can_event(event, 'close_event'):
        b.button(text='🔒 Tadbirni yakunlash', callback_data=f'evclose:{event_id}')
    if event['approval_status'] == 'pending' and access.allows('approve_event'):
        b.button(text='✅ Tasdiqlash va e’lon qilish', callback_data=f'approveevent:{event_id}')
    b.button(text='◀️ Ortga', callback_data=back_callback)
    b.adjust(1)
    return b.as_markup()
