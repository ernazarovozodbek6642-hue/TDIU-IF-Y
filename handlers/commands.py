from keyboards.default.ADMIN_Keyboard import admin_menu
from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from filters.is_admin import IsAdmin
from filters.is_responsible import IsResponsible
from keyboards.default.ADMIN_Keyboard import panel_keyboard
from keyboards.default.Users_KEyboard import user_main_menu, user_register
from loader import dp, db

router = Router()


@router.message(Command("admin"), IsAdmin())
async def enter_admin(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("🛠 Admin paneli", reply_markup=await admin_menu(msg.from_user.id))


@router.message(Command("admin"))
async def admin_denied(msg: Message):
    await msg.answer("Sizda admin huquqi yo'q")


@router.message(Command("panel"), IsResponsible())
async def enter_panel(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("📋 Mas'ul shaxs paneli", reply_markup=panel_keyboard)


@router.message(Command("panel"))
async def panel_denied(msg: Message):
    await msg.answer("Siz hech qanday tadbirga mas'ul shaxs sifatida tayinlanmagansiz")


@router.message(Command("exit"))
async def exit_mode(msg: Message, state: FSMContext):
    await state.clear()
    if not await db.get_user(msg.from_user.id):
        await msg.answer("Bosh menyu", reply_markup=user_register)
    else:
        await msg.answer("Bosh menyu", reply_markup=user_main_menu)
