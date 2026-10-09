import os
import unittest

from slack_assistant.config import load_slack
from slack_assistant.pong import pending
from slack_assistant.slack_scan import find_channel


class ChannelTests(unittest.TestCase):
    def test_name_or_id(self):
        channels = [
            {"id": "C123", "name": "bot-channel"},
            {"id": "C999", "name": "general"},
        ]
        self.assertEqual(find_channel(channels, "#bot-channel")["id"], "C123")
        self.assertEqual(find_channel(channels, "bot-channel")["id"], "C123")
        self.assertEqual(find_channel(channels, "C999")["id"], "C999")
        self.assertIsNone(find_channel(channels, "#missing"))


class PongTests(unittest.TestCase):
    def test_replies_only_to_new_human_messages(self):
        messages = [
            {"ts": "1", "user": "U1", "text": "old"},
            {"ts": "3", "user": "UBOT", "text": "pong"},
            {"ts": "4", "user": "U1", "text": "ping", "bot_id": "B1"},
            {"ts": "2", "user": "U1", "text": "ping"},
            {"ts": "5", "subtype": "channel_join", "user": "U1", "text": "joined"},
        ]
        got = pending(messages, "UBOT", 1.5)
        self.assertEqual([msg["ts"] for msg in got], ["2"])

    def test_slack_env_does_not_need_a_model(self):
        env = os.environ.copy()
        try:
            os.environ["SLACK_BOT_TOKEN"] = "xoxb-test"
            os.environ["SLACK_REPORT_CHANNEL"] = "C1"
            os.environ.pop("XAI_API_KEY", None)
            os.environ.pop("LLM_PROVIDER", None)
            self.assertEqual(load_slack(), ("xoxb-test", "C1"))
        finally:
            os.environ.clear()
            os.environ.update(env)


if __name__ == "__main__":
    unittest.main()
