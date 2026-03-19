#!/usr/bin/env bash
# ISD Ecosystem Bootstrap Script (Optimized)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "🚀 ISD Ecosystem Bootstrap"

# --- 1. Dependency Checks & Installation ---
OS="$(uname -s)"

install_dependencies() {
    if command -v apt-get &>/dev/null; then
        sudo apt-get update -qq
        sudo apt-get install -y python3 python3-venv python3-dev curl git
    elif command -v yum &>/dev/null; then
        sudo yum install -y python3 python3-devel curl git
    elif command -v brew &>/dev/null; then
        brew install python node pm2
    fi
}

echo "📦 Checking system dependencies..."
install_dependencies

# Node.js & PM2
if ! command -v node &>/dev/null; then
    echo "📥 Installing Node.js..."
    if command -v apt-get &>/dev/null; then
        curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
        sudo apt-get install -y nodejs
    fi
fi

if ! command -v pm2 &>/dev/null; then
    echo "📥 Installing PM2 globally..."
    sudo npm install -g pm2
fi

# --- 2. ISD CLI Registration ---
echo "⚓ Registering 'isd' command..."

BIN_DIR="/usr/local/bin"
if [ ! -w "$BIN_DIR" ]; then
    BIN_DIR="$HOME/.local/bin"
    mkdir -p "$BIN_DIR"
    if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
        echo "export PATH=\$PATH:$BIN_DIR" >> "$HOME/.bashrc"
        echo "export PATH=\$PATH:$BIN_DIR" >> "$HOME/.zshrc"
        echo "⚠️ Added $BIN_DIR to PATH. Please restart your terminal or run: source ~/.bashrc"
    fi
fi

cat > /tmp/isd_cmd << EOF
#!/usr/bin/env bash
python3 "$SCRIPT_DIR/isd.py" "\$@"
EOF

sudo mv /tmp/isd_cmd "$BIN_DIR/isd" 2>/dev/null || mv /tmp/isd_cmd "$BIN_DIR/isd"
chmod +x "$BIN_DIR/isd"

echo ""
echo "✅ Bootstrap complete!"
echo "👉 You can now run: isd install"
echo ""
