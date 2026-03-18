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
    
    # Hỏi người dùng về Redis
    use_redis_input = input("❓ Sếp có muốn dùng Redis không? (Y/n): ").strip().lower()
    use_redis = "True" if use_redis_input != 'n' else "False"

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
                # Đọc .env.example và thay thế giá trị
                lines = (NEWS_DIR / ".env.example").read_text().splitlines()
                new_lines = []
                for line in lines:
                    if line.startswith("USE_REDIS="):
                        new_lines.append(f"USE_REDIS={use_redis}")
                    elif line.startswith("CELERY_BROKER_URL=") and use_redis == "False":
                        new_lines.append(f"# {line} (Disabled for No-Redis mode)")
                    else:
                        new_lines.append(line)
                
                (NEWS_DIR / ".env").write_text("\n".join(new_lines))
                print(f"✅ Đã tạo file .env (USE_REDIS={use_redis})")
            else:
                (NEWS_DIR / ".env").write_text(f"DEBUG=False\nUSE_REDIS={use_redis}\nAI_PROVIDER=ollama\nOLLAMA_BASE_URL=http://127.0.0.1:11434\n")
        
        print("🗄️ Đang khởi tạo Database...")
        run_cmd(f'"{python_path}" manage.py migrate', cwd=NEWS_DIR)
    
    # Setup Hub
    if HUB_DIR.exists():
        print("📦 Cấu hình Dashboard (isdnews-hub)...")
        
        # Đảm bảo thư mục data tồn tại cho SQLite
        hub_data_dir = HUB_DIR / "data"
        if not hub_data_dir.exists():
            hub_data_dir.mkdir(parents=True, exist_ok=True)
            print("📁 Đã tạo thư mục data cho Hub.")

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

    # Tạo file ecosystem.config.js để quản lý tập trung và tránh lỗi cửa sổ nhấp nháy
    ecosystem_path = BASE_DIR / "ecosystem.config.js"
    
    news_dir_esc = str(NEWS_DIR).replace("\\", "\\\\")
    hub_dir_esc = str(HUB_DIR).replace("\\", "\\\\")
    
    if is_windows:
        py_path = f"{news_dir_esc}\\\\venv\\\\Scripts\\\\python.exe"
        # Trên Windows bắt buộc dùng --pool=solo để tránh lỗi WinError 5 Access Denied
        pool_flag = " --pool=solo"
    else:
        py_path = f"{news_dir_esc}/venv/bin/python"
        pool_flag = ""

    ecosystem_content = f"""
module.exports = {{
  apps : [
    {{
      name: 'isd-core',
      script: '{py_path}',
      cwd: '{news_dir_esc}',
      args: 'manage.py runserver 0.0.0.0:8000',
      autorestart: true,
      watch: false,
      windowsHide: true
    }},
    {{
      name: 'isd-worker',
      script: '{py_path}',
      cwd: '{news_dir_esc}',
      args: '-m celery -A isdnews worker --loglevel=info{pool_flag}',
      autorestart: true,
      watch: false,
      max_memory_restart: '1G',
      windowsHide: true
    }},
    {{
      name: 'isd-beat',
      script: '{py_path}',
      cwd: '{news_dir_esc}',
      args: '-m celery -A isdnews beat --loglevel=info',
      autorestart: true,
      watch: false,
      windowsHide: true
    }},
    {{
      name: 'isd-api',
      script: 'apps/api/server.js',
      cwd: '{hub_dir_esc}',
      autorestart: true,
      watch: false,
      windowsHide: true
    }}
  ]
}};
"""
    ecosystem_path.write_text(ecosystem_content, encoding='utf-8')

    # Chạy bằng ecosystem file
    run_cmd(f"pm2 start ecosystem.config.js", cwd=BASE_DIR)
    run_cmd("pm2 save")
    print("\n✅ Đã khởi động hệ thống qua Ecosystem! Dùng 'pm2 status' để kiểm tra.")
    print("⚠️  Lưu ý: Nếu isd-worker báo lỗi, hãy đảm bảo sếp đã cài và bật Redis trên Windows.")

def stop():
    print("⏹️ Đang dừng các dịch vụ ISD...")
    run_cmd("pm2 stop isd-worker isd-beat isd-api isd-core || true")

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

def create_superuser():
    print("👤 Đang tạo tài khoản Admin (Superuser)...")
    if NEWS_DIR.exists():
        is_windows = sys.platform.startswith('win')
        python_path = NEWS_DIR / "venv" / ("Scripts" if is_windows else "bin") / ("python.exe" if is_windows else "python")
        run_cmd(f'"{python_path}" manage.py createsuperuser', cwd=NEWS_DIR)

def usage():
    print("""
ISD Ecosystem CLI
Sử dụng:
  isd install      - Cài đặt môi trường từ đầu (venv, npm, db)
  isd admin        - Tạo tài khoản Admin (Superuser)
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
    elif cmd == "admin": create_superuser()
    elif cmd == "start": start()
    elif cmd == "stop": stop()
    elif cmd == "restart": restart()
    elif cmd == "status": status()
    elif cmd == "model" and len(sys.argv) > 2: set_model(sys.argv[2])
    else: usage()
