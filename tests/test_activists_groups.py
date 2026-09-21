import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.types import Chat, Message, User

from handlers.users.ADMIN.activists import PAGE_SIZE, _list_keyboard
from middlewares.private_chat import PrivateChatMiddleware
from utils.set_bot_commands import set_default_commands


def make_message(chat_type: str):
    return Message(
        message_id=1,
        date=datetime.now(timezone.utc),
        chat=Chat(id=-1001 if chat_type != "private" else 10, type=chat_type),
        from_user=User(id=10, is_bot=False, first_name="Test"),
        text="/start",
    )


class ActivistsAndGroupsTests(unittest.IsolatedAsyncioTestCase):
    async def test_group_messages_are_silently_ignored(self):
        handler = AsyncMock(return_value="handled")
        result = await PrivateChatMiddleware()(handler, make_message("supergroup"), {})
        self.assertIsNone(result)
        handler.assert_not_awaited()

    async def test_private_messages_continue_to_handlers(self):
        handler = AsyncMock(return_value="handled")
        result = await PrivateChatMiddleware()(handler, make_message("private"), {})
        self.assertEqual(result, "handled")
        handler.assert_awaited_once()

    def test_activists_page_contains_fifteen_students(self):
        users = [
            {"user_id": index, "user_name": f"talaba{index}",
             "full_name": f"Talaba {index}", "group_name": "IRB"}
            for index in range(1, PAGE_SIZE + 1)
        ]
        markup = _list_keyboard(users, page=0, total=31)
        callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
        self.assertEqual(sum(value.startswith("act:u:") for value in callbacks), PAGE_SIZE)
        self.assertIn("act:p:1", callbacks)
        self.assertIn("act:search", callbacks)

    async def test_commands_are_scoped_to_private_chats(self):
        bot = SimpleNamespace(
            delete_my_commands=AsyncMock(),
            set_my_commands=AsyncMock(),
        )
        await set_default_commands(bot)
        self.assertEqual(bot.delete_my_commands.await_count, 3)
        scope = bot.set_my_commands.await_args.kwargs["scope"]
        self.assertEqual(scope.type, "all_private_chats")


if __name__ == "__main__":
    unittest.main()
