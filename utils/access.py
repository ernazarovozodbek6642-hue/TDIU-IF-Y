"""Role defaults, individual permission overrides and event scope checks."""
from dataclasses import dataclass

from data.config import ADMINS

PERMISSIONS = {
    "create_event": "Tadbir yaratish",
    "edit_event": "Tadbirni tahrirlash",
    "approve_event": "Tadbirni tasdiqlash va e’lon qilish",
    "attendance": "Davomatni yuritish",
    "close_event": "Tadbirni yakunlash",
    "reports": "Hisobotlarni ko‘rish",
    "broadcast": "Xabar yuborish",
    "winners": "Oy talabalarini boshqarish",
    "view_activists": "Faollarni ko‘rish va izlash",
    "manage_scores": "Faollarga ball qo‘shish va ayirish",
    "export_activists": "Faollar ma’lumotini Excel orqali olish",
    "delete_activists": "Faolni ro‘yxatdan o‘chirish",
    "upload_media": "Biriktirilgan tadbirga rasm yuklash",
}
OPTIONAL_PERMISSIONS = frozenset({
    "view_activists", "manage_scores", "export_activists", "delete_activists",
})
ROLE_LABELS = {"super": "Super admin", "chief": "Bosh koordinator", "assistant": "Yordamchi admin",
               "responsible": "Tadbir mas’uli", "media": "Media mas’ul"}
ROLE_PERMISSIONS = {
    "super": frozenset(PERMISSIONS),
    # Deleting an activist is intentionally not a default chief capability;
    # the super admin may grant it explicitly when needed.
    "chief": frozenset(set(PERMISSIONS) - {"delete_activists"}),
    "assistant": frozenset({"create_event", "edit_event", "attendance", "close_event", "reports", "broadcast", "upload_media"}),
    "responsible": frozenset({"attendance", "reports", "upload_media"}),
    "media": frozenset({"upload_media"}),
}


@dataclass(frozen=True)
class Access:
    user_id: int
    role: str | None = None
    direction_id: int | None = None
    display_name: str | None = None
    permissions: frozenset = frozenset()

    def allows(self, permission):
        return self.role == "super" or permission in self.permissions

    def in_scope(self, event, own_event=False):
        if not self.role or not event:
            return False
        if self.role == "assistant" and own_event:
            return self.user_id in {
                event.get("created_by"), event.get("responsible_person")
            }
        if self.role == "responsible":
            return self.user_id == event.get("responsible_person")
        if self.role == "media":
            return self.user_id == event.get("media_responsible")
        return True

    def can_event(self, event, permission):
        if permission == "upload_media":
            return bool(event) and self.allows(permission) and self.user_id == event.get("media_responsible")
        assistant_own_only = {"edit_event", "attendance", "reports", "close_event", "broadcast"}
        own = self.role == "assistant" and permission in assistant_own_only
        return self.allows(permission) and self.in_scope(event, own_event=own)


async def get_access(db, user_id):
    if str(user_id) in ADMINS:
        return Access(user_id, "super", permissions=ROLE_PERMISSIONS["super"])
    row = await db.get_admin_access(user_id)
    # A deliberately deactivated administrator must not regain permissions merely
    # because they are still assigned to an event. Event responsibility is only
    # an implicit role for users who have never had an administrator record.
    if row and not row["active"]:
        return Access(user_id)
    if not row:
        if await db.has_active_event_responsibility(user_id):
            return Access(user_id, "responsible", permissions=ROLE_PERMISSIONS["responsible"])
        if await db.has_event_media_responsibility(user_id):
            return Access(user_id, "media", permissions=ROLE_PERMISSIONS["media"])
        return Access(user_id)
    allowed = ROLE_PERMISSIONS.get(row["role"], frozenset())
    # Unknown permissions never grant access; a role change resets overrides.
    overrides = await db.get_admin_overrides(user_id)
    disabled = {r["permission"] for r in overrides if not r["allowed"]}
    # Sensitive optional capabilities are disabled by default and may only be
    # granted explicitly by the super admin. Existing role caps remain intact
    # for every other permission.
    enabled_optional = {
        r["permission"] for r in overrides
        if r["allowed"] and r["permission"] in OPTIONAL_PERMISSIONS
    }
    return Access(
        user_id, row["role"], row.get("direction_id"), row.get("display_name"),
        (allowed - disabled) | enabled_optional,
    )


async def can_view_event(db, user_id, event):
    access = await get_access(db, user_id)
    return access.in_scope(event, own_event=access.role == "assistant") and bool(access.permissions)
