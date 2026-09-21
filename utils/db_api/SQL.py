from typing import Union
import asyncpg
from datetime import time as dtime, datetime
from asyncpg.pool import Pool
from asyncpg import Connection
from datetime import date
from data import config  # DB konfiguratsiyangiz


from utils.db_api.access import AccessDatabase


class Database(AccessDatabase):
    USER_UPDATE_FIELDS = {
        "full_name", "passport_number", "birth_date", "phone_number", "location", "group_name",
        "profile_photo_file_id", "profile_photo_message_id", "user_name", "lives_in_dormitory",
    }
    EVENT_UPDATE_FIELDS = {
        "event_name", "description", "date", "location", "time", "responsible_person",
        "score", "media_responsible", "participants_count", "verification_method",
        "penalty_score", "waitlist_count",
    }

    def __init__(self):
        self.pool: Union[Pool, None] = None
        self._instance_lock_connection = None

    # ----------------- CONNECT / CLOSE -----------------
    async def create(self):
        self.pool = await asyncpg.create_pool(
            user=config.DB_USER,
            password=config.DB_PASS,
            host=config.DB_HOST,
            database=config.DB_NAME,
            port=config.DB_PORT,
            ssl=config.DB_SSL,
            min_size=0,
            max_size=3,
            max_inactive_connection_lifetime=60,
            command_timeout=15,
        )
        print("Database connected!")

    async def close(self):
        if self.pool:
            if self._instance_lock_connection:
                await self._instance_lock_connection.execute("SELECT pg_advisory_unlock($1)", 824214567301)
                await self.pool.release(self._instance_lock_connection)
                self._instance_lock_connection = None
            await self.pool.close()
            self.pool = None
            print("Database closed!")

    async def acquire_instance_lock(self):
        """Prevent two polling/scheduler instances from processing the same bot."""
        if self.pool is None:
            raise RuntimeError("Database pool is not initialized")
        connection = await self.pool.acquire()
        locked = await connection.fetchval("SELECT pg_try_advisory_lock($1)", 824214567301)
        if not locked:
            await self.pool.release(connection)
            raise RuntimeError("Another bot instance is already running")
        self._instance_lock_connection = connection

    # ----------------- UNIVERSAL EXECUTE -----------------
    async def execute(
            self,
            command,
            *args,
            fetch: bool = False,
            fetchval: bool = False,
            fetchrow: bool = False,
            execute: bool = False
    ):
        if self.pool is None:
            raise RuntimeError("Database pool is not initialized")
        async with self.pool.acquire() as connection:
            connection: Connection
            async with connection.transaction():
                if execute:
                    result = await connection.execute(command, *args)
                elif fetch:
                    result = await connection.fetch(command, *args)
                elif fetchval:
                    result = await connection.fetchval(command, *args)
                elif fetchrow:
                    result = await connection.fetchrow(command, *args)
                else:
                    result = None
            return result

    # ----------------- SCHEMA (bir joyda, xavfsiz/qo'shimcha o'zgarish) -----------------
    async def create_tables(self):
        await self.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            user_name VARCHAR(100),
            full_name VARCHAR(150) NOT NULL,
            passport_number VARCHAR(50),
            phone_number VARCHAR(50),
            location VARCHAR(255),
            group_name VARCHAR(100),
            last_month_score DECIMAL(5,2),
            profile_image_url VARCHAR(500)
        );
        """, execute=True)
        # Yangi ustunlar (mavjud bazani buzmasdan qo'shamiz)
        await self.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_photo_file_id VARCHAR(300);", execute=True)
        await self.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_photo_message_id BIGINT;", execute=True)
        await self.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS penalty_count INT NOT NULL DEFAULT 0;", execute=True)
        await self.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_excluded BOOLEAN NOT NULL DEFAULT FALSE;", execute=True)
        await self.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS lives_in_dormitory BOOLEAN;", execute=True)
        await self.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS registration_status VARCHAR(20) NOT NULL DEFAULT 'approved';", execute=True)
        await self.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS reviewed_by BIGINT;", execute=True)
        await self.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ;", execute=True)
        await self.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS rejection_reason TEXT;", execute=True)
        await self.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS birth_date DATE;", execute=True)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS score_adjustments (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            amount INTEGER NOT NULL CHECK (amount <> 0),
            reason TEXT NOT NULL CHECK (char_length(trim(reason)) >= 3),
            actor_id BIGINT NOT NULL,
            month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
            year INTEGER NOT NULL CHECK (year BETWEEN 2000 AND 9999),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS score_adjustments_user_month_idx
            ON score_adjustments(user_id, year, month, created_at DESC);
        """, execute=True)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS events (
        event_id BIGINT PRIMARY KEY,
        event_name VARCHAR(255) NOT NULL,
        description TEXT,
        date DATE NOT NULL,
        location VARCHAR(255),
        time TIME,
        responsible_person BIGINT REFERENCES users(user_id),
        score INT,
        media_responsible BIGINT REFERENCES users(user_id),
        participants_count INT DEFAULT 0,
        created_at VARCHAR(50) DEFAULT TO_CHAR(NOW() AT TIME ZONE 'Asia/Tashkent', 'YYYY-MM-DD HH24:MI:SS')
        );
        """, execute=True)
        await self.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS verification_method VARCHAR(20) NOT NULL DEFAULT 'manual';", execute=True)
        await self.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS penalty_score INT NOT NULL DEFAULT 0;", execute=True)
        await self.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS is_closed BOOLEAN NOT NULL DEFAULT FALSE;", execute=True)
        await self.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS closed_at TIMESTAMP;", execute=True)
        await self.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS waitlist_count INT NOT NULL DEFAULT 0;", execute=True)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS event_users (
            event_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            attended BOOLEAN DEFAULT TRUE,
            PRIMARY KEY (event_id, user_id),
            FOREIGN KEY (event_id) REFERENCES events(event_id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        );
        """, execute=True)
        # status: pending -> confirmed / rejected / not_attended
        await self.execute("ALTER TABLE event_users ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'pending';", execute=True)
        await self.execute("ALTER TABLE event_users ADD COLUMN IF NOT EXISTS proof_photo_file_id VARCHAR(300);", execute=True)
        await self.execute("ALTER TABLE event_users ADD COLUMN IF NOT EXISTS proof_photo_message_id BIGINT;", execute=True)
        await self.execute("ALTER TABLE event_users ADD COLUMN IF NOT EXISTS confirmer_id BIGINT;", execute=True)
        await self.execute("ALTER TABLE event_users ADD COLUMN IF NOT EXISTS confirmed_by BIGINT;", execute=True)
        await self.execute("ALTER TABLE event_users ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMP;", execute=True)
        await self.execute("ALTER TABLE event_users ADD COLUMN IF NOT EXISTS request_message_id BIGINT;", execute=True)
        await self.execute("ALTER TABLE event_users ADD COLUMN IF NOT EXISTS last_reminder_at TIMESTAMP;", execute=True)
        # status endi: pending / confirmed / rejected / not_attended / withdrawn (o'zi voz kechgan)
        await self.execute("ALTER TABLE event_users ADD COLUMN IF NOT EXISTS is_waitlist BOOLEAN NOT NULL DEFAULT FALSE;", execute=True)
        await self.execute("ALTER TABLE event_users ADD COLUMN IF NOT EXISTS joined_at TIMESTAMP NOT NULL DEFAULT NOW();", execute=True)
        await self.execute(
            "CREATE INDEX IF NOT EXISTS event_users_event_status_idx "
            "ON event_users(event_id, status, is_waitlist, joined_at);",
            execute=True,
        )
        await self.execute(
            "CREATE INDEX IF NOT EXISTS event_users_user_status_idx ON event_users(user_id, status);",
            execute=True,
        )

        await self.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            group_id BIGINT PRIMARY KEY,
            title VARCHAR(255),
            added_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """, execute=True)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS event_announcements (
            id SERIAL PRIMARY KEY,
            event_id BIGINT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
            group_id BIGINT NOT NULL,
            message_id BIGINT NOT NULL,
            kind VARCHAR(20) NOT NULL DEFAULT 'announcement',
            UNIQUE (event_id, group_id, kind)
        );
        """, execute=True)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS event_media (
            id SERIAL PRIMARY KEY,
            event_id BIGINT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
            file_id VARCHAR(300) NOT NULL,
            message_id BIGINT,
            uploaded_by BIGINT,
            uploaded_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """, execute=True)
        # file_type: 'document' (asl sifatda, siqilmagan) yoki 'photo' (Telegram siqqan)
        await self.execute("ALTER TABLE event_media ADD COLUMN IF NOT EXISTS file_type VARCHAR(20) NOT NULL DEFAULT 'photo';", execute=True)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key VARCHAR(100) PRIMARY KEY,
            value VARCHAR(255) NOT NULL
        );
        """, execute=True)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS fsm_storage (
            bot_id BIGINT NOT NULL,
            chat_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            destiny TEXT NOT NULL DEFAULT 'default',
            state TEXT,
            data JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (bot_id, chat_id, user_id, destiny)
        );
        """, execute=True)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS monthly_winners (
            id SERIAL PRIMARY KEY,
            user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
            month INT NOT NULL,
            year INT NOT NULL,
            score NUMERIC(8,2) NOT NULL,
            rank INT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE (user_id, month, year)
        );
        """, execute=True)

        # Oy talabalari e'loni yuborilgan guruh xabarlari (bekor qilishda o'chirish uchun)
        await self.execute("""
        CREATE TABLE IF NOT EXISTS monthly_winner_messages (
            id SERIAL PRIMARY KEY,
            month INT NOT NULL,
            year INT NOT NULL,
            group_id BIGINT NOT NULL,
            message_id BIGINT NOT NULL,
            UNIQUE (month, year, group_id)
        );
        """, execute=True)

        await self.execute("""
        CREATE TABLE IF NOT EXISTS birthday_announcements (
            user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            group_id BIGINT NOT NULL,
            celebration_date DATE NOT NULL,
            message_id BIGINT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, group_id, celebration_date)
        );
        """, execute=True)

    # ----------------- SETTINGS -----------------
    async def get_setting(self, key: str, default: str = None):
        sql = "SELECT value FROM settings WHERE key=$1"
        value = await self.execute(sql, key, fetchval=True)
        return value if value is not None else default

    async def set_setting(self, key: str, value: str):
        sql = """
        INSERT INTO settings (key, value) VALUES ($1, $2)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        RETURNING *;
        """
        return await self.execute(sql, key, str(value), fetchrow=True)

    async def get_all_settings(self):
        sql = "SELECT * FROM settings ORDER BY key"
        return await self.execute(sql, fetch=True)

    # ----------------- USERS TABLE -----------------
    async def add_user(self, user_id: int, user_name: str, full_name: str, passport_number: str = None,
                        birth_date: date = None, phone_number: str = None, location: str = None,
                        group_name: str = None,
                        profile_photo_file_id: str = None, profile_photo_message_id: int = None,
                        lives_in_dormitory: bool = None, registration_status: str = "pending"):
        sql = """
        INSERT INTO users (user_id, user_name, full_name, passport_number, birth_date, phone_number, location, group_name,
                            profile_photo_file_id, profile_photo_message_id, lives_in_dormitory, registration_status)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
        ON CONFLICT (user_id) DO UPDATE SET
            user_name = EXCLUDED.user_name,
            full_name = EXCLUDED.full_name,
            passport_number = EXCLUDED.passport_number,
            birth_date = EXCLUDED.birth_date,
            phone_number = EXCLUDED.phone_number,
            location = EXCLUDED.location,
            group_name = EXCLUDED.group_name,
            profile_photo_file_id = EXCLUDED.profile_photo_file_id,
            profile_photo_message_id = EXCLUDED.profile_photo_message_id,
            lives_in_dormitory = EXCLUDED.lives_in_dormitory,
            registration_status = EXCLUDED.registration_status,
            reviewed_by = NULL, reviewed_at = NULL, rejection_reason = NULL
        RETURNING *;
        """
        return await self.execute(sql, user_id, user_name, full_name, passport_number, birth_date,
                                   phone_number, location, group_name, profile_photo_file_id,
                                   profile_photo_message_id, lives_in_dormitory, registration_status,
                                   fetchrow=True)

    async def get_user(self, user_id: int):
        sql = "SELECT * FROM users WHERE user_id = $1 AND registration_status = 'approved'"
        return await self.execute(sql, user_id, fetchrow=True)

    async def get_user_any_status(self, user_id: int):
        return await self.execute("SELECT * FROM users WHERE user_id=$1", user_id, fetchrow=True)

    async def review_user_registration(self, user_id: int, status: str, reviewed_by: int,
                                       rejection_reason: str = None):
        if status not in {"approved", "rejected"}:
            raise ValueError("Unsupported registration status")
        return await self.execute("""
            UPDATE users SET registration_status=$2, reviewed_by=$3, reviewed_at=NOW(), rejection_reason=$4
            WHERE user_id=$1 AND registration_status='pending' RETURNING *
        """, user_id, status, reviewed_by, rejection_reason, fetchrow=True)

    async def get_pending_users(self):
        return await self.execute(
            "SELECT * FROM users WHERE registration_status='pending' ORDER BY user_id", fetch=True
        )

    async def update_user(self, user_id: int, **kwargs):
        if not kwargs:
            return None
        unknown = set(kwargs) - self.USER_UPDATE_FIELDS
        if unknown:
            raise ValueError(f"Unsupported user fields: {', '.join(sorted(unknown))}")
        set_clause = ', '.join([f"{key} = ${i + 2}" for i, key in enumerate(kwargs.keys())])
        values = list(kwargs.values())
        sql = f"UPDATE users SET {set_clause} WHERE user_id=$1 RETURNING *;"
        return await self.execute(sql, user_id, *values, fetchrow=True)

    async def delete_user(self, user_id: int):
        sql = "DELETE FROM users WHERE user_id = $1"
        return await self.execute(sql, user_id, execute=True)

    async def get_all_users(self):
        sql = "SELECT * FROM users WHERE registration_status='approved' ORDER BY full_name"
        return await self.execute(sql, fetch=True)

    async def count_approved_users(self, query: str = None):
        query = (query or "").strip()
        return await self.execute(
            """SELECT COUNT(*) FROM users
               WHERE registration_status='approved'
                 AND ($1='' OR full_name ILIKE '%' || $1 || '%'
                      OR COALESCE(user_name, '') ILIKE '%' || $1 || '%'
                      OR COALESCE(group_name, '') ILIKE '%' || $1 || '%'
                      OR user_id::text=$1)
            """,
            query, fetchval=True,
        )

    async def get_approved_users_page(self, limit: int = 15, offset: int = 0,
                                      query: str = None):
        query = (query or "").strip()
        return await self.execute(
            """SELECT * FROM users
               WHERE registration_status='approved'
                 AND ($1='' OR full_name ILIKE '%' || $1 || '%'
                      OR COALESCE(user_name, '') ILIKE '%' || $1 || '%'
                      OR COALESCE(group_name, '') ILIKE '%' || $1 || '%'
                      OR user_id::text=$1)
               ORDER BY full_name, user_id
               LIMIT $2 OFFSET $3
            """,
            query, limit, offset, fetch=True,
        )

    async def get_birthdays_for_date(self, celebration_date: date):
        return await self.execute(
            """SELECT user_id, full_name, birth_date FROM users
               WHERE registration_status='approved' AND NOT is_excluded
                 AND birth_date IS NOT NULL
                 AND EXTRACT(MONTH FROM birth_date)=EXTRACT(MONTH FROM $1::date)
                 AND EXTRACT(DAY FROM birth_date)=EXTRACT(DAY FROM $1::date)
               ORDER BY full_name""",
            celebration_date, fetch=True,
        )

    async def get_birthday_deliveries(self, celebration_date: date):
        return await self.execute(
            "SELECT user_id, group_id FROM birthday_announcements WHERE celebration_date=$1",
            celebration_date, fetch=True,
        )

    async def record_birthday_deliveries(self, user_ids, group_id: int,
                                         celebration_date: date, message_id: int):
        if not user_ids:
            return
        if self.pool is None:
            raise RuntimeError("Database pool is not initialized")
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                await connection.executemany(
                    """INSERT INTO birthday_announcements(user_id,group_id,celebration_date,message_id)
                       VALUES($1,$2,$3,$4) ON CONFLICT DO NOTHING""",
                    [(int(user_id), group_id, celebration_date, message_id) for user_id in user_ids],
                )

    async def search_users(self, query: str, limit: int = 10):
        sql = """
        SELECT * FROM users
        WHERE registration_status='approved'
          AND (full_name ILIKE '%' || $1 || '%' OR user_name ILIKE '%' || $1 || '%')
        ORDER BY full_name
        LIMIT $2;
        """
        return await self.execute(sql, query, limit, fetch=True)

    async def increment_penalty_count(self, user_id: int):
        sql = """
        UPDATE users SET penalty_count = penalty_count + 1
        WHERE user_id = $1
        RETURNING *;
        """
        return await self.execute(sql, user_id, fetchrow=True)

    async def set_excluded(self, user_id: int, is_excluded: bool = True):
        sql = "UPDATE users SET is_excluded=$2 WHERE user_id=$1 RETURNING *;"
        return await self.execute(sql, user_id, is_excluded, fetchrow=True)

    async def add_score_adjustment(self, user_id: int, amount: int, reason: str,
                                   actor_id: int, month: int, year: int):
        if not amount:
            raise ValueError("Score adjustment cannot be zero")
        reason = (reason or "").strip()
        if len(reason) < 3:
            raise ValueError("Score adjustment reason is too short")
        return await self.execute(
            """INSERT INTO score_adjustments(user_id,amount,reason,actor_id,month,year)
               SELECT user_id,$2,$3,$4,$5,$6 FROM users
               WHERE user_id=$1 AND registration_status='approved'
               RETURNING *""",
            user_id, amount, reason, actor_id, month, year, fetchrow=True,
        )

    async def get_recent_score_adjustments(self, user_id: int, limit: int = 5):
        return await self.execute(
            """SELECT * FROM score_adjustments WHERE user_id=$1
               ORDER BY created_at DESC, id DESC LIMIT $2""",
            user_id, limit, fetch=True,
        )

    # ----------------- GROUPS TABLE -----------------
    async def add_group(self, group_id: int, title: str = None):
        sql = """
        INSERT INTO groups (group_id, title) VALUES ($1, $2)
        ON CONFLICT (group_id) DO UPDATE SET title = EXCLUDED.title
        RETURNING *;
        """
        return await self.execute(sql, group_id, title, fetchrow=True)

    async def remove_group(self, group_id: int):
        sql = "DELETE FROM groups WHERE group_id = $1"
        return await self.execute(sql, group_id, execute=True)

    async def get_all_groups(self):
        sql = "SELECT * FROM groups ORDER BY added_at"
        return await self.execute(sql, fetch=True)

    # ----------------- EVENT MEDIA (media mas'ul yuklagan rasmlar) -----------------
    async def add_event_media(self, event_id: int, file_id: str, message_id: int, uploaded_by: int,
                               file_type: str = "photo"):
        sql = """
        INSERT INTO event_media (event_id, file_id, message_id, uploaded_by, file_type)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING *;
        """
        return await self.execute(sql, event_id, file_id, message_id, uploaded_by, file_type, fetchrow=True)

    async def get_event_media(self, event_id: int):
        sql = "SELECT * FROM event_media WHERE event_id=$1 ORDER BY uploaded_at"
        return await self.execute(sql, event_id, fetch=True)

    async def get_closed_events_missing_media(self, required_count: int):
        """
        Yopilgan, media mas'ul shaxs tayinlangan va (bazadagi umumiy sozlama bo'yicha)
        talab qilingan rasm soni hali to'liq yuklanmagan tadbirlarni qaytaradi.
        Agar media biriktirilmagan bo'lsa, bu funksiya ishlamaydi.
        """
        sql = """
        SELECT e.*, COALESCE((SELECT COUNT(*) FROM event_media em WHERE em.event_id = e.event_id), 0) AS uploaded_count
        FROM events e
        WHERE e.is_closed = TRUE
          AND e.media_responsible IS NOT NULL
          AND (SELECT COUNT(*) FROM event_media em WHERE em.event_id = e.event_id) < $1
        """
        return await self.execute(sql, required_count, fetch=True)

    # ----------------- EVENT ANNOUNCEMENTS -----------------
    async def add_announcement_message(self, event_id: int, group_id: int, message_id: int, kind: str = "announcement"):
        sql = """
        INSERT INTO event_announcements (event_id, group_id, message_id, kind)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (event_id, group_id, kind) DO UPDATE SET message_id = EXCLUDED.message_id
        RETURNING *;
        """
        return await self.execute(sql, event_id, group_id, message_id, kind, fetchrow=True)

    async def get_announcement_messages(self, event_id: int, kind: str = "announcement"):
        sql = "SELECT * FROM event_announcements WHERE event_id=$1 AND kind=$2"
        return await self.execute(sql, event_id, kind, fetch=True)

    async def get_events_missing_announcements(self):
        return await self.execute("""
            SELECT e.* FROM events e
            WHERE e.approval_status='approved' AND NOT e.is_closed
              AND EXISTS (
                  SELECT 1 FROM groups g
                  WHERE NOT EXISTS (
                      SELECT 1 FROM event_announcements a
                      WHERE a.event_id=e.event_id AND a.group_id=g.group_id AND a.kind='announcement'
                  )
              )
            ORDER BY e.date, e.event_id
        """, fetch=True)

    # ----------------- EVENTS TABLE -----------------
    async def add_event(self, event_id: int, event_name: str, description: str, date_: date,
                         location: str = None, time_: dtime = None, responsible_person: int = None,
                         score: int = None, media_responsible: int = None, participants_count: int = 0,
                         verification_method: str = "manual", penalty_score: int = 0, waitlist_count: int = 0,
                         direction_id: int = None, created_by: int = None, approval_status: str = "pending"):
        sql = """
        INSERT INTO events (event_id, event_name, description, date, location, time, responsible_person, score,
                             media_responsible, participants_count, verification_method, penalty_score,
                             waitlist_count, direction_id, created_by, approval_status)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
        RETURNING *;
        """
        return await self.execute(sql, event_id, event_name, description, date_,
                                   location, time_, responsible_person, score, media_responsible,
                                   participants_count, verification_method, penalty_score, waitlist_count,
                                   direction_id, created_by, approval_status, fetchrow=True)

    async def get_events_by_responsible(self, user_id: int):
        sql = """
        SELECT * FROM events
        WHERE (responsible_person = $1 OR media_responsible = $1) AND is_closed = FALSE
        ORDER BY date, time;
        """
        return await self.execute(sql, user_id, fetch=True)

    async def has_active_event_responsibility(self, user_id: int):
        return await self.execute("""
            SELECT EXISTS(
                SELECT 1 FROM events
                WHERE (responsible_person=$1 OR media_responsible=$1) AND is_closed=FALSE
            )
        """, user_id, fetchval=True)

    async def assign_media_responsible(self, event_id: int, user_id: int):
        sql = """
        UPDATE events
        SET media_responsible = $2
        WHERE event_id = $1
        RETURNING *;
        """
        return await self.execute(sql, event_id, user_id, fetchrow=True)

    async def get_event(self, event_id: int):
        sql = "SELECT * FROM events WHERE event_id = $1"
        return await self.execute(sql, event_id, fetchrow=True)

    async def get_events_by_month(self, month: int, year: int):
        sql = """
        SELECT *
        FROM events
        WHERE EXTRACT(MONTH FROM date) = $1
          AND EXTRACT(YEAR FROM date) = $2
        ORDER BY date;
        """
        return await self.execute(sql, month, year, fetch=True)

    async def update_event(self, event_id: int, **kwargs):
        if not kwargs:
            return None
        unknown = set(kwargs) - self.EVENT_UPDATE_FIELDS
        if unknown:
            raise ValueError(f"Unsupported event fields: {', '.join(sorted(unknown))}")
        set_clause = ', '.join([f"{key} = ${i + 2}" for i, key in enumerate(kwargs.keys())])
        values = list(kwargs.values())
        sql = f"UPDATE events SET {set_clause} WHERE event_id=$1 RETURNING *;"
        return await self.execute(sql, event_id, *values, fetchrow=True)

    async def delete_event(self, event_id: int):
        sql = "DELETE FROM events WHERE event_id = $1"
        return await self.execute(sql, event_id, execute=True)

    async def get_all_events(self):
        sql = "SELECT * FROM events ORDER BY date DESC"
        return await self.execute(sql, fetch=True)

    async def close_event(self, event_id: int):
        """
        Tadbirni yakunlaydi: ro'yxatdan o'tgan, lekin tasdiqlanmagan (pending/rejected)
        talabalarga jarima beradi, ularning statusini 'not_attended' qiladi.
        Qaytaradi: (event, penalized_user_rows)
        """
        if self.pool is None:
            raise RuntimeError("Database pool is not initialized")
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                event = await connection.fetchrow(
                    "SELECT * FROM events WHERE event_id=$1 FOR UPDATE", event_id
                )
                if not event or event["is_closed"]:
                    return event, []
                penalized = await connection.fetch(
                    """
                    SELECT eu.user_id, u.full_name
                    FROM event_users eu JOIN users u ON u.user_id = eu.user_id
                    WHERE eu.event_id=$1 AND eu.status IN ('pending', 'rejected')
                      AND eu.is_waitlist=FALSE
                    """, event_id
                )
                await connection.execute(
                    "UPDATE event_users SET status='not_attended' "
                    "WHERE event_id=$1 AND status IN ('pending','rejected') AND is_waitlist=FALSE", event_id
                )
                await connection.execute(
                    "UPDATE event_users SET status='withdrawn' "
                    "WHERE event_id=$1 AND status IN ('pending','rejected') AND is_waitlist=TRUE", event_id
                )
                await connection.execute(
                    "UPDATE events SET is_closed=TRUE, closed_at=NOW() WHERE event_id=$1", event_id
                )
                penalized_ids = [row["user_id"] for row in penalized]
                if penalized_ids:
                    await connection.execute(
                        "UPDATE users SET penalty_count=penalty_count+1 WHERE user_id=ANY($1::bigint[])",
                        penalized_ids,
                    )
                return await connection.fetchrow("SELECT * FROM events WHERE event_id=$1", event_id), penalized

    # ----------------- EVENT_USERS TABLE -----------------
    async def get_active_participants_count(self, event_id: int, is_waitlist: bool = False):
        sql = """
        SELECT COUNT(*) FROM event_users
        WHERE event_id=$1 AND is_waitlist=$2 AND status != 'withdrawn'
        """
        return await self.execute(sql, event_id, is_waitlist, fetchval=True)

    async def register_user_to_event(self, event_id: int, user_id: int):
        """
        Talabani tadbirga yozadi: asosiy ro'yxat to'lmagan bo'lsa asosiy, aks holda zaxiraga.
        Zaxira ham to'lgan bo'lsa yozilmaydi.
        Qaytaradi: (event_user_row, slot) — slot: 'main' | 'waitlist' | 'full'
        """
        if self.pool is None:
            raise RuntimeError("Database pool is not initialized")
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                event = await connection.fetchrow(
                    "SELECT * FROM events WHERE event_id=$1 FOR UPDATE", event_id
                )
                if not event or event["is_closed"] or event["approval_status"] != "approved":
                    return None, "full"
                user = await connection.fetchrow(
                    """SELECT user_id FROM users
                       WHERE user_id=$1 AND registration_status='approved' AND NOT is_excluded
                       FOR SHARE""",
                    user_id,
                )
                if not user:
                    return None, "forbidden"
                existing = await connection.fetchrow(
                    "SELECT * FROM event_users WHERE event_id=$1 AND user_id=$2 FOR UPDATE",
                    event_id, user_id
                )
                if existing and existing["status"] != "withdrawn":
                    return existing, "waitlist" if existing["is_waitlist"] else "main"
                main_count = await connection.fetchval(
                    "SELECT COUNT(*) FROM event_users WHERE event_id=$1 AND is_waitlist=FALSE AND status!='withdrawn'",
                    event_id
                )
                is_waitlist = main_count >= event["participants_count"]
                if is_waitlist:
                    waitlist_count = await connection.fetchval(
                        "SELECT COUNT(*) FROM event_users WHERE event_id=$1 AND is_waitlist=TRUE AND status!='withdrawn'",
                        event_id
                    )
                    if waitlist_count >= event["waitlist_count"]:
                        return None, "full"
                row = await connection.fetchrow(
                    """INSERT INTO event_users (event_id,user_id,status,is_waitlist,joined_at)
                       VALUES ($1,$2,'pending',$3,NOW())
                       ON CONFLICT (event_id,user_id) DO UPDATE SET
                         status='pending', is_waitlist=EXCLUDED.is_waitlist, joined_at=NOW()
                       RETURNING *""", event_id, user_id, is_waitlist
                )
                return row, "waitlist" if is_waitlist else "main"

    async def withdraw_from_event(self, event_id: int, user_id: int):
        """
        Talaba tadbirdan voz kechadi. Agar u asosiy ro'yxatda bo'lsa, navbatdagi
        zaxiradagi birinchi kishi avtomatik asosiy ro'yxatga ko'tariladi.
        Qaytaradi: promoted_user_row (yoki None)
        """
        if self.pool is None:
            raise RuntimeError("Database pool is not initialized")
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                event = await connection.fetchrow(
                    "SELECT * FROM events WHERE event_id=$1 FOR UPDATE", event_id
                )
                if not event or event["is_closed"] or event["approval_status"] != "approved":
                    return None
                event_user = await connection.fetchrow(
                    "SELECT * FROM event_users WHERE event_id=$1 AND user_id=$2 FOR UPDATE",
                    event_id, user_id,
                )
                if not event_user or event_user["status"] != "pending":
                    return None
                changed = await connection.fetchrow(
                    """UPDATE event_users SET status='withdrawn'
                       WHERE event_id=$1 AND user_id=$2 AND status='pending'
                       RETURNING *""",
                    event_id, user_id,
                )
                if not changed or changed["is_waitlist"]:
                    return None
                return await connection.fetchrow(
                    """WITH next_user AS (
                           SELECT user_id FROM event_users
                           WHERE event_id=$1 AND is_waitlist=TRUE AND status='pending'
                           ORDER BY joined_at, user_id
                           LIMIT 1 FOR UPDATE SKIP LOCKED
                       )
                       UPDATE event_users eu SET is_waitlist=FALSE
                       FROM next_user
                       WHERE eu.event_id=$1 AND eu.user_id=next_user.user_id
                       RETURNING eu.*""",
                    event_id,
                )

    async def get_event_participants(self, event_id: int):
        sql = """
        SELECT u.user_id, u.full_name, eu.status, eu.is_waitlist
        FROM event_users eu
        JOIN users u ON u.user_id = eu.user_id
        WHERE eu.event_id = $1 AND eu.status != 'withdrawn'
        ORDER BY eu.is_waitlist, eu.joined_at;
        """
        rows = await self.execute(sql, event_id, fetch=True)
        main_list = [r for r in rows if not r["is_waitlist"]]
        waitlist = [r for r in rows if r["is_waitlist"]]
        return main_list, waitlist

    async def get_event_user(self, event_id: int, user_id: int):
        sql = "SELECT * FROM event_users WHERE event_id=$1 AND user_id=$2"
        return await self.execute(sql, event_id, user_id, fetchrow=True)

    async def confirm_attendance_manual(self, event_id: int, user_id: int, confirmed_by: int):
        sql = """
        WITH locked_event AS (
            SELECT 1 FROM events WHERE event_id=$1 AND NOT is_closed AND approval_status='approved' FOR UPDATE
        )
        UPDATE event_users
        SET status='confirmed', confirmed_by=$3, confirmed_at=NOW()
        WHERE event_id=$1 AND user_id=$2 AND status IN ('pending', 'rejected')
          AND is_waitlist=FALSE AND EXISTS (SELECT 1 FROM locked_event)
        RETURNING *;
        """
        return await self.execute(sql, event_id, user_id, confirmed_by, fetchrow=True)

    async def unconfirm_attendance_manual(self, event_id: int, user_id: int):
        sql = """
        WITH locked_event AS (
            SELECT 1 FROM events WHERE event_id=$1 AND NOT is_closed AND approval_status='approved' FOR UPDATE
        )
        UPDATE event_users
        SET status='pending', confirmed_by=NULL, confirmed_at=NULL
        WHERE event_id=$1 AND user_id=$2 AND status='confirmed'
          AND is_waitlist=FALSE AND EXISTS (SELECT 1 FROM locked_event)
        RETURNING *;
        """
        return await self.execute(sql, event_id, user_id, fetchrow=True)

    async def submit_attendance_proof(self, event_id: int, user_id: int, proof_photo_file_id: str,
                                       proof_photo_message_id: int, confirmer_id: int, request_message_id: int):
        sql = """
        WITH locked_event AS (
            SELECT 1 FROM events
            WHERE event_id=$1 AND NOT is_closed AND approval_status='approved'
              AND verification_method='photo'
            FOR UPDATE
        )
        UPDATE event_users
        SET proof_photo_file_id=$3, proof_photo_message_id=$4, confirmer_id=$5,
            request_message_id=$6, last_reminder_at=NOW(), status='pending'
        WHERE event_id=$1 AND user_id=$2 AND status IN ('pending', 'rejected')
          AND (status='rejected' OR proof_photo_file_id IS NULL)
          AND is_waitlist=FALSE AND EXISTS (SELECT 1 FROM locked_event)
        RETURNING *;
        """
        return await self.execute(sql, event_id, user_id, proof_photo_file_id, proof_photo_message_id,
                                   confirmer_id, request_message_id, fetchrow=True)

    async def confirm_attendance_photo(self, event_id: int, user_id: int, confirmed_by: int):
        sql = """
        WITH locked_event AS (
            SELECT 1 FROM events WHERE event_id=$1 AND NOT is_closed AND approval_status='approved' FOR UPDATE
        )
        UPDATE event_users
        SET status='confirmed', confirmed_by=$3, confirmed_at=NOW()
        WHERE event_id=$1 AND user_id=$2 AND status='pending' AND is_waitlist=FALSE
          AND EXISTS (SELECT 1 FROM locked_event)
        RETURNING *;
        """
        return await self.execute(sql, event_id, user_id, confirmed_by, fetchrow=True)

    async def reject_attendance_photo(self, event_id: int, user_id: int):
        sql = """
        WITH locked_event AS (
            SELECT 1 FROM events WHERE event_id=$1 AND NOT is_closed AND approval_status='approved' FOR UPDATE
        )
        UPDATE event_users
        SET status='rejected'
        WHERE event_id=$1 AND user_id=$2 AND status='pending' AND is_waitlist=FALSE
          AND EXISTS (SELECT 1 FROM locked_event)
        RETURNING *;
        """
        return await self.execute(sql, event_id, user_id, fetchrow=True)

    async def get_pending_verifications_for_reminder(self, delay_minutes: int):
        sql = """
        SELECT eu.event_id, eu.user_id, eu.proof_photo_file_id, eu.confirmer_id
        FROM event_users eu
        JOIN events e ON e.event_id = eu.event_id
        WHERE eu.status = 'pending'
          AND eu.confirmer_id IS NOT NULL
          AND eu.proof_photo_file_id IS NOT NULL
          AND e.is_closed = FALSE
          AND COALESCE(eu.last_reminder_at, TIMESTAMP 'epoch') <= NOW() - ($1 || ' minutes')::interval
        """
        return await self.execute(sql, str(delay_minutes), fetch=True)

    async def update_verification_reminder(self, event_id: int, user_id: int, request_message_id: int):
        sql = """
        UPDATE event_users
        SET request_message_id=$3, last_reminder_at=NOW()
        WHERE event_id=$1 AND user_id=$2
        """
        return await self.execute(sql, event_id, user_id, request_message_id, execute=True)

    async def get_event_full_info(self, event_id: int):
        event_sql = "SELECT * FROM events WHERE event_id = $1"
        event = await self.execute(event_sql, event_id, fetchrow=True)

        if not event:
            return None

        registered_sql = """
        SELECT u.user_id, u.full_name, u.phone_number, eu.status, eu.is_waitlist
        FROM event_users eu
        JOIN users u ON eu.user_id = u.user_id
        WHERE eu.event_id = $1 AND eu.status != 'withdrawn'
        ORDER BY u.full_name;
        """
        registered = await self.execute(registered_sql, event_id, fetch=True)

        attended = [r for r in registered if r["status"] == "confirmed"]
        not_attended = [r for r in registered if r["status"] in ("not_attended", "rejected")]
        pending = [r for r in registered if r["status"] == "pending"]

        return {
            "event": event,
            "registered": registered,
            "attended": attended,
            "not_attended": not_attended,
            "pending": pending,
        }

    async def remove_user_from_event(self, event_id: int, user_id: int):
        sql = "DELETE FROM event_users WHERE event_id=$1 AND user_id=$2"
        return await self.execute(sql, event_id, user_id, execute=True)

    async def get_user_events_by_date(self, user_id: int, start_date: date, end_date: date):
        sql = """
        SELECT e.*
        FROM events e
        JOIN event_users eu ON e.event_id = eu.event_id
        WHERE eu.user_id=$1 AND e.date BETWEEN $2 AND $3
        ORDER BY e.date;
        """
        return await self.execute(sql, user_id, start_date, end_date, fetch=True)

    async def get_user_upcoming_events(self, user_id: int):
        sql = """
        SELECT e.*, eu.status, eu.is_waitlist
        FROM events e
        JOIN event_users eu ON e.event_id = eu.event_id
        WHERE eu.user_id = $1 AND e.is_closed = FALSE AND eu.status != 'withdrawn'
        ORDER BY e.date, e.time;
        """
        return await self.execute(sql, user_id, fetch=True)

    async def get_user_confirmed_events(self, user_id: int):
        sql = """
        SELECT e.*
        FROM events e
        JOIN event_users eu ON e.event_id = eu.event_id
        WHERE eu.user_id = $1 AND eu.status = 'confirmed'
        ORDER BY e.date DESC;
        """
        return await self.execute(sql, user_id, fetch=True)

    async def get_upcoming_events_open_for_registration(self):
        sql = "SELECT * FROM events WHERE is_closed = FALSE AND approval_status = 'approved' ORDER BY date, time;"
        return await self.execute(sql, fetch=True)

    # ----------------- REYTING / LEADERBOARD -----------------
    async def get_monthly_leaderboard(self, month: int, year: int):
        """
        Shu oyda o'tgan tadbirlar bo'yicha har bir talabaning yig'indi balini qaytaradi
        (confirmed = +score, not_attended/rejected = -penalty_score).
        """
        sql = """
        WITH event_points AS (
            SELECT eu.user_id, COALESCE(SUM(
                CASE
                    WHEN eu.status = 'confirmed' THEN e.score
                    WHEN eu.status = 'not_attended' THEN -e.penalty_score
                    ELSE 0
                END
            ), 0) AS points
            FROM event_users eu
            JOIN events e ON e.event_id = eu.event_id
            WHERE EXTRACT(MONTH FROM e.date) = $1 AND EXTRACT(YEAR FROM e.date) = $2
            GROUP BY eu.user_id
        ), adjustment_points AS (
            SELECT user_id, COALESCE(SUM(amount), 0) AS points
            FROM score_adjustments
            WHERE month=$1 AND year=$2
            GROUP BY user_id
        ), participant_ids AS (
            SELECT user_id FROM event_points
            UNION
            SELECT user_id FROM adjustment_points
        )
        SELECT u.user_id, u.full_name, u.user_name,
               COALESCE(ep.points, 0) + COALESCE(ap.points, 0) AS total_score
        FROM participant_ids p
        JOIN users u ON u.user_id=p.user_id
        LEFT JOIN event_points ep ON ep.user_id=p.user_id
        LEFT JOIN adjustment_points ap ON ap.user_id=p.user_id
        WHERE u.registration_status='approved'
        ORDER BY total_score DESC, u.full_name;
        """
        return await self.execute(sql, month, year, fetch=True)

    async def get_user_monthly_score(self, user_id: int, month: int, year: int):
        sql = """
        SELECT
            COALESCE((
                SELECT SUM(CASE
                    WHEN eu.status='confirmed' THEN e.score
                    WHEN eu.status='not_attended' THEN -e.penalty_score
                    ELSE 0
                END)
                FROM event_users eu JOIN events e ON e.event_id=eu.event_id
                WHERE eu.user_id=$1
                  AND EXTRACT(MONTH FROM e.date)=$2
                  AND EXTRACT(YEAR FROM e.date)=$3
            ), 0)
            + COALESCE((
                SELECT SUM(amount) FROM score_adjustments
                WHERE user_id=$1 AND month=$2 AND year=$3
            ), 0) AS total_score;
        """
        return await self.execute(sql, user_id, month, year, fetchval=True)

    async def add_monthly_winner(self, user_id: int, month: int, year: int, score, rank: int):
        sql = """
        INSERT INTO monthly_winners (user_id, month, year, score, rank)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (user_id, month, year) DO UPDATE SET score = EXCLUDED.score, rank = EXCLUDED.rank
        RETURNING *;
        """
        return await self.execute(sql, user_id, month, year, score, rank, fetchrow=True)

    async def save_monthly_winners_once(self, month: int, year: int, winners, once_per_student: bool):
        """Atomically finalize one month's winners and reject stale/concurrent publication."""
        if self.pool is None:
            raise RuntimeError("Database pool is not initialized")
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute("SELECT pg_advisory_xact_lock($1)", year * 100 + month)
                if await connection.fetchval(
                        "SELECT EXISTS(SELECT 1 FROM monthly_winners WHERE month=$1 AND year=$2)",
                        month, year):
                    return None
                user_ids = [int(w["user_id"]) for w in winners]
                if once_per_student and await connection.fetchval(
                        "SELECT EXISTS(SELECT 1 FROM monthly_winners WHERE user_id=ANY($1::bigint[]))",
                        user_ids):
                    return None
                rows = []
                for rank, winner in enumerate(winners, 1):
                    rows.append(await connection.fetchrow(
                        """INSERT INTO monthly_winners(user_id,month,year,score,rank)
                           VALUES($1,$2,$3,$4,$5) RETURNING *""",
                        int(winner["user_id"]), month, year, winner["total_score"], rank,
                    ))
                return rows

    async def get_all_time_winner_ids(self):
        sql = "SELECT DISTINCT user_id FROM monthly_winners"
        rows = await self.execute(sql, fetch=True)
        return {r["user_id"] for r in rows}

    async def get_monthly_winners(self, month: int, year: int):
        sql = """
        SELECT mw.*, u.full_name
        FROM monthly_winners mw
        JOIN users u ON u.user_id = mw.user_id
        WHERE mw.month=$1 AND mw.year=$2
        ORDER BY mw.rank;
        """
        return await self.execute(sql, month, year, fetch=True)

    async def delete_monthly_winners(self, month: int, year: int):
        sql = "DELETE FROM monthly_winners WHERE month=$1 AND year=$2"
        return await self.execute(sql, month, year, execute=True)

    async def add_winner_message(self, month: int, year: int, group_id: int, message_id: int):
        sql = """
        INSERT INTO monthly_winner_messages (month, year, group_id, message_id)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (month, year, group_id) DO UPDATE SET message_id = EXCLUDED.message_id
        RETURNING *;
        """
        return await self.execute(sql, month, year, group_id, message_id, fetchrow=True)

    async def get_winner_messages(self, month: int, year: int):
        sql = "SELECT * FROM monthly_winner_messages WHERE month=$1 AND year=$2"
        return await self.execute(sql, month, year, fetch=True)

    async def delete_winner_messages(self, month: int, year: int):
        sql = "DELETE FROM monthly_winner_messages WHERE month=$1 AND year=$2"
        return await self.execute(sql, month, year, execute=True)
