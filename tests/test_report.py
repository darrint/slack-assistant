import os
import shutil
import subprocess
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from slack_sdk.errors import SlackApiError

from slack_assistant import summarize
from slack_assistant.config import Config
from slack_assistant.slack_scan import (
    CHANNEL_TYPES,
    is_human,
    plain_text,
    select_channels,
)
from slack_assistant.__main__ import run

TZ = ZoneInfo("America/Indiana/Indianapolis")
DAY = datetime(2026, 10, 8, 21, 0, tzinfo=TZ)


def cfg(**overrides) -> Config:
    base = dict(
        slack_bot_token="xoxb-test",
        report_channel="Creport",
        database_url="postgresql://unused",
        llm_provider="xai",
        xai_api_key="test-key",
        xai_model="grok-4.6",
        claude_model=None,
        exclude_channels=frozenset(),
        tz="America/Indiana/Indianapolis",
    )
    base.update(overrides)
    return Config(**base)


class MemoryStore:
    def __init__(self):
        self.rows = {}

    def get_report(self, day):
        return self.rows.get(day)

    def save_report(self, day, kind, body, posted_at):
        self.rows[day] = (kind, body)

    def close(self):
        pass


class FakeSlack:
    def __init__(self, channels, messages=None, fail_join=None):
        self.channels = channels
        self.messages = messages or {}
        self.fail_join = set(fail_join or [])
        self.joined = []
        self.posted = []
        self.history_calls = []
        self.list_types = None

    def auth_test(self):
        return {"user_id": "UBOT"}

    def conversations_list(self, **kwargs):
        self.list_types = kwargs["types"]
        return {"channels": self.channels, "response_metadata": {"next_cursor": ""}}

    def conversations_join(self, channel):
        if channel in self.fail_join:
            raise SlackApiError("join failed", {"error": "restricted_action"})
        self.joined.append(channel)
        return {"ok": True}

    def conversations_history(self, **kwargs):
        self.history_calls.append(kwargs)
        return {
            "messages": self.messages.get(kwargs["channel"], []),
            "response_metadata": {"next_cursor": ""},
        }

    def users_list(self, **kwargs):
        return {
            "members": [
                {"id": "U1", "name": "ada", "profile": {"display_name": "Ada"}},
                {"id": "U2", "name": "bea", "profile": {"display_name": "Bea"}},
                {"id": "UBOT", "name": "bot", "profile": {"display_name": "447 bot"}},
            ],
            "response_metadata": {"next_cursor": ""},
        }

    def chat_postMessage(self, channel, text):
        self.posted.append((channel, text))


def channels():
    return [
        {"id": "Cpub", "name": "general", "is_private": False, "is_member": True},
        {"id": "Cjoin", "name": "shop", "is_private": False, "is_member": False},
        {"id": "Gpriv", "name": "mentors", "is_private": True, "is_member": True},
        {"id": "Gno", "name": "secret", "is_private": True, "is_member": False},
        {"id": "Creport", "name": "bot", "is_private": False, "is_member": True},
        {"id": "Dim", "name": "dm", "is_im": True, "is_member": True},
    ]


def human(ts, user="U1", text="fixed the intake", subtype=None):
    msg = {"ts": ts, "user": user, "text": text}
    if subtype:
        msg["subtype"] = subtype
    return msg


class SelectTests(unittest.TestCase):
    def test_private_uninvited_is_dropped_and_not_joined(self):
        read, join = select_channels(channels(), "Creport", frozenset())
        ids = {ch["id"] for ch in read}
        self.assertEqual(ids, {"Cpub", "Cjoin", "Gpriv"})
        self.assertEqual([ch["id"] for ch in join], ["Cjoin"])

    def test_exclude_and_report_channel(self):
        read, join = select_channels(channels(), "Creport", frozenset({"Cpub"}))
        self.assertNotIn("Cpub", {ch["id"] for ch in read})
        self.assertNotIn("Creport", {ch["id"] for ch in read})
        self.assertEqual(join[0]["id"], "Cjoin")

    def test_channel_types_are_not_dms(self):
        self.assertNotIn("im", CHANNEL_TYPES)
        self.assertNotIn("mpim", CHANNEL_TYPES)


class SummarizeTests(unittest.TestCase):
    def test_missing_xai_key_skips_the_model(self):
        def boom(cfg, prompt):
            raise AssertionError("model called")

        original = summarize.complete
        summarize.complete = boom
        try:
            kind, body = summarize.summarize(
                DAY.date(),
                [{"channel": "shop", "when": "19:00", "user": "Ada", "text": "fixed the intake"}],
                cfg(xai_api_key=None),
            )
        finally:
            summarize.complete = original
        self.assertEqual(kind, "summary")
        self.assertIn("No model configured.", body)
        self.assertIn("Ada: fixed the intake", body)

    def test_empty_does_not_call_model(self):
        def boom(cfg, prompt):
            raise AssertionError("model called")

        original = summarize.complete
        summarize.complete = boom
        try:
            kind, body = summarize.summarize(DAY.date(), [], cfg())
        finally:
            summarize.complete = original
        self.assertEqual(kind, "no_meeting")
        self.assertEqual(body, "No meeting information for 2026-10-08.")

    def test_token_becomes_no_meeting_line(self):
        kind, body = summarize.interpret(DAY.date(), "  NO_MEETING\n")
        self.assertEqual((kind, body), ("no_meeting", "No meeting information for 2026-10-08."))

    def test_summary_keeps_model_text_and_date(self):
        kind, body = summarize.interpret(DAY.date(), "Ada fixed the intake.")
        self.assertEqual(kind, "summary")
        self.assertEqual(body, "2026-10-08\nAda fixed the intake.")

    def test_blank_model_text_is_no_meeting(self):
        kind, body = summarize.interpret(DAY.date(), "  \n")
        self.assertEqual(kind, "no_meeting")


class RunTests(unittest.TestCase):
    def test_no_human_messages_dry_run_does_not_post_or_call_model(self):
        slack = FakeSlack(channels(), {"Cpub": [human("1", user="UBOT", text="joined")]})
        store = MemoryStore()
        called = []
        original = summarize.complete
        summarize.complete = lambda *args: called.append(args)
        try:
            code = run(cfg(), dry_run=True, now=DAY, client=slack, store=store)
        finally:
            summarize.complete = original
        self.assertEqual(code, 0)
        self.assertEqual(called, [])
        self.assertEqual(slack.posted, [])
        self.assertEqual(store.rows, {})
        self.assertEqual(slack.joined, ["Cjoin"])
        self.assertNotIn("Gno", {call["channel"] for call in slack.history_calls})
        self.assertNotIn("Creport", {call["channel"] for call in slack.history_calls})
        self.assertNotIn("Dim", {call["channel"] for call in slack.history_calls})
        self.assertNotIn("im", slack.list_types)

    def test_local_date_is_indianapolis_not_utc(self):
        utc = datetime(2026, 10, 9, 1, 0, tzinfo=timezone.utc)
        slack = FakeSlack(channels())
        printed = []
        real_print = __builtins__["print"] if isinstance(__builtins__, dict) else __builtins__.print

        def capture(*args, **kwargs):
            printed.append(" ".join(str(arg) for arg in args))

        import builtins

        builtins.print = capture
        try:
            run(cfg(), dry_run=True, now=utc, client=slack, store=MemoryStore())
        finally:
            builtins.print = real_print
        self.assertIn("No meeting information for 2026-10-08.", printed)
        midnight = datetime(2026, 10, 8, 0, 0, tzinfo=TZ).timestamp()
        self.assertTrue(slack.history_calls)
        self.assertEqual(float(slack.history_calls[0]["oldest"]), midnight)

    def test_summary_posts_once_then_skips_unless_forced(self):
        ts = f"{datetime(2026, 10, 8, 19, 0, tzinfo=TZ).timestamp():.6f}"
        slack = FakeSlack(
            channels(),
            {"Cpub": [human(ts, text="fixed the intake with <@U2>")]},
        )
        store = MemoryStore()
        prompts = []

        def fake(cfg, prompt):
            prompts.append(prompt)
            return "Ada and Bea fixed the intake."

        original = summarize.complete
        summarize.complete = fake
        try:
            self.assertEqual(run(cfg(), now=DAY, client=slack, store=store), 0)
            self.assertEqual(len(slack.posted), 1)
            self.assertEqual(slack.posted[0][0], "Creport")
            self.assertIn("Ada and Bea fixed the intake.", slack.posted[0][1])
            self.assertIn("fixed the intake with Bea", prompts[0])
            again = FakeSlack(channels(), {"Cpub": [human(ts)]})
            self.assertEqual(run(cfg(), now=DAY, client=again, store=store), 0)
            self.assertEqual(again.posted, [])
            self.assertEqual(again.history_calls, [])
            forced = FakeSlack(channels(), {"Cpub": [human(ts, text="rebuilt the shooter")]})
            self.assertEqual(run(cfg(), force=True, now=DAY, client=forced, store=store), 0)
            self.assertEqual(len(forced.posted), 1)
            self.assertEqual(store.rows[DAY.date()][0], "summary")
        finally:
            summarize.complete = original

    def test_dry_run_with_messages_prints_and_does_not_save(self):
        ts = f"{datetime(2026, 10, 8, 19, 0, tzinfo=TZ).timestamp():.6f}"
        slack = FakeSlack(channels(), {"Gpriv": [human(ts, text="logged the match")]})
        store = MemoryStore()
        original = summarize.complete
        summarize.complete = lambda cfg, prompt: "Logged the match."
        import builtins

        printed = []
        real_print = builtins.print
        builtins.print = lambda *args, **kwargs: printed.append(" ".join(map(str, args)))
        try:
            run(cfg(), dry_run=True, now=DAY, client=slack, store=store)
        finally:
            builtins.print = real_print
            summarize.complete = original
        self.assertEqual(slack.posted, [])
        self.assertEqual(store.rows, {})
        self.assertTrue(any("Logged the match." in line for line in printed))
        self.assertNotIn("Gno", self.joined_ids(slack))

    def test_failed_public_join_is_not_read(self):
        slack = FakeSlack(channels(), fail_join={"Cjoin"})
        slack.messages["Cjoin"] = [human("1", text="should not be read")]
        original = summarize.complete
        summarize.complete = lambda *args: (_ for _ in ()).throw(AssertionError("model"))
        try:
            run(cfg(), dry_run=True, now=DAY, client=slack, store=MemoryStore())
        finally:
            summarize.complete = original
        self.assertNotIn("Cjoin", {call["channel"] for call in slack.history_calls})

    def joined_ids(self, slack):
        return set(slack.joined)


class TextTests(unittest.TestCase):
    def test_mentions_and_links(self):
        names = {"U2": "Bea"}
        self.assertEqual(plain_text("with <@U2> see <http://x|notes>", names), "with Bea see notes")

    def test_join_subtype_is_not_human(self):
        self.assertFalse(is_human({"subtype": "channel_join", "user": "U1", "text": "joined"}, "UBOT"))
        self.assertFalse(is_human({"user": "UBOT", "text": "hello"}, "UBOT"))


def _initdb():
    for candidate in (
        shutil.which("initdb"),
        "/run/current-system/sw/bin/initdb",
    ):
        if candidate and Path(candidate).exists():
            return candidate
    return None


class PgTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        initdb = _initdb()
        if not initdb:
            raise unittest.SkipTest("initdb not installed")
        postgres = str(Path(initdb).with_name("postgres"))
        cls.tmp = tempfile.mkdtemp(prefix="slack-assistant-pg-")
        env = os.environ.copy()
        env["LC_ALL"] = "C"
        subprocess.check_call(
            [initdb, "-D", cls.tmp, "--username=slack_assistant", "--auth=trust", "--locale=C", "--encoding=UTF8"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        cls.log = open(Path(cls.tmp) / "pg.log", "w")
        cls.proc = subprocess.Popen(
            [postgres, "-D", cls.tmp, "-k", cls.tmp, "-p", "5432", "-c", "listen_addresses="],
            stdout=cls.log,
            stderr=cls.log,
        )
        cls.url = f"postgresql://slack_assistant@/postgres?host={cls.tmp}&port=5432"
        deadline = time.time() + 10
        last = None
        while time.time() < deadline:
            if cls.proc.poll() is not None:
                break
            try:
                import psycopg

                psycopg.connect(cls.url, connect_timeout=1).close()
                return
            except Exception as exc:
                last = exc
                time.sleep(0.1)
        cls.tearDownClass()
        raise RuntimeError(f"postgres did not start: {last}")

    @classmethod
    def tearDownClass(cls):
        proc = getattr(cls, "proc", None)
        if proc and proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=10)
        log = getattr(cls, "log", None)
        if log:
            log.close()
        tmp = getattr(cls, "tmp", None)
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)

    def setUp(self):
        from slack_assistant.store import PgStore

        store = PgStore(self.url)
        with store.conn.cursor() as cur:
            cur.execute("delete from reports")
        store.conn.commit()
        store.close()

    def test_save_get_and_replace(self):
        from slack_assistant.store import PgStore

        store = PgStore(self.url)
        try:
            self.assertIsNone(store.get_report(DAY.date()))
            store.save_report(DAY.date(), "no_meeting", "No meeting information for 2026-10-08.", DAY)
            self.assertEqual(
                store.get_report(DAY.date()),
                ("no_meeting", "No meeting information for 2026-10-08."),
            )
            store.save_report(DAY.date(), "summary", "2026-10-08\nAda fixed the intake.", DAY)
            self.assertEqual(store.get_report(DAY.date())[0], "summary")
        finally:
            store.close()

    def test_run_does_not_double_post(self):
        from slack_assistant.store import PgStore

        ts = f"{datetime(2026, 10, 8, 19, 0, tzinfo=TZ).timestamp():.6f}"
        store = PgStore(self.url)
        def fake(cfg, prompt):
            return "again" if "again" in prompt else "Ada fixed the intake."

        original = summarize.complete
        summarize.complete = fake
        try:
            slack = FakeSlack(channels(), {"Cpub": [human(ts)]})
            run(cfg(database_url=self.url), now=DAY, client=slack, store=store)
            again = FakeSlack(channels(), {"Cpub": [human(ts)]})
            run(cfg(database_url=self.url), now=DAY, client=again, store=store)
            self.assertEqual(len(slack.posted), 1)
            self.assertEqual(again.posted, [])
            forced = FakeSlack(channels(), {"Cpub": [human(ts, text="again")]})
            run(cfg(database_url=self.url), force=True, now=DAY, client=forced, store=store)
            self.assertEqual(len(forced.posted), 1)
            self.assertIn("again", store.get_report(DAY.date())[1])
        finally:
            summarize.complete = original
            store.close()


class ConfigTests(unittest.TestCase):
    def test_missing_env_exits_before_work(self):
        from slack_assistant.config import load

        env = os.environ.copy()
        for key in (
            "SLACK_BOT_TOKEN",
            "SLACK_REPORT_CHANNEL",
            "DATABASE_URL",
            "XAI_API_KEY",
            "LLM_PROVIDER",
        ):
            os.environ.pop(key, None)
        os.environ["LLM_PROVIDER"] = "xai"
        try:
            with self.assertRaises(SystemExit) as raised:
                load()
            self.assertIn("SLACK_BOT_TOKEN", str(raised.exception))
        finally:
            os.environ.clear()
            os.environ.update(env)


if __name__ == "__main__":
    unittest.main()
