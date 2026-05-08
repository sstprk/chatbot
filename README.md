# Company Chatbot

An internal RAG-powered chatbot that ingests knowledge from **Slack channels** and **Notion pages**, stores it in a vector database, and answers employee questions via Slack @mentions or DMs.

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Slack API   │────▶│   FastAPI     │────▶│   Ollama     │
│  (events)    │◀────│  + Slack Bolt │◀────│  qwen2.5:3b  │
└──────────────┘     └──────┬───────┘     └──────────────┘
                           │
                    ┌──────┴───────┐
                    │   Qdrant     │
                    │ (vector DB)  │
                    └──────────────┘
                           ▲
              ┌────────────┴────────────┐
              │      APScheduler        │
              │  ┌─────────┬──────────┐ │
              │  │  Slack   │  Notion  │ │
              │  │ Ingestor │ Ingestor │ │
              │  └─────────┴──────────┘ │
              └─────────────────────────┘
```

## Stack

| Component     | Technology                           |
|---------------|--------------------------------------|
| LLM           | Ollama — `qwen2.5:3b`               |
| Embeddings    | Ollama — `nomic-embed-text` (768d)   |
| Vector DB     | Qdrant (cosine similarity)           |
| Orchestration | LlamaIndex (chunking + Notion reader)|
| App Framework | FastAPI + Slack Bolt (HTTP mode)      |
| Scheduler     | APScheduler (AsyncIO)                |
| Reverse Proxy | Caddy (auto HTTPS, production only)  |
| Containers    | Docker + Docker Compose              |

---

## Quick Start (Local Development)

### 1. Clone and configure

```bash
cp .env.example .env
# Edit .env with your Slack and Notion credentials
```

### 2. Start services

```bash
docker compose up -d --build
```

### 3. Pull the models

```bash
docker exec ollama ollama pull qwen2.5:3b
docker exec ollama ollama pull nomic-embed-text
```

### 4. Verify

```bash
curl http://localhost:8000/health
# → {"status":"ok","model":"qwen2.5:3b","embed_model":"nomic-embed-text","collection":"company_knowledge"}
```

### 5. Configure Slack

In your Slack App settings:

1. **Event Subscriptions** → Request URL: `https://yourdomain.com/slack/events`
2. **Subscribe to bot events**: `app_mention`, `message.im`
3. **OAuth Scopes**: `app_mentions:read`, `chat:write`, `channels:history`, `channels:read`, `users:read`, `reactions:write`, `im:history`

---

## Production Deployment (AWS EC2)

### 1. Provision EC2

- Amazon Linux 2023, `t3.xlarge` or larger (Ollama needs RAM)
- Open ports: 22, 80, 443
- Attach an Elastic IP
- Point your domain's DNS A record to the Elastic IP

### 2. Bootstrap the instance

```bash
ssh ec2-user@your-ec2-ip 'bash -s' < scripts/setup_ec2.sh
```

### 3. Deploy

```bash
export EC2_HOST=ec2-user@your-ec2-ip
./scripts/deploy.sh
```

### 4. Update Caddyfile

Edit `caddy/Caddyfile` and replace `yourdomain.com` with your actual domain before deploying.

---

## Environment Variables

| Variable                     | Description                              | Default              |
|------------------------------|------------------------------------------|----------------------|
| `SLACK_BOT_TOKEN`            | Slack Bot OAuth token (`xoxb-...`)       | —                    |
| `SLACK_SIGNING_SECRET`       | Slack app signing secret                 | —                    |
| `SLACK_CHANNELS_TO_INGEST`   | Comma-separated channel names            | `""`                 |
| `NOTION_INTEGRATION_TOKEN`   | Notion integration token                 | `""`                 |
| `NOTION_PAGE_IDS`            | Comma-separated Notion page IDs          | `""`                 |
| `OLLAMA_BASE_URL`            | Ollama API base URL                      | `http://ollama:11434`|
| `OLLAMA_MODEL`               | LLM model name                           | `qwen2.5:3b`        |
| `OLLAMA_EMBED_MODEL`         | Embedding model name                     | `nomic-embed-text`   |
| `QDRANT_URL`                 | Qdrant server URL                        | `http://qdrant:6333` |
| `QDRANT_COLLECTION`          | Qdrant collection name                   | `company_knowledge`  |
| `INGESTION_INTERVAL_MINUTES` | How often to re-ingest (minutes)         | `60`                 |
| `APP_HOST`                   | FastAPI bind host                        | `0.0.0.0`           |
| `APP_PORT`                   | FastAPI bind port                        | `8000`               |

---

## Project Structure

```
company-chatbot/
├── docker-compose.yml          # Local dev: Ollama + Qdrant + App
├── docker-compose.prod.yml     # Production overlay: adds Caddy HTTPS
├── Dockerfile                  # Python 3.11-slim app container
├── .env.example                # Template environment variables
├── requirements.txt            # Pinned Python dependencies
├── caddy/
│   └── Caddyfile               # Reverse proxy with auto HTTPS
├── scripts/
│   ├── setup_ec2.sh            # Bootstrap Amazon Linux 2023
│   └── deploy.sh               # Deploy to EC2 via SSH
└── app/
    ├── main.py                 # FastAPI entrypoint + Slack mount
    ├── config.py               # pydantic-settings configuration
    ├── rag/
    │   ├── pipeline.py         # RAG: embed → retrieve → generate
    │   ├── embeddings.py       # Ollama /api/embed wrapper
    │   └── qdrant_store.py     # Qdrant collection + upsert + search
    ├── ingestion/
    │   ├── scheduler.py        # APScheduler: periodic ingestion
    │   ├── slack_ingestor.py   # Slack channel history ingestor
    │   └── notion_ingestor.py  # Notion page ingestor
    └── slack/
        ├── bot.py              # Slack Bolt app (HTTP mode)
        └── handlers.py         # @mention + DM event handlers
```

---

## How It Works

1. **Ingestion** — On startup (and every N minutes), APScheduler runs the Slack and Notion ingestors. They pull new content, chunk it, embed via `nomic-embed-text`, and upsert into Qdrant.

2. **Query** — When a user @mentions the bot or sends a DM, the handler calls the RAG pipeline:
   - Embeds the question
   - Retrieves top-5 relevant chunks from Qdrant
   - Builds a context-enriched prompt
   - Generates an answer via `qwen2.5:3b`
   - Appends source citations (channel name, page title)

3. **Response** — The answer is posted back to Slack in the same thread, with source attributions formatted as Slack mrkdwn.
