#!/usr/bin/env bash
# ISD Bootstrap - chạy 1 lần duy nhất để cài lệnh `isd`
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🚀 ISD Bootstrap"

# 1. Python
if ! command -v python3 &>/dev/null; then
  sudo apt-get update -qq && sudo apt-get install -y python3 python3-venv python3-dev
fi

# 2. Node.js
if ! command -v node &>/dev/null; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
  sudo apt-get install -y nodejs
fi

# 3. PM2
if ! command -v pm2 &>/dev/null; then
  sudo npm install -g pm2
fi

# 4. Chromium
if ! command -v chromium-browser &>/dev/null && ! command -v chromium &>/dev/null; then
  sudo apt-get install -y chromium-browser 2>/dev/null || sudo apt-get install -y chromium 2>/dev/null || true
fi

# 5. Đăng ký lệnh `isd` vào PATH
cat > /tmp/isd_cmd << EOF
#!/usr/bin/env bash
python3 "$SCRIPT_DIR/isd.py" "\$@"
EOF
sudo mv /tmp/isd_cmd /usr/local/bin/isd
sudo chmod +x /usr/local/bin/isd

echo ""
echo "✅ Xong! Từ giờ dùng lệnh: isd install / isd start"
