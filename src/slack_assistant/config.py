import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    slack_bot_token: str
    report_channel: str
    database_url: str
    llm_provider: str
    xai_api_key: str | None
    xai_model: str
    claude_model: str | None
    exclude_channels: frozenset[str]
    tz: str


def load_slack() -> tuple[str, str]:
    missing = []
    token = os.environ.get("SLACK_BOT_TOKEN", "").strip()
    channel = os.environ.get("SLACK_REPORT_CHANNEL", "").strip()
    if not token:
        missing.append("SLACK_BOT_TOKEN")
    if not channel:
        missing.append("SLACK_REPORT_CHANNEL")
    if missing:
        raise SystemExit("missing env: " + ", ".join(missing))
    return token, channel


def load(*, require_model: bool = True) -> Config:
    provider = os.environ.get("LLM_PROVIDER", "xai").strip() or "xai"
    if provider not in ("xai", "claude"):
        raise SystemExit(f"LLM_PROVIDER must be xai or claude, got {provider}")

    missing = []

    def need(name: str) -> str:
        value = os.environ.get(name, "").strip()
        if not value:
            missing.append(name)
        return value

    token = need("SLACK_BOT_TOKEN")
    channel = need("SLACK_REPORT_CHANNEL")
    database_url = need("DATABASE_URL")
    xai_key = os.environ.get("XAI_API_KEY", "").strip() or None
    if require_model and provider == "xai" and not xai_key:
        missing.append("XAI_API_KEY")
    if missing:
        raise SystemExit("missing env: " + ", ".join(missing))

    exclude = frozenset(
        part.strip()
        for part in os.environ.get("SLACK_EXCLUDE_CHANNELS", "").split(",")
        if part.strip()
    )
    claude_model = os.environ.get("CLAUDE_MODEL", "").strip() or None
    return Config(
        slack_bot_token=token,
        report_channel=channel,
        database_url=database_url,
        llm_provider=provider,
        xai_api_key=xai_key,
        xai_model=os.environ.get("XAI_MODEL", "").strip() or "grok-4.6",
        claude_model=claude_model,
        exclude_channels=exclude,
        tz=os.environ.get("TZ", "").strip() or "America/Indiana/Indianapolis",
    )
