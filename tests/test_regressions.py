import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

from utils.announcements import build_announcement_text, send_event_announcement
from utils.db_api.SQL import Database
from utils.misc.funcsion import is_member_of_any_group
from utils.spreadsheets import safe_excel_value
from utils.scheduler import _birthday_job, _birthday_message_chunks
from handlers.users.ADMIN.export import HEADERS


class AnnouncementDatabase:
    async def get_event_participants(self, event_id):
        people = [{"full_name": f"<User {index}>"} for index in range(1000)]
        return people, people


class RegressionTests(unittest.IsolatedAsyncioTestCase):
    def test_excel_export_contains_username_column(self):
        self.assertIn("Username", HEADERS)

    def test_excel_formula_prefixes_are_neutralized(self):
        for value in ("=SUM(A1:A2)", "+cmd", "-1+2", "@formula"):
            self.assertEqual(safe_excel_value(value), "'" + value)
        self.assertEqual(safe_excel_value("ordinary text"), "ordinary text")
        self.assertIsNone(safe_excel_value(None))

    async def test_announcement_is_escaped_and_below_telegram_limit(self):
        event = {
            "event_id": 7,
            "event_name": "<b>unsafe</b>",
            "description": "<script>alert(1)</script>",
            "date": "2026-09-13",
            "time": "12:00",
            "participants_count": 1000,
            "waitlist_count": 1000,
            "score": 5,
            "location": "text:<Hall>",
        }
        text = await build_announcement_text(AnnouncementDatabase(), event, "safe_bot")
        self.assertLessEqual(len(text), 4096)
        self.assertIn("&lt;b&gt;unsafe&lt;/b&gt;", text)
        self.assertIn("&lt;Hall&gt;", text)
        self.assertNotIn("<script>", text)

    async def test_approved_event_with_no_groups_returns_zero_delivery(self):
        db = SimpleNamespace(get_all_groups=AsyncMock(return_value=[]))
        result = await send_event_announcement(None, db, {"approval_status": "approved"})
        self.assertEqual(result, (0, 0))

    async def test_restricted_but_current_member_is_accepted(self):
        bot = SimpleNamespace(get_chat_member=AsyncMock(return_value=SimpleNamespace(
            status="restricted", is_member=True,
        )))
        db = SimpleNamespace(get_all_groups=AsyncMock(return_value=[{"group_id": -1001}]))
        self.assertTrue(await is_member_of_any_group(bot, db, 123))

    async def test_duplicate_pending_photo_is_rejected_atomically(self):
        db = Database()
        db.execute = AsyncMock(return_value=None)
        await db.submit_attendance_proof(1, 2, "file", 3, 4, None)
        query = db.execute.await_args.args[0]
        self.assertIn("proof_photo_file_id IS NULL", query)
        self.assertIn("verification_method='photo'", query)
        self.assertIn("is_waitlist=FALSE", query)

    async def test_manual_score_adjustment_requires_reason_and_is_audited(self):
        db = Database()
        db.execute = AsyncMock(return_value={"id": 1})
        await db.add_score_adjustment(12, -5, "Sababsiz kelmadi", 99, 9, 2026)
        args = db.execute.await_args.args
        self.assertIn("score_adjustments", args[0])
        self.assertEqual(args[1:], (12, -5, "Sababsiz kelmadi", 99, 9, 2026))
        with self.assertRaises(ValueError):
            await db.add_score_adjustment(12, 5, "x", 99, 9, 2026)

    async def test_monthly_score_includes_manual_adjustments(self):
        db = Database()
        db.execute = AsyncMock(return_value=7)
        self.assertEqual(await db.get_user_monthly_score(12, 9, 2026), 7)
        self.assertIn("score_adjustments", db.execute.await_args.args[0])

    def test_birthday_messages_are_split_below_telegram_limit(self):
        users = [
            {"user_id": index, "full_name": "<Very long user name>" * 7}
            for index in range(1, 101)
        ]
        chunks = _birthday_message_chunks(users)
        self.assertGreater(len(chunks), 1)
        self.assertEqual(sum(len(user_ids) for _, user_ids in chunks), 100)
        self.assertTrue(all(len(text) <= 3800 for text, _ in chunks))
        self.assertTrue(all("&lt;Very long user name&gt;" in text for text, _ in chunks))

    async def test_birthday_job_sends_only_missing_group_deliveries(self):
        users = [
            {"user_id": 1, "full_name": "Ali <Test>", "birth_date": date(2005, 9, 13)},
            {"user_id": 2, "full_name": "Vali", "birth_date": date(2004, 9, 13)},
        ]
        db = SimpleNamespace(
            get_birthdays_for_date=AsyncMock(return_value=users),
            get_all_groups=AsyncMock(return_value=[{"group_id": -10}, {"group_id": -20}]),
            get_birthday_deliveries=AsyncMock(return_value=[{"user_id": 1, "group_id": -10}]),
            record_birthday_deliveries=AsyncMock(),
        )
        bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=77)))
        today = date(2026, 9, 13)
        await _birthday_job(bot, db, today)
        self.assertEqual(bot.send_message.await_count, 2)
        recorded = [call.args[0] for call in db.record_birthday_deliveries.await_args_list]
        self.assertIn([2], recorded)
        self.assertIn([1, 2], recorded)


if __name__ == "__main__":
    unittest.main()
