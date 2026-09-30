from aiogram.utils.keyboard import InlineKeyboardBuilder
from utils.access import get_access
from keyboards.default.ADMIN_Keyboard import admin_menu
from datetime import time, datetime
from html import escape

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from filters.is_admin import IsAdmin
from keyboards.default.ADMIN_Keyboard import location, back_menu
from keyboards.default.Users_KEyboard import user_main_menu
from keyboards.inline.Admin_keyboard_in import (
    generate_next_7_days_keyboard, generate_half_hour_keyboard_7_20,
    confirmation_event, verification_method_keyboard, user_pick_keyboard,
    media_needed_keyboard,
)
from loader import dp, db, bot
from states.Admin_state import EVENT
from utils.logger_channel import log_action
from utils.misc.funcsion import generate_unique_8_digit_event_id, normalize_event_location

router = Router()
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


@router.message(F.text == "🔚 Chiqish")
async def admin_exit(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer(text='Bosh menyu', reply_markup=user_main_menu)


@router.message(F.text == "🏠 Bosh Menyu")
async def admin_home(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer(text='Menyuni tanlang', reply_markup=await admin_menu(msg.from_user.id))


@router.message(F.text == "➕Tadbir yatatish")
async def add_event_(msg: Message, state: FSMContext):
    await state.clear()
    await state.update_data(direction_id=None)
    await msg.answer("Tadbir nomini kiriting", reply_markup=back_menu)
    await state.set_state(EVENT.name_event)


@router.callback_query(EVENT.direction, F.data.startswith("eventdir:"))
async def choose_event_direction(call: CallbackQuery, state: FSMContext):
    direction_id = int(call.data.split(":")[-1])
    access = await get_access(db, call.from_user.id)
    if (False and direction_id != access.direction_id) or direction_id not in {d["direction_id"] for d in await db.get_directions()}:
        await call.answer("Yo‘nalish uchun ruxsat yo‘q", show_alert=True)
        return
    await state.update_data(direction_id=direction_id)
    await state.set_state(EVENT.name_event)
    await call.message.answer("Tadbir nomini kiriting", reply_markup=back_menu)
    await call.answer()


@router.message(EVENT.name_event)
async def description(msg: Message, state: FSMContext):
    if not msg.text or not msg.text.strip() or len(msg.text.strip()) > 255:
        await msg.answer("Tadbir nomi bo'sh bo'lmasligi va 255 belgidan oshmasligi kerak")
        return
    await state.update_data(event_name=msg.text.strip())
    await msg.answer(text="Ta'rifni kiriting", reply_markup=back_menu)
    await state.set_state(EVENT.description)


@router.message(EVENT.description)
async def event_date(msg: Message, state: FSMContext):
    if not msg.text or not msg.text.strip() or len(msg.text.strip()) > 2000:
        await msg.answer("Tavsif bo'sh bo'lmasligi va 2000 belgidan oshmasligi kerak")
        return
    await state.update_data(description=msg.text.strip())
    await msg.answer(text="Sanani tanlang", reply_markup=await generate_next_7_days_keyboard())
    await state.set_state(EVENT.date)


@router.callback_query(EVENT.date, F.data.startswith("date_"))
async def event_date_cb(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.update_data(date=call.data.split('_')[1])
    await call.message.delete()
    await call.message.answer(text="Endi esa soatni tanlang", reply_markup=await generate_half_hour_keyboard_7_20())
    await state.set_state(EVENT.time)


@router.callback_query(EVENT.date, F.data == "eventback:description")
async def event_date_back(call: CallbackQuery, state: FSMContext):
    await call.message.delete()
    await call.message.answer("Tadbir ta'rifini kiriting", reply_markup=back_menu)
    await state.set_state(EVENT.description)
    await call.answer()


@router.callback_query(EVENT.time, F.data.startswith("time_"))
async def event_time_cb(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.update_data(time=str(call.data.split('_')[1]))
    await call.message.delete()
    await call.message.answer(text="Tadbir balini kiriting", reply_markup=back_menu)
    await state.set_state(EVENT.score)


@router.callback_query(EVENT.time, F.data == "eventback:date")
async def event_time_back(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("Sanani tanlang", reply_markup=await generate_next_7_days_keyboard())
    await state.set_state(EVENT.date)
    await call.answer()


@router.message(EVENT.score)
async def event_score(msg: Message, state: FSMContext):
    if not msg.text or not msg.text.isdigit() or int(msg.text) > 100000:
        await msg.answer("Iltimos, faqat son kiriting")
        return
    await state.update_data(score=int(msg.text))
    await msg.answer(text="Qatnashuvni tasdiqlash usulini tanlang", reply_markup=verification_method_keyboard())
    await state.set_state(EVENT.verification_method)


@router.callback_query(EVENT.verification_method, F.data.startswith("vmethod:"))
async def event_verification_method(call: CallbackQuery, state: FSMContext):
    method = call.data.split(":")[-1]
    if method not in {"manual", "photo"}:
        await call.answer("Noto'g'ri tasdiqlash usuli", show_alert=True)
        return
    await call.answer()
    await state.update_data(verification_method=method)
    await call.message.delete()
    await call.message.answer(
        text="Tadbirga ro'yxatdan o'tib, kelmagan talabalarga beriladigan jarima balini kiriting\n"
             "(Jarima kerak bo'lmasa <b>0</b> kiriting)",
        reply_markup=back_menu
    )
    await state.set_state(EVENT.penalty_score)


@router.callback_query(EVENT.verification_method, F.data == "eventback:score")
async def event_verification_back(call: CallbackQuery, state: FSMContext):
    await call.message.delete()
    await call.message.answer("Tadbir balini kiriting", reply_markup=back_menu)
    await state.set_state(EVENT.score)
    await call.answer()


@router.message(EVENT.penalty_score)
async def event_penalty_score(msg: Message, state: FSMContext):
    if not msg.text or not msg.text.isdigit() or int(msg.text) > 100000:
        await msg.answer("Iltimos, faqat son kiriting")
        return
    await state.update_data(penalty_score=int(msg.text))
    await msg.answer(text="Tadbir qatnashchilar soni", reply_markup=back_menu)
    await state.set_state(EVENT.participants_count)


@router.message(EVENT.participants_count)
async def participants_count(msg: Message, state: FSMContext):
    if not msg.text or not msg.text.isdigit() or int(msg.text) < 1 or int(msg.text) > 100000:
        await msg.answer("Iltimos, faqat son kiriting")
        return
    await state.update_data(participants_count=int(msg.text))
    await msg.answer(
        text="Zaxira ro'yxati uchun necha kishilik joy bo'lsin?\n(Kerak bo'lmasa <b>0</b> kiriting)",
        reply_markup=back_menu
    )
    await state.set_state(EVENT.waitlist_count)


@router.message(EVENT.waitlist_count)
async def waitlist_count(msg: Message, state: FSMContext):
    if not msg.text or not msg.text.isdigit() or int(msg.text) > 100000:
        await msg.answer("Iltimos, faqat son kiriting")
        return
    await state.update_data(waitlist_count=int(msg.text))
    await msg.answer(
        text="Tadbir joylashuvini yuboring: 📍 geolokatsiya, oddiy manzil matni yoki https:// havola",
        reply_markup=location
    )
    await state.set_state(EVENT.location)


@router.message(EVENT.location, F.location)
async def event_location(msg: Message, state: FSMContext):
    await state.update_data(location=f"geo:{msg.location.longitude}.:{msg.location.latitude}")
    await msg.answer(
        text="Ma'sul shaxsni qidirish uchun F.I.Sh (yoki uning bir qismi)ni yozing",
        reply_markup=back_menu
    )
    await state.set_state(EVENT.responsible_person)


@router.message(EVENT.location, F.text)
async def event_location_text(msg: Message, state: FSMContext):
    value = (msg.text or "").strip()
    if not value or len(value) > 250:
        await msg.answer("Manzil bo'sh bo'lmasligi va 250 belgidan oshmasligi kerak")
        return
    await state.update_data(location=normalize_event_location(value))
    await msg.answer(
        text="Ma'sul shaxsni qidirish uchun F.I.Sh (yoki uning bir qismi)ni yozing",
        reply_markup=back_menu
    )
    await state.set_state(EVENT.responsible_person)


@router.message(EVENT.responsible_person)
async def responsible_person_search(msg: Message, state: FSMContext):
    if not msg.text or not msg.text.strip():
        await msg.answer("Qidirish uchun ism kiriting")
        return
    users = await db.search_users(msg.text)
    if not users:
        await msg.answer("Hech kim topilmadi. Boshqa nom bilan qidirib ko'ring")
        return
    await msg.answer("Topilgan natijalardan birini tanlang:", reply_markup=user_pick_keyboard(users, "pickresp"))


@router.callback_query(EVENT.responsible_person, F.data.startswith("pickresp:"))
async def responsible_person_pick(call: CallbackQuery, state: FSMContext):
    await call.answer()
    user_id = int(call.data.split(":")[-1])
    user = await db.get_user(user_id)
    if not user:
        await call.message.answer("Bu talaba topilmadi yoki hali tasdiqlanmagan. Qayta qidiring.")
        return
    await state.update_data(responsible_user_id=user_id, responsible_person_name=user["full_name"])
    await call.message.delete()

    await call.message.answer("🎥 Bu tadbir uchun media mas’ul kerakmi?", reply_markup=media_needed_keyboard())
    await state.set_state(EVENT.media_choice)


@router.callback_query(EVENT.responsible_person, F.data == "pickback:pickresp")
async def responsible_person_back(call: CallbackQuery, state: FSMContext):
    await call.message.delete()
    await call.message.answer(
        "Tadbir joylashuvini yuboring yoki manzilni matn sifatida yozing", reply_markup=location
    )
    await state.set_state(EVENT.location)
    await call.answer()


@router.callback_query(EVENT.media_choice, F.data == "media_needed:yes")
async def media_needed_yes(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data.get("verification_method") == "photo":
        await call.message.edit_text("Tasdiqlovchi rasmni ko‘radigan media mas’ulni qidirish uchun F.I.Sh yozing:")
    else:
        await call.message.edit_text("Media mas’ulni qidirish uchun F.I.Sh (yoki uning bir qismi)ni yozing:")
    await state.set_state(EVENT.media_responsible)
    await call.answer()


@router.callback_query(EVENT.media_choice, F.data == "media_needed:no")
async def media_needed_no(call: CallbackQuery, state: FSMContext):
    await state.update_data(media_responsible_id=None, media_responsible_name=None)
    await call.message.delete()
    await _show_confirmation(call.message, state)
    await call.answer()


@router.callback_query(EVENT.media_choice, F.data == "eventback:responsible")
async def media_choice_back(call: CallbackQuery, state: FSMContext):
    await call.message.delete()
    await call.message.answer("Mas'ul shaxsni qidirish uchun F.I.Sh yozing", reply_markup=back_menu)
    await state.set_state(EVENT.responsible_person)
    await call.answer()


@router.message(EVENT.media_responsible)
async def media_responsible_search(msg: Message, state: FSMContext):
    if not msg.text or not msg.text.strip():
        await msg.answer("Qidirish uchun ism kiriting")
        return
    users = await db.search_users(msg.text)
    if not users:
        await msg.answer("Hech kim topilmadi. Boshqa nom bilan qidirib ko'ring")
        return
    await msg.answer("Topilgan natijalardan birini tanlang:", reply_markup=user_pick_keyboard(users, "pickmedia"))


@router.callback_query(EVENT.media_responsible, F.data.startswith("pickmedia:"))
async def media_responsible_pick(call: CallbackQuery, state: FSMContext):
    await call.answer()
    user_id = int(call.data.split(":")[-1])
    user = await db.get_user(user_id)
    if not user:
        await call.message.answer("Bu talaba topilmadi yoki hali tasdiqlanmagan. Qayta qidiring.")
        return
    await state.update_data(media_responsible_id=user_id, media_responsible_name=user["full_name"])
    await call.message.delete()
    await _show_confirmation(call.message, state)


@router.callback_query(EVENT.media_responsible, F.data == "pickback:pickmedia")
async def media_responsible_back(call: CallbackQuery, state: FSMContext):
    await call.message.delete()
    await call.message.answer(
        "Ma'sul shaxsni qidirish uchun F.I.Sh (yoki uning bir qismi)ni yozing", reply_markup=back_menu
    )
    await state.set_state(EVENT.responsible_person)
    await call.answer()


async def _show_confirmation(msg: Message, state: FSMContext):
    event_info = await state.get_data()
    method_labels = {"manual": "Qo'lda (Manual)", "photo": "2-bosqichli (tugma+rasm)"}
    text = (
        f"🎉 <b>Tadbir nomi:</b> {escape(str(event_info.get('event_name') or ''))}\n"
        f"📝 <b>Tadbir izohi:</b> {escape(str(event_info.get('description') or ''))}\n"
        f"📅 <b>Tadbir sanasi:</b> {event_info.get('date')}\n"
        f"⏰ <b>Tadbir vaqti:</b> {event_info.get('time')}\n"
        f"⭐ <b>Tadbir bahosi:</b> {event_info.get('score')}\n"
        f"🚫 <b>Jarima bali:</b> {event_info.get('penalty_score')}\n"
        f"🔎 <b>Tasdiqlash usuli:</b> {method_labels.get(event_info.get('verification_method'))}\n"
        f"👥 <b>Qatnashchilar soni:</b> {event_info.get('participants_count')}\n"
        f"🔁 <b>Zaxira:</b> {event_info.get('waitlist_count')}\n"
        f"👤 <b>Mas'ul shaxs:</b> {escape(str(event_info.get('responsible_person_name') or ''))}\n"
    )
    if event_info.get("media_responsible_name"):
        text += f"🎥 <b>Media mas'ul:</b> {escape(str(event_info.get('media_responsible_name')))}\n"

    event_location = event_info.get("location", "")
    if event_location.startswith("geo:"):
        coords = event_location[len("geo:"):]
        location_msg = await msg.answer_location(
            longitude=float(coords.split(".:")[0]),
            latitude=float(coords.split(".:")[1])
        )
        await location_msg.reply(text=text, reply_markup=confirmation_event)
    elif event_location.startswith("link:"):
        link = event_location[len("link:"):]
        text += f'📍 <b>Manzil:</b> <a href="{escape(link)}">Manzilni ochish</a>\n'
        await msg.answer(text=text, reply_markup=confirmation_event, disable_web_page_preview=True)
    else:
        address = event_location[len("text:"):] if event_location.startswith("text:") else event_location
        text += f"📍 <b>Manzil:</b> {escape(address)}\n"
        await msg.answer(text=text, reply_markup=confirmation_event)
    await state.set_state(EVENT.confirmation)


async def _notify_assigned(event):
    text = (
        f"📋 Siz <b>{escape(str(event['event_name']))}</b> tadbiriga mas'ul shaxs qilib tayinlandingiz.\n"
        f"🗓 Sana: {event['date']} | ⏰ {event['time']}\n\n"
        f"Batafsil ma'lumot va boshqarish uchun <b>/panel</b> buyrug'ini yuboring."
    )
    try:
        await bot.send_message(event["responsible_person"], text)
    except Exception:
        pass

    if event["media_responsible"] and event["media_responsible"] != event["responsible_person"]:
        media_text = (
            f"🎥 Siz <b>{escape(str(event['event_name']))}</b> tadbiriga media mas'ul shaxs qilib tayinlandingiz.\n"
            f"🗓 Sana: {event['date']} | ⏰ {event['time']}\n\n"
            f"Tadbir rasmlarini yuklash uchun <b>/panel</b> buyrug'ini yuboring. "
            f"Davomatni tasdiqlash tadbir mas’uli tomonidan amalga oshiriladi."
        )
        try:
            await bot.send_message(event["media_responsible"], media_text)
        except Exception:
            pass


@router.callback_query(EVENT.confirmation, F.data.startswith("con:"))
async def confirmation(call: CallbackQuery, state: FSMContext):
    action = call.data.split(':')[-1]
    if action == "back":
        data = await state.get_data()
        await call.message.delete()
        if data.get("verification_method") == "photo":
            await call.message.answer(
                "Tasdiqlovchi rasmlarni ko'radigan media mas'ulni qidiring", reply_markup=back_menu
            )
            await state.set_state(EVENT.media_responsible)
        else:
            await call.message.answer(
                "Mas'ul shaxsni qidirish uchun F.I.Sh yozing", reply_markup=back_menu
            )
            await state.set_state(EVENT.responsible_person)
        await call.answer()
        return
    if action == 'confirm':
        event_info = await state.get_data()
        access = await get_access(db, call.from_user.id)
        direction_id = event_info.get("direction_id")
        required = {"event_name", "description", "date", "time", "score", "participants_count", "location", "responsible_user_id"}
        if not required.issubset(event_info):
            await call.answer("Ma’lumot yoki yo‘nalish o‘zgargan. Tadbirni qaytadan yarating.", show_alert=True)
            await state.clear()
            return
        # Always save a draft before publication, even for the owner.
        event_time_parts = event_info.get('time').split(':')
        event_id = await generate_unique_8_digit_event_id(db.pool)
        await db.add_event(
            event_id=event_id,
            event_name=str(event_info.get('event_name')),
            description=str(event_info.get('description')),
            date_=datetime.strptime(event_info.get('date'), "%d-%m-%Y").date(),
            time_=time(hour=int(event_time_parts[0]), minute=int(event_time_parts[1])),
            score=int(event_info.get('score')),
            participants_count=int(event_info.get('participants_count')),
            waitlist_count=int(event_info.get('waitlist_count', 0)),
            location=str(event_info.get('location')),
            responsible_person=int(event_info.get('responsible_user_id')),
            media_responsible=event_info.get('media_responsible_id'),
            verification_method=event_info.get('verification_method', 'manual'),
            penalty_score=int(event_info.get('penalty_score', 0)),
            direction_id=direction_id, created_by=call.from_user.id, approval_status="pending",
        )
        event = await db.get_event(event_id)
        if access.allows("approve_event"):
            from handlers.users.ADMIN.approvals import publish_event
            published, sent, failed = await publish_event(event_id, call.from_user.id)
            message = (
                f"✅ Tadbir tasdiqlandi. E'lon yuborildi: {sent}, yetkazilmadi: {failed}."
                if published else "✅ Tadbir tasdiqlash navbatida saqlandi."
            )
        else:
            message = "✅ Tadbir saqlandi va tasdiqlash navbatiga qo‘shildi. Tasdiqlangach e’lon qilinadi."
        await call.message.answer(message, reply_markup=await admin_menu(call.from_user.id))
        await log_action(bot, call.from_user,
                          f"Tadbir yaratildi: <b>{event['event_name']}</b> (ID: {event_id})")
        await state.clear()
    elif action == 'again':
        await call.message.delete()
        await call.message.answer(text='Menyuni tanlang', reply_markup=await admin_menu(call.from_user.id))
        await state.clear()



