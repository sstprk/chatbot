# Mnemo Slack Bot

Slack-facing relay for the Mnemo knowledge infrastructure platform. This container has no AI, no vector DB, no embedding model — it forwards every Slack message to a Mnemo user container's `/query` endpoint and returns the response.

```
Slack  →  mnemo-slack  →  User Container /query  →  Slack
```

## Prerequisites

- A running **Mnemo user container** (from the mnemo-container repo) reachable on the `mnemo-net` Docker network
- A **Slack app** configured with the scopes and events listed below
- An **HTTPS endpoint** (required by Slack Events API) — use Caddy, ngrok, or Socket Mode for dev

## Slack App Configuration

### Required OAuth Scopes

| Scope | Purpose |
|---|---|
| `app_mentions:read` | Receive @mention events |
| `chat:write` | Send messages |
| `im:history` | Read DM history |
| `im:write` | Send DMs |
| `reactions:write` | Add/remove thinking indicator |
| `users:read` | Resolve user names |
| `app_home:read` | Display App Home tab |

### Required Event Subscriptions

| Event | Purpose |
|---|---|
| `app_mention` | Respond to @mentions in channels |
| `message.im` | Respond to direct messages |
| `app_home_opened` | Display welcome in App Home |

## Quick Start

```bash
# 1. Clone
git clone https://github.com/sstprk/mnemo-slack.git
cd mnemo-slack

# 2. Configure
cp .env.example .env
# Fill in SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET, and CONTAINER_URL

# 3. Create the shared network (if not already created)
docker network create mnemo-net

# 4. Start
docker compose up -d --build

# 5. Set Slack Request URL
# In your Slack app settings → Event Subscriptions → Request URL:
# https://your-domain.com/slack/events

# 6. Test
# @mention the bot in any channel it's in
```

## Socket Mode vs HTTP Mode

| | Socket Mode | HTTP Mode |
|---|---|---|
| When to use | Local dev, no HTTPS | Production |
| Config | Set `SLACK_APP_TOKEN=xapp-...` | Leave `SLACK_APP_TOKEN` empty |
| HTTPS required | No | Yes |
| How it works | Bot opens WebSocket to Slack | Slack POSTs to your URL |

**If `SLACK_APP_TOKEN` is set, Socket Mode takes priority over HTTP mode.** To enable Socket Mode, generate an app-level token in your Slack app under *Settings → Basic Information → App-Level Tokens* with the `connections:write` scope.

## Pointing to a Different User Container

Change one environment variable:

```bash
CONTAINER_URL=http://other-container:8000
```

No code changes needed. The bot will forward all queries to the new target.

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `SLACK_BOT_TOKEN` | Yes | — | Bot User OAuth Token (`xoxb-...`) |
| `SLACK_SIGNING_SECRET` | Yes | — | From Basic Information → App Credentials |
| `SLACK_APP_TOKEN` | No | `""` | App-Level Token (`xapp-...`) for Socket Mode |
| `CONTAINER_URL` | No | `http://mnemo-chatbot:8000` | User container URL |
| `USER_API_KEY` | No | `""` | API key sent as `X-Api-Key` header |
| `BOT_NAME` | No | `Mnemo` | Display name in error messages and App Home |
| `QUERY_TIMEOUT` | No | `120.0` | Seconds to wait for user container response |
| `SHOW_SOURCES` | No | `true` | Append source citations to responses |
| `SHOW_PROVENANCE` | No | `false` | Append cache hit stats to responses |
| `TYPING_EMOJI` | No | `hourglass_flowing_sand` | Emoji for thinking indicator |
| `ERROR_MESSAGE` | No | `Sorry, I couldn't process...` | User-facing error message |
| `APP_HOST` | No | `0.0.0.0` | FastAPI bind host |
| `APP_PORT` | No | `3000` | FastAPI bind port |
| `LOG_LEVEL` | No | `INFO` | Python log level |

## Mnemo Master Registry

This container does **not** register itself with the Mnemo master. It is a Slack client, not a knowledge container. The user container it points to is what appears in the registry.

## HTTPS Setup with Caddy

For production, Slack requires HTTPS for Event Subscriptions.

1. Edit `caddy/Caddyfile` — replace `your-slack-domain.com` with your domain
2. Point your domain's DNS A record to your server
3. Deploy with the prod overlay:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Caddy auto-provisions TLS via Let's Encrypt. If your master container already runs Caddy, add the slack domain to the existing Caddyfile instead of running a second instance.

## Project Structure

```
mnemo-slack/
├── Dockerfile
├── docker-compose.yml
├── docker-compose.prod.yml
├── .env.example
├── .gitignore
├── README.md
├── requirements.txt
├── caddy/
│   └── Caddyfile
└── app/
    ├── main.py       # FastAPI entrypoint + Slack Bolt setup
    ├── config.py     # pydantic-settings configuration
    ├── bot.py        # Slack event handlers (mention, DM, App Home)
    └── client.py     # HTTP client for user container /query calls
```
