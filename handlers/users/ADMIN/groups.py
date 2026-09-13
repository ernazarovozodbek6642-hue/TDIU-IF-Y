from keyboards.default.ADMIN_Keyboard import admin_menu
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from html import escape

from filters.is_admin import IsAdmin
from keyboards.default.ADMIN_Keyboard import back_menu
from keyboards.inline.groups_inline import groups_list_keyboard
from loader import dp, db, bot
from states.Admin_state import GROUP
from utils.logger_channel import log_action

router = Router()
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


@router.message(F.text == "🏠 Bosh Menyu")
async def groups_home(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer(text="Menyuni tanlang", reply_markup=await admin_menu(msg.from_user.id))


@router.message(F.text == "🏘 Guruhlar")
async def groups_menu(msg: Message, state: FSMContext):
    await state.clear()
    groups = await db.get_all_groups()
    if groups:
        text = "🏘 <b>Ruxsat berilgan guruhlar:</b>\n\n(O'chirish uchun bosing)"
        await msg.answer(text, reply_markup=groups_list_keyboard(groups))
    else:
        await msg.answer("Hozircha hech qanday guruh qo'shilmagan")
    await msg.answer(
        "➕ Yangi guruh qo'shish uchun, botni kerakli guruhga admin qilib qo'shing va shu yerga "
        "guruh ID raqamini yuboring (masalan: <code>-1001234567890</code>)",
        reply_markup=back_menu
    )
    await state.set_state(GROUP.group_id)


@router.message(GROUP.group_id)
async def add_group(msg: Message, state: FSMContext):
    try:
        group_id = int(msg.text)
    except (TypeError, ValueError):
        await msg.answer("Iltimos, faqat guruh ID raqamini yuboring (masalan: -1001234567890)")
        return

    try:
        chat = await bot.get_chat(group_id)
        if chat.type not in {"group", "supergroup"}:
            await msg.answer("Faqat Telegram guruh yoki superguruh ID raqamini kiriting.")
            return
        bot_member = await bot.get_chat_member(group_id, bot.id)
        if bot_member.status not in {"administrator", "creator"}:
            await msg.answer("Bot guruhda administrator bo'lishi kerak.")
            return
        title = chat.title
    except Exception:
        await msg.answer(
            "Bu ID bo'yicha guruhga kira olmadim. Bot shu guruhga admin qilib qo'shilganini tekshiring."
        )
        return

    await db.add_group(group_id, title)
    await msg.answer(f"✅ '{escape(str(title))}' guruhi qo'shildi", reply_markup=await admin_menu(msg.from_user.id))
    await log_action(bot, msg.from_user, f"Guruh qo'shildi: {title} (<code>{group_id}</code>)")
    await state.clear()


@router.callback_query(F.data.startswith("delgroup:"))
async def delete_group(call: CallbackQuery):
    group_id = int(call.data.split(":")[-1])
    await db.remove_group(group_id)
    await log_action(bot, call.from_user, f"Guruh o'chirildi: <code>{group_id}</code>")
    groups = await db.get_all_groups()
    if groups:
        await call.message.edit_text(
            "🏘 <b>Ruxsat berilgan guruhlar:</b>\n\n(O'chirish uchun bosing)",
            reply_markup=groups_list_keyboard(groups)
        )
    else:
        await call.message.edit_text("Hozircha hech qanday guruh qo'shilmagan")
    await call.answer("O'chirildi")


@router.callback_query(F.data == "groups:back")
async def groups_back(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("Menyuni tanlang")
    await call.message.answer("Admin paneli", reply_markup=await admin_menu(call.from_user.id))
    await call.answer()
