from html import escape
from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loader import db, bot
from utils.access import get_access
from utils.announcements import send_event_announcement
from utils.logger_channel import log_action

router = Router()


async def publish_event(event_id, actor_id):
    access = await get_access(db, actor_id)
    if not access.allows('approve_event'):
        return None, 0, 0
    event = await db.approve_event_once(event_id, actor_id)
    newly_approved = bool(event)
    if not event:
        event = await db.get_event(event_id)
        if not event or event["approval_status"] != "approved" or event["is_closed"]:
            return None, 0, 0
    sent, failed = await send_event_announcement(bot, db, event)
    if newly_approved:
        from handlers.users.ADMIN.add_event import _notify_assigned
        await _notify_assigned(event)
    return event, sent, failed


async def pending_keyboard(page=0):
    events = await db.execute("SELECT event_id,event_name FROM events WHERE approval_status='pending' AND NOT is_closed ORDER BY date,event_id", fetch=True)
    b = InlineKeyboardBuilder()
    for e in events[page*15:(page+1)*15]:
        b.button(text=str(e['event_name'])[:64], callback_data=f"reviewevent:{e['event_id']}")
    if page:
        b.button(text='◀️ Oldingi', callback_data=f'pendingpage:{page-1}')
    if len(events) > (page+1)*15:
        b.button(text='Keyingi ▶️', callback_data=f'pendingpage:{page+1}')
    b.adjust(1)
    return b.as_markup(), len(events)


@router.message(F.text == '⏳ Tasdiqlash kutilmoqda')
async def pending_list(msg: Message):
    markup, count = await pending_keyboard()
    await msg.answer(f'⏳ Tasdiqlash kutilmoqda: {count} ta tadbir.', reply_markup=markup)


@router.callback_query(F.data.startswith('pendingpage:'))
async def pending_page(call: CallbackQuery):
    markup, count = await pending_keyboard(max(0, int(call.data.split(':')[-1])))
    await call.message.edit_text(f'⏳ Tasdiqlash kutilmoqda: {count} ta tadbir.', reply_markup=markup)
    await call.answer()


@router.callback_query(F.data.startswith('reviewevent:'))
async def review_event(call: CallbackQuery):
    event_id = int(call.data.split(':')[-1])
    event = await db.get_event(event_id)
    if not event or event['approval_status'] != 'pending':
        await call.answer('Tadbir tasdiqlash navbatida yo‘q.', show_alert=True)
        return
    b = InlineKeyboardBuilder()
    b.button(text='✅ Tasdiqlash va e’lon qilish', callback_data=f'approveevent:{event_id}')
    b.button(text='📋 Tafsilotlar', callback_data=f'event:{event_id}')
    b.button(text='◀️ Navbat', callback_data='pendingpage:0')
    b.adjust(1)
    await call.message.edit_text(
        f"⏳ <b>{escape(event['event_name'])}</b>\n{escape(event['description'] or '')}\n"
        f"Sana: {event['date']} | {event['time']}\nBall: {event['score']} | Jarima: {event['penalty_score']}\n"
        f"Ishtirokchi: {event['participants_count']} | Zaxira: {event['waitlist_count']}\n"
        f"Yaratuvchi: {event['created_by']}", reply_markup=b.as_markup())
    await call.answer()


@router.callback_query(F.data.startswith('approveevent:'))
async def approve_event(call: CallbackQuery):
    event_id = int(call.data.split(':')[-1])
    await call.answer()
    event, sent, failed = await publish_event(event_id, call.from_user.id)
    if not event:
        await call.message.answer('Tadbir allaqachon tasdiqlangan yoki ruxsat o‘zgargan.')
        return
    delivery = f" Yuborildi: {sent}, yetkazilmadi: {failed}." if sent or failed else " E'lon avval yuborilgan."
    await call.message.edit_text(f"✅ {escape(event['event_name'])} tasdiqlandi.{delivery}")
    await log_action(bot, call.from_user, f'Tadbir tasdiqlandi: {event_id}')
