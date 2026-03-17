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
    is_windows = sys.platform.startswith('win')
    
    # Tìm lệnh python phù hợp
    python_cmds = ["python", "py", "python3"]
    py_cmd = "python"
    for cmd in python_cmds:
        try:
            subprocess.run(f"{cmd} --version", shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            py_cmd = cmd
            break
        except:
            continue

    # Setup News
    if NEWS_DIR.exists():
        print(f"📦 Cấu hình Pipeline (isdnews) sử dụng {py_cmd}...")
        
        # Đảm bảo thư mục logs tồn tại để tránh lỗi Django logging
        logs_dir = NEWS_DIR / "logs"
        if not logs_dir.exists():
            logs_dir.mkdir(parents=True, exist_ok=True)
            print("📁 Đã tạo thư mục logs.")

        venv_dir = NEWS_DIR / "venv"
        run_cmd(f"{py_cmd} -m venv venv", cwd=NEWS_DIR)
        
        # Đường dẫn thực thi (Windows dùng Scripts, Linux dùng bin)
        if is_windows:
            pip_path = venv_dir / "Scripts" / "pip.exe"
            python_path = venv_dir / "Scripts" / "python.exe"
        else:
            pip_path = venv_dir / "bin" / "pip"
            python_path = venv_dir / "bin" / "python"
        
        # Chạy lệnh với dấu ngoặc kép bọc quanh đường dẫn để xử lý khoảng trắng
        print("📥 Đang cài đặt thư viện Python...")
        run_cmd(f'"{pip_path}" install -r requirements.txt', cwd=NEWS_DIR)
        
        print("🎭 Đang cài đặt Playwright Browser...")
        run_cmd(f'"{python_path}" -m playwright install chromium', cwd=NEWS_DIR)
        
        if not (NEWS_DIR / ".env").exists():
            if (NEWS_DIR / ".env.example").exists():
                import shutil
                shutil.copy(str(NEWS_DIR / ".env.example"), str(NEWS_DIR / ".env"))
            else:
                (NEWS_DIR / ".env").write_text("DEBUG=False\nAI_PROVIDER=ollama\nOLLAMA_BASE_URL=http://127.0.0.1:11434\n")
        
        print("🗄️ Đang khởi tạo Database...")
        run_cmd(f'"{python_path}" manage.py migrate', cwd=NEWS_DIR)
    
    # Setup Hub
    if HUB_DIR.exists():
        print("📦 Cấu hình Dashboard (isdnews-hub)...")
        # Kiểm tra npm
        run_cmd("npm install", cwd=HUB_DIR)
        if not (HUB_DIR / ".env").exists():
            # Đồng bộ đường dẫn DB (dùng đường dẫn tuyệt đối đã bọc ngoặc)
            db_path = str(NEWS_DIR / "db.sqlite3").replace("\\", "/")
            hub_db = str(HUB_DIR / "data" / "hub.sqlite3").replace("\\", "/")
            env_content = f"PORT=8787\nSOURCE_DB_PATH={db_path}\nHUB_DB_PATH={hub_db}\nLLM_BASE_URL=http://127.0.0.1:11434\n"
            (HUB_DIR / ".env").write_text(env_content)

    print("\n✅ Cài đặt hoàn tất! Dùng 'isd start' để chạy hệ thống.")

def start():
    print("▶️ Đang khởi động các dịch vụ ISD...")
    is_windows = sys.platform.startswith('win')
    
    # Kiểm tra PM2
    try:
        subprocess.run("pm2 --version", shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        print("❌ Lỗi: Không tìm thấy lệnh 'pm2'.")
        print("👉 Vui lòng cài đặt PM2 bằng lệnh: npm install -g pm2")
        return

    if NEWS_DIR.exists():
        python_path = NEWS_DIR / ("Scripts" if is_windows else "bin") / "python"
        
        # Trên Windows, PM2 chạy lệnh trực tiếp từ venv python, không cần 'source activate'
        worker_cmd = f'"{python_path}" manage.py celery worker'
        beat_cmd = f'"{python_path}" manage.py celery beat'
        
        if not is_windows:
            worker_cmd = f"source venv/bin/activate && {worker_cmd}"
            beat_cmd = f"source venv/bin/activate && {beat_cmd}"

        run_cmd(f'pm2 start "{worker_cmd}" --name isd-worker', cwd=NEWS_DIR)
        run_cmd(f'pm2 start "{beat_cmd}" --name isd-beat', cwd=NEWS_DIR)
        
    if HUB_DIR.exists():
        # Node.js thường chạy trực tiếp được
        run_cmd("pm2 start apps/api/server.js --name isd-api", cwd=HUB_DIR)
    
    run_cmd("pm2 save")
    print("\n✅ Tất cả dịch vụ đã được khởi động trong PM2!")

def stop():
    print("⏹️ Đang dừng các dịch vụ ISD...")
    run_cmd("pm2 stop isd-worker isd-beat isd-api || true")

def restart():
    print("🔄 Đang khởi động lại các dịch vụ ISD...")
    # Tương tự start, cần đảm bảo đường dẫn đúng nếu restart môi trường
    stop()
    start()

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
