from aiogram import Dispatcher

from . import commands
from middlewares.access import protect
from middlewares.membership import MembershipMiddleware
from .users.ADMIN import access_admin, approvals, activists
from .errors import error_handler
from .users.ADMIN import (
    add_event, edit_event, event_list, settings as admin_settings,
    groups as admin_groups, broadcast as admin_broadcast, export as admin_export,
    winners as admin_winners
)
from .users.PANEL import panel
from .users.Users import new_users
from . import verification
from .users import help as help_


def setup_routers(dp: Dispatcher):
    protect(access_admin.router, "super")
    protect(activists.router, "view_activists", {
        "score_adjust_start": "manage_scores",
        "score_adjust_amount": "manage_scores",
        "score_adjust_reason": "manage_scores",
        "activist_delete_start": "delete_activists",
        "activist_delete_confirm": "delete_activists",
    })
    protect(approvals.router, "approve_event", event_scope=True)
    protect(add_event.router, "create_event")
    protect(edit_event.router, "edit_event", event_scope=True)
    protect(event_list.router, overrides={
        "event_attendance_list": "attendance", "toggle_attendance": "attendance",
        "attendance_page": "attendance", "attendance_search_start": "attendance",
        "attendance_search_query": "attendance", "attendance_show_all": "attendance",
        "close_event_handler": "close_event", "event_media": "reports",
    }, event_scope=True)
    protect(admin_settings.router, "super")
    protect(admin_groups.router, "super")
    protect(admin_broadcast.router, "broadcast")
    protect(admin_export.router, "export_activists")
    protect(admin_winners.router, "winners")
    protect(panel.router, "attendance", {
        "my_events": None, "panel_back_to_events": None,
        "event_excel_report": "reports",
        "upload_media_start": "upload_media",
        "upload_media_document": "upload_media",
        "upload_media_photo": "upload_media",
    }, event_scope=True)
    protect(verification.router, "public", {
        "proof_confirm": "attendance", "proof_reject": "attendance",
    }, event_scope=True)
    dp.include_router(error_handler.router)
    dp.include_router(access_admin.router)
    dp.include_router(activists.router)
    dp.include_router(approvals.router)
    dp.include_router(commands.router)
    new_users.router.message.middleware(MembershipMiddleware())
    new_users.router.callback_query.middleware(MembershipMiddleware())
    dp.include_router(new_users.router)
    dp.include_router(add_event.router)
    dp.include_router(edit_event.router)
    dp.include_router(event_list.router)
    dp.include_router(admin_settings.router)
    dp.include_router(admin_groups.router)
    dp.include_router(admin_broadcast.router)
    dp.include_router(admin_export.router)
    dp.include_router(admin_winners.router)
    dp.include_router(panel.router)
    dp.include_router(verification.router)
    dp.include_router(help_.router)

