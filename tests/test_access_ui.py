import unittest
from contextlib import ExitStack
from datetime import datetime, timezone
from unittest.mock import patch

from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.types import User, Message, Chat, Update, CallbackQuery
from data.config import SUPER_ADMIN_ID
from handlers import setup_routers
from test_access import FakeDatabase


class FakeSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.calls = []

    async def close(self): pass

    async def stream_content(self, *args, **kwargs):
        yield b''

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if method.__api_method__ == 'getMe':
            return User(id=12345, is_bot=True, first_name='Test', username='test_bot')
        if method.__api_method__ == 'answerCallbackQuery':
            return True
        return Message(message_id=42, date=datetime.now(timezone.utc), chat=Chat(id=SUPER_ADMIN_ID, type='private'),
                       from_user=User(id=12345, is_bot=True, first_name='Bot'), text=getattr(method, 'text', 'test'))


class UIDatabase(FakeDatabase):
    def __init__(self):
        super().__init__()
        self.directions = [dict(direction_id=1, name='Sport')]

    async def get_directions(self): return self.directions

    async def list_admin_access(self):
        return [dict(user_id=uid, full_name=None, direction_name=None, **r) for uid, r in self.rows.items()]

    async def save_admin_access(self, actor_id, user_id, role, display_name=None):
        self.rows[user_id] = dict(role=role, direction_id=None, display_name=display_name, active=True)
        self.overrides[user_id] = []

    async def set_admin_permission(self, actor_id, user_id, permission, allowed):
        self.overrides[user_id] = [dict(permission=permission, allowed=allowed)]

    async def set_admin_active(self, actor_id, user_id, active):
        self.rows[user_id]['active'] = active


class RouterFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_owner_id_assignment_toggle_revocation_and_cancel(self):
        database = UIDatabase()
        session = FakeSession()
        bot = Bot(token='12345:unit_test_token', session=session)
        dp = Dispatcher()
        setup_routers(dp)
        update_id = 0

        async def send(uid, text=None, callback=None):
            nonlocal update_id
            update_id += 1
            user = User(id=uid, is_bot=False, first_name='Test')
            msg = Message(message_id=update_id, date=datetime.now(timezone.utc), chat=Chat(id=uid, type='private'), from_user=user, text=text or 'panel')
            update = Update(update_id=update_id, message=msg) if text else Update(update_id=update_id, callback_query=CallbackQuery(id=str(update_id), from_user=user, chat_instance='test', data=callback, message=msg))
            return await dp.feed_update(bot, update)

        with ExitStack() as stack:
            for name in ('loader.db', 'handlers.users.ADMIN.access_admin.db', 'handlers.commands.db'):
                stack.enter_context(patch(name, database))
            await send(SUPER_ADMIN_ID, text='/admins')
            self.assertIn('Adminlar', session.calls[-1].text)
            await send(SUPER_ADMIN_ID, callback='acl:add')
            await send(SUPER_ADMIN_ID, text='777')
            await send(SUPER_ADMIN_ID, callback='acl:role:assistant')
            await send(SUPER_ADMIN_ID, text='Audit admin')
            self.assertEqual(database.rows[777]['role'], 'assistant')
            await send(SUPER_ADMIN_ID, callback='acl:perm:777:broadcast:0')
            self.assertFalse(database.overrides[777][0]['allowed'])
            await send(777, text='/admin')
            buttons = [b.text for row in session.calls[-1].reply_markup.keyboard for b in row]
            self.assertNotIn('✉️Faollarga habar yuborish', buttons)
            self.assertNotIn('👥 Adminlar va ruxsatlar', buttons)
            await send(777, callback='acl:active:102:0')
            self.assertTrue(database.rows[102]['active'])
            await send(SUPER_ADMIN_ID, callback='acl:active:777:0')
            await send(777, text='/admin')
            self.assertIn("huquqi yo'q", session.calls[-1].text)
            await send(SUPER_ADMIN_ID, callback='acl:add')
            await send(SUPER_ADMIN_ID, text='/admin')
            self.assertIn('Admin paneli', session.calls[-1].text)
        await dp.storage.close()
        await session.close()
