#!/bin/bash
# ISD Ecosystem Bootstrap
# This script installs the 'isd' CLI globally from the local folder.

set -e

echo "🧰 Đang cài đặt ISD CLI..."

# Lấy đường dẫn tuyệt đối của file isd.py trong thư mục hiện tại
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
CLI_SOURCE="$SCRIPT_DIR/isd.py"
INSTALL_PATH="/usr/local/bin/isd"

if [ ! -f "$CLI_SOURCE" ]; then
    echo "❌ Không tìm thấy file isd.py trong thư mục này!"
    exit 1
fi

# Tạo link shortcut toàn cục
sudo ln -sf "$CLI_SOURCE" "$INSTALL_PATH"
sudo chmod +x "$CLI_SOURCE"
sudo chmod +x "$INSTALL_PATH"

echo "✅ Đã cài đặt lệnh 'isd' thành công!"
echo "Bây giờ sếp có thể gõ 'isd install' để bắt đầu."
