#!/usr/bin/env bash
set -e

echo "🚀 ISD Smart Installer"
echo "════════════════════════════════"

# ── 1. Python ────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
  echo "📦 Installing Python..."
  sudo apt-get update -qq && sudo apt-get install -y python3 python3-venv python3-dev python3-pip
else
  echo "✅ Python: $(python3 --version)"
fi

# ── 2. Node.js ───────────────────────────────────────────────
if ! command -v node &>/dev/null; then
  echo "📦 Installing Node.js..."
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
  sudo apt-get install -y nodejs
else
  echo "✅ Node.js: $(node --version)"
fi

# ── 3. PM2 ───────────────────────────────────────────────────
if ! command -v pm2 &>/dev/null; then
  echo "📦 Installing PM2..."
  sudo npm install -g pm2
else
  echo "✅ PM2: $(pm2 --version)"
fi

# ── 4. Chromium (for Playwright) ─────────────────────────────
if ! command -v chromium-browser &>/dev/null && ! command -v chromium &>/dev/null; then
  echo "📦 Installing Chromium..."
  sudo apt-get install -y chromium-browser 2>/dev/null || sudo apt-get install -y chromium 2>/dev/null || true
else
  echo "✅ Chromium installed"
fi

# ── 5. Redis (optional, skip if not needed) ──────────────────
if command -v redis-server &>/dev/null; then
  echo "✅ Redis already installed"
else
  echo "⏭️  Redis not found. If you use Redis broker, install it with: sudo apt install redis-server"
fi

echo ""
echo "════════════════════════════════"
echo "🎯 Running ISD installer..."
echo ""

python3 isd.py install
