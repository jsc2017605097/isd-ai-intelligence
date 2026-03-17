#!/usr/bin/env python3
import os
import sys
import subprocess
from pathlib import Path

# ISD Ecosystem CLI - v1.1.0
# Distribution Version

BASE_DIR = Path(__file__).parent.absolute()
NEWS_DIR = BASE_DIR / "isdnews"
HUB_DIR = BASE_DIR / "isdnews-hub"

def run_cmd(cmd, cwd=None, shell=True):
    try:
        subprocess.run(cmd, cwd=cwd, shell=shell, check=True)
    except subprocess.CalledProcessError:
        print(f"❌ Lỗi khi thực hiện: {cmd}")
        sys.exit(1)

def install():
    print("🚀 Đang cài đặt hệ sinh thái ISD...")
    
    # Setup News
    if NEWS_DIR.exists():
        print("📦 Cấu hình Pipeline (isdnews)...")
        run_cmd("python3 -m venv venv", cwd=NEWS_DIR)
        run_cmd("./venv/bin/pip install -r requirements.txt", cwd=NEWS_DIR)
        if not (NEWS_DIR / ".env").exists():
            if (NEWS_DIR / ".env.example").exists():
                run_cmd("cp .env.example .env", cwd=NEWS_DIR)
            else:
                (NEWS_DIR / ".env").write_text("DEBUG=False\nAI_PROVIDER=ollama\nOLLAMA_BASE_URL=http://127.0.0.1:11434\n")
        run_cmd("./venv/bin/python manage.py migrate", cwd=NEWS_DIR)
    
    # Setup Hub
    if HUB_DIR.exists():
        print("📦 Cấu hình Dashboard (isdnews-hub)...")
        run_cmd("npm install", cwd=HUB_DIR)
        if not (HUB_DIR / ".env").exists():
            db_path = NEWS_DIR / "db.sqlite3"
            hub_db = HUB_DIR / "data" / "hub.sqlite3"
            env_content = f"PORT=8787\nSOURCE_DB_PATH={db_path}\nHUB_DB_PATH={hub_db}\nLLM_BASE_URL=http://127.0.0.1:11434\n"
            (HUB_DIR / ".env").write_text(env_content)

    print("\n✅ Cài đặt hoàn tất! Dùng 'isd start' để chạy hệ thống.")

def start():
    print("▶️ Đang khởi động các dịch vụ ISD...")
    if NEWS_DIR.exists():
        run_cmd(f"pm2 start \"source {NEWS_DIR}/venv/bin/activate && python manage.py celery worker\" --name isd-worker", cwd=NEWS_DIR)
        run_cmd(f"pm2 start \"source {NEWS_DIR}/venv/bin/activate && python manage.py celery beat\" --name isd-beat", cwd=NEWS_DIR)
    if HUB_DIR.exists():
        run_cmd(f"pm2 start apps/api/server.js --name isd-api", cwd=HUB_DIR)
    run_cmd("pm2 save")

def stop():
    print("⏹️ Đang dừng các dịch vụ ISD...")
    run_cmd("pm2 stop isd-worker isd-beat isd-api || true")

def restart():
    print("🔄 Đang khởi động lại các dịch vụ ISD...")
    run_cmd("pm2 restart isd-worker isd-beat isd-api || true")

def status():
    run_cmd("pm2 list | grep isd || echo 'Chưa có dịch vụ nào đang chạy.'")

def set_model(model_name):
    print(f"🤖 Đang chuyển sang model: {model_name}")
    env_path = NEWS_DIR / ".env"
    if env_path.exists():
        lines = env_path.read_text().splitlines()
        new_lines = [l if not l.startswith("AI_MODEL=") else f"AI_MODEL={model_name}" for l in lines]
        if not any(l.startswith("AI_MODEL=") for l in lines):
            new_lines.append(f"AI_MODEL={model_name}")
        env_path.write_text("\n".join(new_lines))
    restart()

def usage():
    print("""
ISD Ecosystem CLI
Sử dụng:
  isd install      - Cài đặt môi trường từ đầu (venv, npm, db)
  isd start        - Chạy tất cả dịch vụ bằng PM2
  isd stop         - Dừng tất cả dịch vụ
  isd restart      - Khởi động lại dịch vụ
  isd status       - Xem tình trạng các dịch vụ
  isd model <name> - Đổi model AI (VD: isd model qwen3:30b)
    """)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        usage()
        sys.exit(0)
    
    cmd = sys.argv[1]
    if cmd == "install": install()
    elif cmd == "start": start()
    elif cmd == "stop": stop()
    elif cmd == "restart": restart()
    elif cmd == "status": status()
    elif cmd == "model" and len(sys.argv) > 2: set_model(sys.argv[2])
    else: usage()
