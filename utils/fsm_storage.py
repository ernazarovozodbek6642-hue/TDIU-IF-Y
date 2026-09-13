import json

from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey


class PostgresStorage(BaseStorage):
    """Durable FSM storage backed by the bot's existing PostgreSQL pool."""

    def __init__(self, database):
        self.db = database

    @staticmethod
    def _key(key: StorageKey):
        return key.bot_id, key.chat_id, key.user_id, key.destiny

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        value = state.state if hasattr(state, "state") else state
        await self.db.execute(
            """INSERT INTO fsm_storage(bot_id,chat_id,user_id,destiny,state,data,updated_at)
               VALUES($1,$2,$3,$4,$5,'{}'::jsonb,NOW())
               ON CONFLICT(bot_id,chat_id,user_id,destiny)
               DO UPDATE SET state=EXCLUDED.state, updated_at=NOW()""",
            *self._key(key), value, execute=True,
        )

    async def get_state(self, key: StorageKey) -> str | None:
        return await self.db.execute(
            "SELECT state FROM fsm_storage WHERE bot_id=$1 AND chat_id=$2 AND user_id=$3 AND destiny=$4",
            *self._key(key), fetchval=True,
        )

    async def set_data(self, key: StorageKey, data: dict) -> None:
        await self.db.execute(
            """INSERT INTO fsm_storage(bot_id,chat_id,user_id,destiny,state,data,updated_at)
               VALUES($1,$2,$3,$4,NULL,$5::jsonb,NOW())
               ON CONFLICT(bot_id,chat_id,user_id,destiny)
               DO UPDATE SET data=EXCLUDED.data, updated_at=NOW()""",
            *self._key(key), json.dumps(data, ensure_ascii=False), execute=True,
        )

    async def get_data(self, key: StorageKey) -> dict:
        value = await self.db.execute(
            "SELECT data FROM fsm_storage WHERE bot_id=$1 AND chat_id=$2 AND user_id=$3 AND destiny=$4",
            *self._key(key), fetchval=True,
        )
        if not value:
            return {}
        return json.loads(value) if isinstance(value, str) else dict(value)

    async def update_data(self, key: StorageKey, data: dict) -> dict:
        if self.db.pool is None:
            raise RuntimeError("Database pool is not initialized")
        async with self.db.pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """INSERT INTO fsm_storage(bot_id,chat_id,user_id,destiny,state,data,updated_at)
                       VALUES($1,$2,$3,$4,NULL,'{}'::jsonb,NOW())
                       ON CONFLICT(bot_id,chat_id,user_id,destiny) DO NOTHING""",
                    *self._key(key),
                )
                current = await connection.fetchval(
                    """SELECT data FROM fsm_storage
                       WHERE bot_id=$1 AND chat_id=$2 AND user_id=$3 AND destiny=$4 FOR UPDATE""",
                    *self._key(key),
                )
                current = json.loads(current) if isinstance(current, str) else dict(current or {})
                current.update(data)
                await connection.execute(
                    """UPDATE fsm_storage SET data=$5::jsonb, updated_at=NOW()
                       WHERE bot_id=$1 AND chat_id=$2 AND user_id=$3 AND destiny=$4""",
                    *self._key(key), json.dumps(current, ensure_ascii=False),
                )
                return current

    async def close(self) -> None:
        return None
