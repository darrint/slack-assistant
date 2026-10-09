import time

from slack_sdk.errors import SlackApiError

from slack_assistant.slack_scan import resolve_channel


def should_pong(msg: dict, bot_user_id: str) -> bool:
    if msg.get("subtype") not in (None, "file_share"):
        return False
    if msg.get("bot_id") or msg.get("user") == bot_user_id:
        return False
    return bool((msg.get("text") or "").strip())


def pending(messages, bot_user_id: str, cursor: float) -> list[dict]:
    found = []
    for msg in messages:
        ts = float(msg["ts"])
        if ts <= cursor or not should_pong(msg, bot_user_id):
            continue
        found.append(msg)
    found.sort(key=lambda msg: float(msg["ts"]))
    return found


def serve(client, channel: str, *, interval: float = 2) -> int:
    found = resolve_channel(client, channel)
    channel = found["id"]
    name = found.get("name") or channel
    if found.get("is_private") and not found.get("is_member"):
        raise SystemExit(f"bot is not in #{name}. Invite it, then retry.")
    if not found.get("is_member"):
        client.conversations_join(channel=channel)
    bot_user_id = client.auth_test()["user_id"]
    cursor = time.time()
    print(f"pong listening in #{name} ({channel})")
    print("Slack will not show this bot online. It polls; it does not hold a connection.")
    while True:
        try:
            resp = client.conversations_history(
                channel=channel,
                oldest=f"{cursor:.6f}",
                inclusive=False,
                limit=100,
            )
        except SlackApiError as exc:
            err = exc.response.get("error")
            if err in ("not_in_channel", "channel_not_found"):
                raise SystemExit(f"{err}: #{name} ({channel})") from exc
            print(f"history: {err}")
            time.sleep(interval)
            continue
        for msg in pending(resp.get("messages") or [], bot_user_id, cursor):
            client.chat_postMessage(channel=channel, text="pong", thread_ts=msg["ts"])
            cursor = float(msg["ts"])
            print("pong")
        time.sleep(interval)
