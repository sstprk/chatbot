#!/usr/bin/env bash
# setup_ec2.sh — Bootstrap an Amazon Linux 2023 instance for the chatbot.
# Usage: ssh ec2-user@<host> 'bash -s' < scripts/setup_ec2.sh

set -euo pipefail

echo "══════════════════════════════════════════════════════════════"
echo "  Company Chatbot — EC2 Setup (Amazon Linux 2023)"
echo "══════════════════════════════════════════════════════════════"

# ── 1. System update ─────────────────────────────────────────────────
echo "[1/4] Updating system packages..."
sudo dnf update -y

# ── 2. Install Docker ────────────────────────────────────────────────
echo "[2/4] Installing Docker..."
sudo dnf install -y docker

# ── 3. Install Docker Compose plugin ─────────────────────────────────
echo "[3/4] Installing Docker Compose plugin..."
sudo mkdir -p /usr/local/lib/docker/cli-plugins
COMPOSE_VERSION=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | grep '"tag_name"' | sed -E 's/.*"([^"]+)".*/\1/')
sudo curl -SL "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-linux-$(uname -m)" \
    -o /usr/local/lib/docker/cli-plugins/docker-compose
sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# Verify
docker compose version

# ── 4. Post-install configuration ────────────────────────────────────
echo "[4/4] Configuring Docker service..."
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker ec2-user

echo ""
echo "✅  Setup complete. Log out and back in for group changes to apply."
echo "    Then run:  docker compose version"
