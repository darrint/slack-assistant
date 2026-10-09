# Plan: FRC 447 Slack daily report

A small nightly job. It reads today's Slack activity and posts one short note to a channel the bot owns. It is not the vault planning system, and it does not talk to Hermes.

## What it does

At 22:00 `America/Indiana/Indianapolis`, a systemd timer runs one shot:

1. Join any public channel the bot is not already in. Read those, plus private channels it has been invited to. Do not read DMs.
2. Collect human messages from local midnight through the run. Skip the report channel and the bot's own posts.
3. If that text is empty, post `No meeting information for YYYY-MM-DD.` to the report channel. Do not call a model.
4. Otherwise ask the configured model for a short summary of the day's student activity, including any meeting logs pasted into Slack. If the model says there was no meeting or work session, post the same no-meeting line. Otherwise post the summary to that same channel.

Both outcomes go to one channel. The window is today until 10pm, so a Mon/Tue 6–9pm meeting is in the same night's report.

## Report shape

One Slack message. Roughly:

- Date
- A few sentences on what people actually did
- Who was active (display names)
- Decisions or next steps only if someone wrote them

No ratings, no calendar flags, no standards critique, no wiki links, no plan-vs-actual tables. If the sources are thin, say so. Do not invent work.

## Stack

Python 3. `slack-sdk` and `psycopg` are in nixpkgs. No long-running Bolt process: a timer plus the Web API is enough.

`flake.nix` exposes a devShell for local iteration, `packages.default`, and `nixosModules.default`. The timer's `ExecStart` is the store package, not `nix develop`. Secrets stay out of this repo; the host flake decrypts them.

## Slack app (human step)

Create a Slack app, install it on the team workspace, and invite it to the report channel and to any private channels it should see.

Bot token scopes:

- `channels:read`, `channels:history`, `channels:join`
- `groups:read`, `groups:history`
- `chat:write`
- `users:read`

No `im:history`, `mpim:history`, or `users:read.email`.

Modern Slack apps only receive history for channels they have joined. The job joins public channels it is missing. The first run will post a join line in each of those channels. Private channels are never joined; someone must invite the bot.

## Model

`LLM_PROVIDER=xai` or `LLM_PROVIDER=claude`. One active provider per host.

- **xai** — POST `https://api.x.ai/v1/chat/completions` with `XAI_API_KEY` from the env file. This is the Supergrok account, used directly. Default model `grok-4.6`, override with `XAI_MODEL`. Do not shell out to OpenCode or Hermes. OpenCode is how that account is used interactively; the nightly job needs its own key so the other VM does not depend on this host's login.
- **claude** — `claude -p` as the user who has completed the Claude team login. That uses the subscription, not a separate Anthropic API key. The timer must run as that user, and `claude` must already be logged in. Pass `CLAUDE_MODEL` when set.

## State

Use the Postgres already on the host. Database `slack_assistant`. On startup, create:

- `reports(report_date date primary key, posted_at timestamptz, kind text, body text)`

`kind` is `summary` or `no_meeting`. A second fire the same local date does not post again unless `--force`.

Do not store raw Slack messages. Students are minors. Fetch, summarize, discard. The report text is enough to see what was posted.

`DATABASE_URL` comes from the env file so the other VM is not tied to peer auth on this host.

## Secrets

Not in this repo. The host flake decrypts a sops env file (mode 0400) into the timer.

Required:

- `SLACK_BOT_TOKEN`
- `SLACK_REPORT_CHANNEL` (channel ID)
- `DATABASE_URL`
- `LLM_PROVIDER`
- `XAI_API_KEY` when provider is `xai`

Optional:

- `XAI_MODEL`, `CLAUDE_MODEL`
- `SLACK_EXCLUDE_CHANNELS` (comma-separated IDs; the report channel is always excluded)
- `TZ` (default `America/Indiana/Indianapolis`)

## Layout to build

```
flake.nix                 # devShell, package, nixosModule
src/slack_assistant/
  __main__.py             # CLI: default run, --dry-run, --force
  config.py
  slack_scan.py           # list, join public, history for the window
  summarize.py            # xai HTTP or claude -p
  store.py                # ensure schema, insert report, skip if date exists
  report.py               # post or print
nix/timer.nix             # oneshot + timer; ExecStart is the store package
.env.example
```

`nixosModules.default` imports `nix/timer.nix`. It only writes the unit. Options: `enable`, `package`, `user`, `environmentFile`, `onCalendar` (default `22:00:00`), `timeZone`.

Timer: `Persistent = true` so a powered-off 10pm still runs after boot. `RandomizedDelaySec` is unnecessary.

## Out of scope

- NATS. Add it later if Leantime or another system should feed this report. Do not stub it.
- frc-team-management, BookStack, calendar status, observation ratings.
- Hermes.
- Socket Mode, slash commands, DMs, file-attachment download. If meeting logs are uploaded files rather than pasted text, that is a follow-up.

## Test

1. `nix develop --command python -m slack_assistant --dry-run` prints the note and does not post.
2. A day with no human messages posts the no-meeting line and does not call the model.
3. A second run the same date does not double-post.
4. `--force` posts again.
5. Private channels the bot was not invited to do not appear.
