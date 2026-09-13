import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.types import CallbackQuery, Chat, Message, User
from data.config import SUPER_ADMIN_ID
from middlewares.access import AccessMiddleware
from utils.access import Access, ROLE_PERMISSIONS, get_access


class FakeDatabase:
    def __init__(self):
        self.rows = {
            101: dict(role='chief', direction_id=None, active=True),
            102: dict(role='assistant', direction_id=None, active=True),
            103: dict(role='assistant', direction_id=None, active=True),
        }
        self.overrides = {}
        self.events = {
            10: dict(event_id=10, direction_id=1, created_by=102, responsible_person=102,
                     media_responsible=None, is_closed=False, approval_status='approved'),
            20: dict(event_id=20, direction_id=2, created_by=103, responsible_person=103,
                     media_responsible=None, is_closed=False, approval_status='approved'),
        }

    async def get_admin_access(self, user_id):
        return self.rows.get(user_id)

    async def get_admin_overrides(self, user_id):
        return self.overrides.get(user_id, [])

    async def get_event(self, event_id):
        return self.events.get(event_id)

    async def has_active_event_responsibility(self, user_id):
        return any(
            not event['is_closed'] and user_id in {event['responsible_person'], event['media_responsible']}
            for event in self.events.values()
        )


def callback(user_id, data):
    return CallbackQuery(id='test', from_user=User(id=user_id, is_bot=False, first_name='Test'),
                         chat_instance='test', data=data)


def message(user_id):
    return Message(message_id=1, date=datetime.now(timezone.utc),
                   chat=Chat(id=user_id, type='private'), from_user=User(id=user_id, is_bot=False, first_name='Test'), text='test')


class AccessTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = FakeDatabase()

    async def invoke(self, uid, permission, cb=None, name='target', state_data=None):
        async def target(): pass
        target.__name__ = name
        handler = AsyncMock(return_value='handled')
        state = SimpleNamespace(get_data=AsyncMock(return_value=state_data or {}), clear=AsyncMock())
        event = callback(uid, cb) if cb else message(uid)
        data = dict(handler=SimpleNamespace(callback=target), state=state)
        with patch('loader.db', self.db), patch.object(CallbackQuery, 'answer', new_callable=AsyncMock), patch.object(Message, 'answer', new_callable=AsyncMock):
            result = await AccessMiddleware(permission, event_scope=True)(handler, event, data)
        return result, handler, state

    async def test_single_owner(self):
        owner = await get_access(self.db, SUPER_ADMIN_ID)
        self.assertEqual(owner.role, 'super')
        self.assertTrue(owner.allows('manage_admins'))
        self.assertIsNone((await get_access(self.db, 999)).role)

    async def test_role_caps_cannot_be_overridden(self):
        self.db.overrides[102] = [dict(permission='approve_event', allowed=True)]
        self.assertFalse((await get_access(self.db, 102)).allows('approve_event'))

    async def test_permission_revocation_is_immediate(self):
        self.assertTrue((await get_access(self.db, 101)).allows('broadcast'))
        self.db.overrides[101] = [dict(permission='broadcast', allowed=False)]
        self.assertFalse((await get_access(self.db, 101)).allows('broadcast'))
        result, handler, state = await self.invoke(101, 'broadcast', cb='bcast:send')
        handler.assert_not_awaited()
        state.clear.assert_awaited_once()

    async def test_deactivated_admin_has_no_legacy_responsible_bypass(self):
        self.db.rows[102]['active'] = False
        _, handler, _ = await self.invoke(102, 'attendance', cb='toggleattend:10:7')
        handler.assert_not_awaited()

    async def test_forged_cross_direction_callback_denied(self):
        _, handler, _ = await self.invoke(102, 'attendance', cb='toggleattend:20:7')
        handler.assert_not_awaited()

    async def test_same_direction_unassigned_event_attendance_denied(self):
        self.db.events[10].update(created_by=555, responsible_person=555)
        _, handler, _ = await self.invoke(102, 'attendance', cb='evattend:10')
        handler.assert_not_awaited()
        self.assertFalse((await get_access(self.db, 102)).can_event(self.db.events[10], 'reports'))

    async def test_chief_can_manage_all_directions(self):
        result, handler, _ = await self.invoke(101, 'attendance', cb='evattend:20')
        self.assertEqual(result, 'handled')
        handler.assert_awaited_once()

    async def test_old_fsm_edit_rechecks_direction(self):
        _, handler, _ = await self.invoke(102, 'edit_event', name='edit_field_value', state_data={'edit_event_id': 20})
        handler.assert_not_awaited()

    async def test_missing_fsm_event_is_denied(self):
        _, handler, _ = await self.invoke(101, 'edit_event', name='edit_field_value')
        handler.assert_not_awaited()

    async def test_pending_event_has_no_attendance(self):
        self.db.events[10]['approval_status'] = 'pending'
        _, handler, _ = await self.invoke(SUPER_ADMIN_ID, 'attendance', cb='toggleattend:10:7')
        handler.assert_not_awaited()

    async def test_published_event_edit_requires_approval_permission(self):
        _, handler, _ = await self.invoke(102, 'edit_event', cb='editevent:10')
        handler.assert_not_awaited()
        self.db.events[10]['approval_status'] = 'pending'
        _, handler, _ = await self.invoke(102, 'edit_event', cb='editevent:10')
        handler.assert_awaited_once()

    async def test_closed_event_cannot_change_attendance(self):
        self.db.events[10]['is_closed'] = True
        _, handler, _ = await self.invoke(SUPER_ADMIN_ID, 'attendance', cb='toggleattend:10:7')
        handler.assert_not_awaited()

    async def test_chief_cannot_access_owner_panel(self):
        _, handler, _ = await self.invoke(101, 'super', cb='acl:perm:102:broadcast:1')
        handler.assert_not_awaited()

    async def test_owner_cannot_lock_self_out(self):
        self.db.rows[SUPER_ADMIN_ID] = dict(role='chief', direction_id=None, active=False)
        self.assertEqual((await get_access(self.db, SUPER_ADMIN_ID)).role, 'super')

    async def test_unassigned_event_not_visible_to_assistant(self):
        self.db.events[10]['direction_id'] = None
        self.db.events[10].update(created_by=555, responsible_person=555, media_responsible=None)
        _, handler, _ = await self.invoke(102, None, cb='event:10')
        handler.assert_not_awaited()

    async def test_revoked_media_upload_continuation_denied(self):
        self.db.overrides[102] = [dict(permission='attendance', allowed=False)]
        _, handler, _ = await self.invoke(102, 'attendance', name='upload_media_photo', state_data={'media_event_id': 10})
        handler.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
