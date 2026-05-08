#!/usr/bin/env bash
# deploy.sh — Deploy the chatbot to an EC2 instance.
#
# Prerequisites:
#   - EC2_HOST env var set (e.g. ec2-user@1.2.3.4)
#   - SSH key configured (~/.ssh/config or agent)
#   - .env file present in the project root
#
# Usage: ./scripts/deploy.sh

set -euo pipefail

REPO_URL="${REPO_URL:-git@github.com:yourorg/company-chatbot.git}"
REMOTE_DIR="/home/ec2-user/company-chatbot"

if [[ -z "${EC2_HOST:-}" ]]; then
    echo "❌  EC2_HOST is not set. Export it first:"
    echo "    export EC2_HOST=ec2-user@your-ec2-ip"
    exit 1
fi

if [[ ! -f ".env" ]]; then
    echo "❌  .env file not found in project root. Copy .env.example and fill it in."
    exit 1
fi

echo "══════════════════════════════════════════════════════════════"
echo "  Company Chatbot — Deploying to ${EC2_HOST}"
echo "══════════════════════════════════════════════════════════════"

# ── 1. Clone or pull the repository ──────────────────────────────────
echo "[1/5] Syncing repository on remote..."
ssh "${EC2_HOST}" <<ENDSSH
    set -euo pipefail
    if [[ -d "${REMOTE_DIR}" ]]; then
        cd "${REMOTE_DIR}" && git pull --ff-only
    else
        git clone "${REPO_URL}" "${REMOTE_DIR}"
    fi
ENDSSH

# ── 2. Copy .env to server ──────────────────────────────────────────
echo "[2/5] Uploading .env..."
scp .env "${EC2_HOST}:${REMOTE_DIR}/.env"

# ── 3. Build and start services ─────────────────────────────────────
echo "[3/5] Starting services with Docker Compose..."
ssh "${EC2_HOST}" <<ENDSSH
    set -euo pipefail
    cd "${REMOTE_DIR}"
    docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
ENDSSH

# ── 4. Pull LLM and embedding models ────────────────────────────────
echo "[4/5] Pulling Ollama models (this may take a while)..."
ssh "${EC2_HOST}" <<ENDSSH
    set -euo pipefail
    echo "  → Pulling qwen2.5:3b..."
    docker exec ollama ollama pull qwen2.5:3b
    echo "  → Pulling nomic-embed-text..."
    docker exec ollama ollama pull nomic-embed-text
ENDSSH

# ── 5. Health check ──────────────────────────────────────────────────
echo "[5/5] Running health check..."
sleep 5
ssh "${EC2_HOST}" "curl -sf http://localhost:8000/health" && echo "" || echo "⚠️  Health check failed — check logs with: docker compose logs app"

echo ""
echo "✅  Deployment complete!"
echo "    Dashboard:  https://yourdomain.com/health"
echo "    Logs:       ssh ${EC2_HOST} 'cd ${REMOTE_DIR} && docker compose logs -f app'"
