import json
import subprocess
import urllib.error
import urllib.request
from datetime import date

from slack_assistant.config import Config

SYSTEM = """You write a short Slack note for an FRC team about today's shop activity.
Use only the messages given. Do not invent people, work, or decisions.
If the messages do not describe a meeting or work session, reply with exactly NO_MEETING.
Otherwise write one phone-length note, under 1200 characters: a few sentences on what people did, who was active, and decisions or next steps only if someone wrote them.
No ratings, scores, tables, or title line. The date is added for you."""


def no_meeting_line(day: date) -> str:
    return f"No meeting information for {day.isoformat()}."


def build_prompt(day: date, messages: list[dict]) -> str:
    lines = [f"Local date: {day.isoformat()}", "Messages:"]
    for msg in messages:
        lines.append(f"[{msg['channel']}] {msg['when']} {msg['user']}: {msg['text']}")
    text = "\n".join(lines)
    if len(text) > 60000:
        text = text[:60000] + "\n[truncated]"
    return text


def interpret(day: date, raw: str) -> tuple[str, str]:
    text = raw.strip()
    if text == "NO_MEETING" or not text:
        return "no_meeting", no_meeting_line(day)
    return "summary", f"{day.isoformat()}\n{text}"


def complete(cfg: Config, prompt: str) -> str:
    if cfg.llm_provider == "xai":
        return complete_xai(cfg, prompt)
    if cfg.llm_provider == "claude":
        return complete_claude(cfg, prompt)
    raise SystemExit(f"LLM_PROVIDER must be xai or claude, got {cfg.llm_provider}")


def unsummarized(day: date, messages: list[dict]) -> tuple[str, str]:
    lines = [day.isoformat(), "No model configured."]
    shown = messages[:30]
    for msg in shown:
        lines.append(f"[{msg['channel']}] {msg['when']} {msg['user']}: {msg['text']}")
    if len(messages) > len(shown):
        lines.append(f"... {len(messages) - len(shown)} more")
    return "summary", "\n".join(lines)


def summarize(day: date, messages: list[dict], cfg: Config) -> tuple[str, str]:
    if not messages:
        return "no_meeting", no_meeting_line(day)
    if cfg.llm_provider == "xai" and not cfg.xai_api_key:
        return unsummarized(day, messages)
    return interpret(day, complete(cfg, build_prompt(day, messages)))


def complete_xai(cfg: Config, prompt: str) -> str:
    payload = {
        "model": cfg.xai_model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
    }
    req = urllib.request.Request(
        "https://api.x.ai/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {cfg.xai_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()
        raise RuntimeError(detail or f"xAI HTTP {exc.code}") from exc
    return data["choices"][0]["message"]["content"]


def complete_claude(cfg: Config, prompt: str) -> str:
    cmd = [
        "claude",
        "-p",
        "--output-format",
        "text",
        "--tools",
        "",
        "--setting-sources",
        "user",
        "--no-session-persistence",
        "--permission-prompts",
        "none",
        "--system-prompt",
        SYSTEM,
    ]
    if cfg.claude_model:
        cmd.extend(["--model", cfg.claude_model])
    proc = subprocess.run(cmd, input=prompt, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise RuntimeError(detail or f"claude exited {proc.returncode}")
    return proc.stdout
