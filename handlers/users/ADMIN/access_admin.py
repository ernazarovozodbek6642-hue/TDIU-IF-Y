from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from data.config import SUPER_ADMIN_ID
from loader import db
from utils.access import PERMISSIONS, ROLE_LABELS, ROLE_PERMISSIONS, get_access

router = Router()


class AdminSetup(StatesGroup):
    telegram_id = State()
    display_name = State()
    role = State()


def keyboard(items):
    b = InlineKeyboardBuilder()
    for text, callback in items:
        b.button(text=text, callback_data=callback)
    b.adjust(1)
    return b.as_markup()


async def list_keyboard(page=0):
    admins = await db.list_admin_access()
    items = [('➕ Admin qo‘shish', 'acl:add')]
    for a in admins[page*15:(page+1)*15]:
        label = a['full_name'] or str(a['user_id'])
        items.append((f"{'✅' if a['active'] else '⛔'} {label} — {ROLE_LABELS[a['role']]}", f"acl:user:{a['user_id']}"))
    if page:
        items.append(('◀️ Oldingi', f'acl:list:{page-1}'))
    if (page+1)*15 < len(admins):
        items.append(('Keyingi ▶️', f'acl:list:{page+1}'))
    return keyboard(items)


@router.message(Command('admins'))
@router.message(F.text == '👥 Adminlar va ruxsatlar')
async def admin_list(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer('👥 <b>Adminlar va ruxsatlar</b>\nAdminni tanlang yoki Telegram ID orqali qo‘shing.', reply_markup=await list_keyboard())


@router.callback_query(F.data.startswith('acl:list:'))
async def back_list(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text('👥 Adminlar va ruxsatlar', reply_markup=await list_keyboard(max(0, int(call.data.split(':')[-1]))))
    await call.answer()


@router.callback_query(F.data == 'acl:add')
async def add_start(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(AdminSetup.telegram_id)
    await call.message.answer('Yangi koordinatorning Telegram ID raqamini yuboring. Bekor qilish: /admin')
    await call.answer()


@router.message(AdminSetup.telegram_id, ~F.text.startswith("/"))
async def receive_id(msg: Message, state: FSMContext):
    raw = (msg.text or '').strip()
    if not raw.isdecimal() or not 0 < int(raw) < 2**63:
        await msg.answer('Musbat Telegram ID raqamini kiriting.')
        return
    user_id = int(raw)
    if user_id == SUPER_ADMIN_ID:
        await msg.answer('Bu super admin ID raqami. Uning huquqini bu yerdan o‘zgartirib bo‘lmaydi.')
        return
    await state.update_data(admin_target=user_id)
    await state.set_state(AdminSetup.role)
    await msg.answer(f'<code>{user_id}</code> uchun rolni tanlang.\nMavjud koordinator bo‘lsa, rol va ruxsatlar standart holatga qaytariladi.', reply_markup=keyboard([
        ('Bosh koordinator', 'acl:role:chief'), ('Yordamchi admin', 'acl:role:assistant'),
        ('◀️ Bekor qilish', 'acl:list:0')]))


@router.callback_query(AdminSetup.role, F.data.startswith('acl:role:'))
async def choose_role(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    target = data.get('admin_target')
    if not target or target == SUPER_ADMIN_ID:
        await call.answer('Telegram ID ni qaytadan kiriting.', show_alert=True)
        return
    role = call.data.split(':')[-1]
    if role == 'chief':
        await db.save_admin_access(call.from_user.id, target, role, display_name=None)
        await state.clear()
        await show_user(call, target)
    elif role == 'assistant':
        await state.set_state(AdminSetup.display_name)
        await call.message.edit_text('Yordamchi admin uchun ko‘rinadigan nomni kiriting (masalan: Ali yoki Media mas’ul).')
    await call.answer()


@router.message(AdminSetup.display_name, ~F.text.startswith("/"))
async def receive_display_name(msg: Message, state: FSMContext):
    name = (msg.text or '').strip()
    target = (await state.get_data()).get('admin_target')
    if not target or not 1 <= len(name) <= 120:
        await msg.answer('Nom 1–120 belgidan iborat bo‘lsin.')
        return
    await db.save_admin_access(msg.from_user.id, target, 'assistant', display_name=name)
    await state.clear()
    await msg.answer(f'✅ Yordamchi admin saqlandi: {escape(name)}', reply_markup=await list_keyboard())



async def show_user(call, target):
    row = await db.get_admin_access(target)
    if not row:
        await call.answer('Koordinator topilmadi.', show_alert=True)
        return
    overrides = {r['permission']: r['allowed'] for r in await db.get_admin_overrides(target)}
    items = []
    for permission in PERMISSIONS:
        if permission not in ROLE_PERMISSIONS[row['role']]:
            continue
        enabled = overrides.get(permission, True)
        items.append((f"{'✅' if enabled else '⛔'} {PERMISSIONS[permission]}", f'acl:perm:{target}:{permission}:{int(not enabled)}'))
    items += [(('⛔ Kirishni to‘xtatish' if row['active'] else '✅ Kirishni tiklash'), f"acl:active:{target}:{int(not row['active'])}"),
              ('◀️ Adminlar ro‘yxati', 'acl:list:0')]
    scope = row.get('display_name') or 'Nom berilmagan'
    await call.message.edit_text(
        f"👤 <code>{target}</code> — {ROLE_LABELS[row['role']]}\n"
        f"🗂 {escape(scope)}\nHolat: {'Faol' if row['active'] else 'Kirish to‘xtatilgan'}\n\n"
        'Ruxsatni yoqish yoki o‘chirish uchun bosing. O‘zgarish keyingi amaldan kuchga kiradi.\n'
        'Admin tayinlash va tizim sozlamalari faqat super adminda qoladi.', reply_markup=keyboard(items))


@router.callback_query(F.data.startswith('acl:user:'))
async def user_detail(call: CallbackQuery):
    await show_user(call, int(call.data.split(':')[-1]))
    await call.answer()


@router.callback_query(F.data.startswith('acl:perm:'))
async def set_permission(call: CallbackQuery):
    _, _, target, permission, value = call.data.split(':')
    target = int(target)
    row = await db.get_admin_access(target)
    if target == SUPER_ADMIN_ID or not row or permission not in ROLE_PERMISSIONS[row['role']] or value not in {'0', '1'}:
        await call.answer('Ruxsatni o‘zgartirib bo‘lmaydi.', show_alert=True)
        return
    await db.set_admin_permission(call.from_user.id, target, permission, value == '1')
    await show_user(call, target)
    await call.answer('Saqlandi')


@router.callback_query(F.data.startswith('acl:active:'))
async def set_active(call: CallbackQuery):
    _, _, target, value = call.data.split(':')
    target = int(target)
    if target == SUPER_ADMIN_ID or value not in {'0', '1'} or not await db.get_admin_access(target):
        await call.answer('Bu akkaunt holatini o‘zgartirib bo‘lmaydi.', show_alert=True)
        return
    await db.set_admin_active(call.from_user.id, target, value == '1')
    await show_user(call, target)
    await call.answer('Saqlandi')

