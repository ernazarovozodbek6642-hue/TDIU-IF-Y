"""Additive schema and queries for administrator access control."""
class AccessDatabase:
    async def create_access_tables(self):
        await self.execute("""
            CREATE TABLE IF NOT EXISTS admin_directions (
                direction_id SERIAL PRIMARY KEY,
                name VARCHAR(100) UNIQUE NOT NULL
            );
            CREATE TABLE IF NOT EXISTS admin_access (
                user_id BIGINT PRIMARY KEY,
                role TEXT NOT NULL CHECK (role IN ('chief', 'assistant')),
                display_name VARCHAR(120),
                direction_id INTEGER REFERENCES admin_directions(direction_id),
                active BOOLEAN NOT NULL DEFAULT TRUE,
                CHECK (role != 'assistant' OR direction_id IS NULL)
            );
            CREATE TABLE IF NOT EXISTS admin_permission_overrides (
                user_id BIGINT REFERENCES admin_access(user_id) ON DELETE CASCADE,
                permission TEXT NOT NULL,
                allowed BOOLEAN NOT NULL,
                PRIMARY KEY(user_id, permission)
            );
            CREATE TABLE IF NOT EXISTS admin_access_audit (
                id BIGSERIAL PRIMARY KEY,
                actor_id BIGINT NOT NULL,
                target_id BIGINT,
                action TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            ALTER TABLE admin_access DROP CONSTRAINT IF EXISTS admin_access_role_check;
            ALTER TABLE admin_access DROP CONSTRAINT IF EXISTS admin_access_check;
            UPDATE admin_access SET role='assistant', direction_id=NULL WHERE role='direction';
            ALTER TABLE admin_access ADD CONSTRAINT admin_access_role_check CHECK (role IN ('chief', 'assistant'));
            ALTER TABLE admin_access ADD COLUMN IF NOT EXISTS display_name VARCHAR(120);
            ALTER TABLE events ADD COLUMN IF NOT EXISTS direction_id INTEGER REFERENCES admin_directions(direction_id);
            ALTER TABLE events ADD COLUMN IF NOT EXISTS created_by BIGINT;
            ALTER TABLE events ADD COLUMN IF NOT EXISTS approval_status TEXT NOT NULL DEFAULT 'approved';
            ALTER TABLE events ADD COLUMN IF NOT EXISTS approved_by BIGINT;
            CREATE INDEX IF NOT EXISTS events_direction_idx ON events(direction_id);
        """, execute=True)

    async def get_admin_access(self, user_id):
        return await self.execute("SELECT * FROM admin_access WHERE user_id=$1", user_id, fetchrow=True)

    async def get_admin_overrides(self, user_id):
        return await self.execute("SELECT permission, allowed FROM admin_permission_overrides WHERE user_id=$1", user_id, fetch=True)

    async def list_admin_access(self):
        return await self.execute("""SELECT a.*, d.name AS direction_name, COALESCE(a.display_name, u.full_name) AS full_name
            FROM admin_access a LEFT JOIN admin_directions d USING(direction_id)
            LEFT JOIN users u USING(user_id) ORDER BY a.user_id""", fetch=True)

    async def save_admin_access(self, actor_id, user_id, role, display_name=None):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("""INSERT INTO admin_access(user_id,role,display_name,direction_id) VALUES($1,$2,$3,NULL)
                    ON CONFLICT(user_id) DO UPDATE SET role=$2, display_name=$3, direction_id=NULL, active=TRUE""", user_id, role, display_name)
                await conn.execute("DELETE FROM admin_permission_overrides WHERE user_id=$1", user_id)
                await conn.execute("INSERT INTO admin_access_audit(actor_id,target_id,action) VALUES($1,$2,$3)",
                                   actor_id, user_id, f"role={role}; defaults restored")

    async def set_admin_permission(self, actor_id, user_id, permission, allowed):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("""INSERT INTO admin_permission_overrides VALUES($1,$2,$3)
                    ON CONFLICT(user_id,permission) DO UPDATE SET allowed=$3""", user_id, permission, allowed)
                await conn.execute("INSERT INTO admin_access_audit(actor_id,target_id,action) VALUES($1,$2,$3)",
                                   actor_id, user_id, f"{permission}={allowed}")

    async def set_admin_active(self, actor_id, user_id, active):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("UPDATE admin_access SET active=$2 WHERE user_id=$1", user_id, active)
                await conn.execute("INSERT INTO admin_access_audit(actor_id,target_id,action) VALUES($1,$2,$3)",
                                   actor_id, user_id, f"active={active}")

    async def get_directions(self):
        return await self.execute("SELECT * FROM admin_directions ORDER BY name", fetch=True)

    async def add_direction(self, actor_id, name):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow("""INSERT INTO admin_directions(name) VALUES($1)
                    ON CONFLICT(name) DO UPDATE SET name=EXCLUDED.name RETURNING *""", name)
                await conn.execute("INSERT INTO admin_access_audit(actor_id,action) VALUES($1,$2)", actor_id, f"direction={name}")
                return row

    async def get_scoped_events(self, direction_id=None, own_user_id=None):
        return await self.execute("""SELECT * FROM events
            WHERE ($1::integer IS NULL OR direction_id=$1)
            AND ($2::bigint IS NULL OR created_by=$2 OR responsible_person=$2 OR media_responsible=$2)
            ORDER BY date DESC, event_id""", direction_id, own_user_id, fetch=True)

    async def get_direction_report(self, direction_id):
        return await self.execute("""SELECT e.event_name, e.date, u.full_name, u.group_name,
            eu.status, eu.is_waitlist
            FROM event_users eu JOIN events e USING(event_id) JOIN users u USING(user_id)
            WHERE e.direction_id=$1 ORDER BY e.date DESC, e.event_id, u.full_name""", direction_id, fetch=True)

    async def approve_event_once(self, event_id, actor_id):
        return await self.execute("""UPDATE events SET approval_status='approved', approved_by=$2
            WHERE event_id=$1 AND approval_status='pending' AND NOT is_closed RETURNING *""",
            event_id, actor_id, fetchrow=True)
