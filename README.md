# slack-assistant

Nightly Slack report for FRC team 447. At 10:00pm `America/Indiana/Indianapolis` it reads today's public channels (after joining them) and private channels it has been invited to, then posts one note to its own channel.

If nobody wrote meeting or work-session information, the note is:

```
No meeting information for YYYY-MM-DD.
```

Otherwise it is a short summary of student activity, including meeting logs pasted into Slack. Design notes are in [PLAN.md](PLAN.md).

## Run

```
nix develop
python -m slack_assistant --dry-run
```

`--dry-run` prints the note and does not post. It does not need `XAI_API_KEY`. `--force` posts even if today's report is already stored.

No model yet:

```
python -m slack_assistant --pong
```

That only needs `SLACK_BOT_TOKEN` and `SLACK_REPORT_CHANNEL`. It watches that channel and replies `pong` to new human messages. It does not join other channels.

Copy `.env.example` to a file outside the repo and export it, or pass it to systemd. Do not commit tokens.

## Slack app

1. At https://api.slack.com/apps choose **Create New App** → **From a manifest**, paste [slack-manifest.yaml](slack-manifest.yaml), and install it on the team workspace.
2. Copy the **Bot User OAuth Token** into `SLACK_BOT_TOKEN`.
3. Create a channel for the bot, invite the bot, and put the channel ID or `#name` in `SLACK_REPORT_CHANNEL`.
4. Invite the bot to any private channels it should read. It will join public channels itself. The first join posts a line in each channel.

No DMs.

## Model

`LLM_PROVIDER=xai` calls `https://api.x.ai/v1` with `XAI_API_KEY` (Supergrok). Create that key for this account. The job does not use OpenCode or Hermes.

`LLM_PROVIDER=claude` runs `claude -p` as the user who is logged into the Claude team plan. Log in once with `claude` before enabling the timer.

## Host

Import `nixosModules.default`. The timer runs `packages.default` (`slack-assistant`), not `nix develop`. Set `user` and `environmentFile`. Postgres must already be running; the app creates the `reports` table in the database named by `DATABASE_URL`. Secrets stay out of this repo.
