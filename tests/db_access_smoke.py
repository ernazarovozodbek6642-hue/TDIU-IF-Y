"""Explicit DB smoke check: isolated schema, always rolled back, no Telegram calls."""
import asyncio
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.db_api.SQL import Database
from utils.access import get_access


class PinnedPool:
    def __init__(self, conn): self.conn = conn
    def acquire(self): return self
    async def __aenter__(self): return self.conn
    async def __aexit__(self, *args): pass


async def main():
    db = Database()
    await db.create()
    pool = db.pool
    try:
        async with pool.acquire() as conn:
            transaction = conn.transaction()
            await transaction.start()
            try:
                schema = 'acl_smoke_' + uuid.uuid4().hex
                await conn.execute(f'CREATE SCHEMA {schema}')
                await conn.execute(f'SET LOCAL search_path TO {schema}')
                await conn.execute('''
                    CREATE TABLE users(user_id BIGINT PRIMARY KEY, full_name TEXT, group_name TEXT);
                    CREATE TABLE events(event_id BIGINT PRIMARY KEY, event_name TEXT, description TEXT,
                        date DATE, location TEXT, time TIME, responsible_person BIGINT, score INTEGER,
                        media_responsible BIGINT, participants_count INTEGER, verification_method TEXT,
                        penalty_score INTEGER, waitlist_count INTEGER, is_closed BOOLEAN DEFAULT FALSE);
                    CREATE TABLE event_users(event_id BIGINT,user_id BIGINT,status TEXT,is_waitlist BOOLEAN,joined_at TIMESTAMPTZ,
                        PRIMARY KEY(event_id,user_id));
                    INSERT INTO events(event_id,event_name) VALUES(1,'legacy');
                ''')
                db.pool = PinnedPool(conn)
                await db.create_access_tables()
                await db.create_access_tables()
                assert (await db.get_event(1))['approval_status'] == 'approved'
                direction = await db.add_direction(5589013665, 'Smoke test')
                await db.save_admin_access(5589013665, 100001, 'assistant', 'Smoke admin')
                await db.set_admin_permission(5589013665, 100001, 'broadcast', False)
                assert not (await get_access(db, 100001)).allows('broadcast')
                await db.set_admin_active(5589013665, 100001, False)
                assert not (await get_access(db, 100001)).role
                await db.save_admin_access(5589013665, 100001, 'assistant', 'Smoke admin')
                assert (await get_access(db, 100001)).allows('broadcast')
                await db.add_event(2, 'pending', 'test', date.today(), participants_count=10,
                                   waitlist_count=1, direction_id=direction['direction_id'], created_by=100001)
                assert await db.register_user_to_event(2, 100002) == (None, 'full')
                assert not any(e['event_id'] == 2 for e in await db.get_upcoming_events_open_for_registration())
                assert await db.approve_event_once(2, 5589013665)
                assert await db.approve_event_once(2, 5589013665) is None
                row, slot = await db.register_user_to_event(2, 100002)
                assert slot == 'main'
                assert row['user_id'] == 100002
                scoped = await db.get_scoped_events(direction['direction_id'], 100001)
                assert [e['event_id'] for e in scoped] == [2]
                await db.get_direction_report(direction['direction_id'])
                assert await conn.fetchval('SELECT count(*) FROM admin_access_audit') == 5
                print('DB smoke OK: migration idempotence, legacy preservation, role/permission persistence, pending registration gate, single approval, scoped queries.')
            finally:
                await transaction.rollback()
                db.pool = pool
                print('Isolated schema rolled back; no test records retained.')
    finally:
        await db.close()


if __name__ == '__main__':
    asyncio.run(main())
