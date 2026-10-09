# AGENTS.md

Rules for agents in this repo.

## What this is

A nightly Slack reporter for FRC team 447. Read [PLAN.md](PLAN.md) before adding behavior. Keep it smaller than that file, not larger.

## Do not

- Integrate frc-team-management, BookStack, calendars, ratings, or wiki links.
- Add NATS, Socket Mode, slash commands, or DM reads unless asked.
- Call Hermes or shell out to OpenCode. xAI is an HTTP call with `XAI_API_KEY`. Claude is `claude -p` for a team login.
- Grow this into a chore-stars-style service. Production runs `packages.default` from `nixosModules.default`. Keep the devShell for local iteration.
- Persist raw Slack messages. Store the posted report and the date only.
- Request or use `im:history`, `mpim:history`, or email scopes.
- Invent meeting details. Thin sources get a short report or the no-meeting line.
- Commit secrets, tokens, or `.env` files.
- Commit git changes unless asked.

## Do

- Post both outcomes to the one report channel.
- Window is local midnight through the run (`America/Indiana/Indianapolis`).
- Skip the report channel and the bot's own messages when collecting sources.
- Join missing public channels. Never join private channels.
- Skip a second post for the same local date unless `--force`.
- Keep the Slack note short enough to read on a phone.
- `--pong` is a no-model connectivity check. It only watches the report channel. Do not turn it into Socket Mode.
