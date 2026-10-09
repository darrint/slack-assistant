import argparse
from dataclasses import replace
from datetime import datetime, time
from zoneinfo import ZoneInfo

from slack_sdk import WebClient

from slack_assistant import pong, report, slack_scan, summarize
from slack_assistant.config import Config, load, load_slack
from slack_assistant.store import PgStore


def run(
    cfg: Config,
    *,
    dry_run: bool = False,
    force: bool = False,
    now: datetime | None = None,
    client=None,
    store=None,
) -> int:
    tz = ZoneInfo(cfg.tz)
    now = now.astimezone(tz) if now else datetime.now(tz)
    day = now.date()
    start = datetime.combine(day, time.min, tzinfo=tz)
    own_store = store is None
    if store is None:
        store = PgStore(cfg.database_url)
    try:
        if not dry_run and not force and store.get_report(day):
            print(f"already posted for {day.isoformat()}")
            return 0
        slack = client or WebClient(token=cfg.slack_bot_token)
        cfg = replace(cfg, report_channel=slack_scan.resolve_channel(slack, cfg.report_channel)["id"])
        messages = slack_scan.collect(slack, cfg, start, now)
        kind, body = summarize.summarize(day, messages, cfg)
        if dry_run:
            print(body)
            return 0
        report.post(slack, cfg.report_channel, body)
        store.save_report(day, kind, body, now)
        print(body)
        return 0
    finally:
        if own_store:
            store.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="slack-assistant")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--pong", action="store_true", help="listen in the report channel and reply pong")
    args = parser.parse_args(argv)
    if args.pong:
        token, channel = load_slack()
        return pong.serve(WebClient(token=token), channel)
    return run(load(require_model=not args.dry_run), dry_run=args.dry_run, force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
