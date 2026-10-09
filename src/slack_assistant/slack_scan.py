import re
import sys
from datetime import datetime

from slack_sdk.errors import SlackApiError

from slack_assistant.config import Config

MENTION = re.compile(r"<@([A-Z0-9]+)>")
LINK = re.compile(r"<([^|>]+)\|([^>]+)>")
CHANNEL_TYPES = "public_channel,private_channel"


def select_channels(channels, report_channel: str, exclude: frozenset[str]):
    read = []
    join = []
    for ch in channels:
        if ch.get("is_im") or ch.get("is_mpim"):
            continue
        cid = ch["id"]
        if cid == report_channel or cid in exclude or ch.get("is_archived"):
            continue
        if ch.get("is_private"):
            if ch.get("is_member"):
                read.append(ch)
            continue
        if not ch.get("is_member"):
            join.append(ch)
        read.append(ch)
    return read, join


def find_channel(channels, ref: str):
    ref = ref.strip()
    by_id = [ch for ch in channels if ch["id"] == ref]
    if len(by_id) == 1:
        return by_id[0]
    name = ref.lstrip("#")
    found = [ch for ch in channels if ch.get("name") == name]
    if len(found) != 1:
        return None
    return found[0]


def resolve_channel(client, ref: str):
    found = find_channel(list_channels(client), ref)
    if found is None:
        raise SystemExit(
            f"channel not found: {ref}. Use the channel ID, or invite the bot if it is private."
        )
    return found


def list_channels(client):
    cursor = None
    out = []
    while True:
        kwargs = {
            "types": CHANNEL_TYPES,
            "exclude_archived": True,
            "limit": 200,
        }
        if cursor:
            kwargs["cursor"] = cursor
        resp = client.conversations_list(**kwargs)
        out.extend(resp["channels"])
        cursor = (resp.get("response_metadata") or {}).get("next_cursor") or ""
        if not cursor:
            return out


def join_public(client, channels):
    joined = set()
    for ch in channels:
        try:
            client.conversations_join(channel=ch["id"])
            joined.add(ch["id"])
        except SlackApiError as exc:
            err = exc.response.get("error")
            if err == "already_in_channel":
                joined.add(ch["id"])
                continue
            print(f"skip join {ch.get('name', ch['id'])}: {err}", file=sys.stderr)
    return joined


def user_names(client) -> dict[str, str]:
    cursor = None
    names = {}
    while True:
        kwargs = {"limit": 200}
        if cursor:
            kwargs["cursor"] = cursor
        resp = client.users_list(**kwargs)
        for member in resp["members"]:
            profile = member.get("profile") or {}
            names[member["id"]] = (
                profile.get("display_name")
                or profile.get("real_name")
                or member.get("name")
                or member["id"]
            )
        cursor = (resp.get("response_metadata") or {}).get("next_cursor") or ""
        if not cursor:
            return names


def plain_text(text: str, names: dict[str, str]) -> str:
    text = MENTION.sub(lambda m: names.get(m.group(1), m.group(1)), text)
    text = LINK.sub(lambda m: m.group(2), text)
    return text.strip()


def is_human(msg: dict, bot_user_id: str) -> bool:
    if msg.get("subtype") not in (None, "file_share"):
        return False
    if msg.get("bot_id") or msg.get("user") == bot_user_id:
        return False
    return bool((msg.get("text") or "").strip())


def history(client, channel_id: str, oldest: str, latest: str):
    cursor = None
    out = []
    while True:
        kwargs = {
            "channel": channel_id,
            "oldest": oldest,
            "latest": latest,
            "inclusive": True,
            "limit": 200,
        }
        if cursor:
            kwargs["cursor"] = cursor
        resp = client.conversations_history(**kwargs)
        out.extend(resp.get("messages") or [])
        cursor = (resp.get("response_metadata") or {}).get("next_cursor") or ""
        if not cursor:
            return out


def collect(client, cfg: Config, start: datetime, now: datetime) -> list[dict]:
    bot_user_id = client.auth_test()["user_id"]
    channels = list_channels(client)
    read, to_join = select_channels(channels, cfg.report_channel, cfg.exclude_channels)
    joined = join_public(client, to_join)
    names = user_names(client)
    oldest = f"{start.timestamp():.6f}"
    latest = f"{now.timestamp():.6f}"
    found = []
    for ch in read:
        if ch["id"] in {item["id"] for item in to_join} and ch["id"] not in joined:
            continue
        try:
            messages = history(client, ch["id"], oldest, latest)
        except SlackApiError as exc:
            err = exc.response.get("error")
            print(f"skip history {ch.get('name', ch['id'])}: {err}", file=sys.stderr)
            continue
        for msg in messages:
            if not is_human(msg, bot_user_id):
                continue
            found.append(
                {
                    "channel": ch.get("name") or ch["id"],
                    "when": datetime.fromtimestamp(float(msg["ts"]), start.tzinfo).strftime("%H:%M"),
                    "user": names.get(msg["user"], msg["user"]),
                    "text": plain_text(msg["text"], names),
                    "ts": float(msg["ts"]),
                }
            )
    found.sort(key=lambda item: item["ts"])
    return found
