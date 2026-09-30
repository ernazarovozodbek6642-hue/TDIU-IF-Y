from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery
from utils.access import get_access


class AccessMiddleware(BaseMiddleware):
    """Checks current rights on every matched handler, including FSM continuations."""
    def __init__(self, permission=None, overrides=None, event_scope=False):
        self.permission = permission
        self.overrides = overrides or {}
        self.event_scope = event_scope

    async def __call__(self, handler, event, data):
        from loader import db
        name = data['handler'].callback.__name__
        if name in {'admin_exit', 'admin_home', 'panel_exit'}:
            return await handler(event, data)
        permission = self.overrides.get(name, self.permission)
        if permission == 'public':
            return await handler(event, data)
        access = await get_access(db, event.from_user.id)
        allowed = bool(access.role)
        if permission == 'super':
            allowed = access.role == 'super'
        elif permission:
            allowed = allowed and access.allows(permission)
        else:
            allowed = allowed and bool(access.permissions)
        event_id = None
        state_data = await data['state'].get_data() if data.get('state') else {}
        if self.event_scope:
            if isinstance(event, CallbackQuery):
                parts = (event.data or '').split(':')
                if parts[0] in {'event', 'evattend', 'toggleattend', 'eventmedia', 'evclose',
                                'editevent', 'editfield', 'editvmethod', 'editback', 'editpick',
                                'uploadmedia', 'eventexcel', 'proofconfirm', 'proofreject', 'approveevent'}:
                    try:
                        event_id = int(parts[1])
                    except (ValueError, IndexError):
                        allowed = False
            if isinstance(event, CallbackQuery) and event_id is None:
                parts = (event.data or '').split(':')
                if parts[0] in {'attpage', 'attsearch', 'attall'}:
                    try:
                        event_id = int(parts[1])
                    except (ValueError, IndexError):
                        allowed = False
            if event_id is None and name in {
                    'edit_field_value', 'upload_media_document', 'upload_media_photo',
                    'attendance_search_query'}:
                event_id = (state_data.get('edit_event_id') or state_data.get('media_event_id')
                            or state_data.get('attendance_event_id'))
                if not event_id:
                    allowed = False
            if event_id is not None:
                target = await db.get_event(event_id)
                allowed = allowed and (
                    access.can_event(target, permission)
                    if permission else access.in_scope(target, own_event=access.role == "assistant")
                )
                if target and permission in {'attendance', 'close_event'}:
                    allowed = allowed and target['approval_status'] == 'approved'
                media_upload = name in {'upload_media_start', 'upload_media_document', 'upload_media_photo'}
                if target and permission in {'attendance', 'close_event', 'edit_event'} and not media_upload:
                    allowed = allowed and not target['is_closed']
                if target and permission == 'edit_event' and target['approval_status'] == 'approved':
                    allowed = allowed and access.allows('approve_event')
        if not allowed:
            text = '⛔ Bu amal uchun ruxsatingiz yo‘q yoki super admin ruxsatni cheklagan. /admin orqali menyuni yangilang.'
            if isinstance(event, CallbackQuery):
                await event.answer(text, show_alert=True)
            else:
                await event.answer(text)
            if data.get('state'):
                await data['state'].clear()
            return
        data['access'] = access
        return await handler(event, data)


def protect(router, permission=None, overrides=None, event_scope=False):
    middleware = AccessMiddleware(permission, overrides, event_scope)
    router.message.middleware(middleware)
    router.callback_query.middleware(middleware)
