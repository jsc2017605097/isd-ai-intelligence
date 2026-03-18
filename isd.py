#!/usr/bin/env python3
import os
import sys
import subprocess
import json
from pathlib import Path

# ISD Ecosystem CLI - v1.4.1
# Distribution Version (Robust Cross-Platform UI)

BASE_DIR = Path(__file__).parent.absolute()
NEWS_DIR = BASE_DIR / "isdnews"
HUB_DIR = BASE_DIR / "isdnews-hub"

def run_cmd(cmd, cwd=None, shell=True):
    try:
        subprocess.run(cmd, cwd=cwd, shell=shell, check=True)
    except subprocess.CalledProcessError:
        print(f"Error executing: {cmd}")
        sys.exit(1)

def pick(title, options):
    """Zero-dependency cross-platform arrow-key selector"""
    print(f"\n=== {title} ===")
    print("(Use arrow keys/WASD to move, Enter to select)")
    
    current_idx = 0
    
    # Check if we are on Windows
    is_windows = sys.platform.startswith('win')
    
    if is_windows:
        import msvcrt
        def get_key():
            ch = msvcrt.getch()
            if ch in [b'\x00', b'\xe0']: # Function key prefix
                ch = msvcrt.getch()
                if ch == b'H': return 'up'
                if ch == b'P': return 'down'
            if ch in [b'w', b'W']: return 'up'
            if ch in [b's', b'S']: return 'down'
            if ch == b'\r': return 'enter'
            return None
    else:
        import tty, termios
        def get_key():
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(sys.stdin.fileno())
                ch = sys.stdin.read(1)
                if ch == '\x1b':
                    ch2 = sys.stdin.read(2)
                    if ch2 == '[A': return 'up'
                    if ch2 == '[B': return 'down'
                if ch == '\r' or ch == '\n': return 'enter'
                if ch == 'w': return 'up'
                if ch == 's': return 'down'
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            return None

    def show_menu(idx):
        # Clear lines
        for _ in range(len(options)):
            sys.stdout.write("\033[K") # Clear line
        sys.stdout.write(f"\033[{len(options)}A") # Move up
        
        for i, option in enumerate(options):
            if i == idx:
                print(f"\033[96m> {option}\033[0m") # Cyan for selection
            else:
                print(f"  {option}")

    # Initial print placeholders
    for _ in range(len(options)): print("")
    
    while True:
        show_menu(current_idx)
        key = get_key()
        if key == 'up' and current_idx > 0:
            current_idx -= 1
        elif key == 'down' and current_idx < len(options) - 1:
            current_idx += 1
        elif key == 'enter':
            return options[current_idx]

def configure_ai():
    print("\n--- AI Configuration ---")
    
    providers = ["ollama", "openai", "google", "anthropic", "openrouter"]
    provider = pick("Select AI Provider", providers)
    
    auth_methods = ["API Key"]
    if provider in ["google", "openai", "anthropic"]:
        auth_methods.append("OAuth 2.0")
    
    auth_method = pick(f"Select Authentication for {provider.upper()}", auth_methods)
    
    config_data = {
        "AI_PROVIDER": provider,
        "AI_AUTH_METHOD": "oauth" if auth_method == "OAuth 2.0" else "apikey",
        "AI_API_KEY": "",
        "AI_CLIENT_ID": "",
        "AI_CLIENT_SECRET": "",
        "AI_REFRESH_TOKEN": "",
        "AI_BASE_URL": "",
        "AI_MODEL": "qwen3:30b-a3b" if provider == "ollama" else ""
    }

    if config_data["AI_AUTH_METHOD"] == "apikey":
        if provider != "ollama":
            config_data["AI_API_KEY"] = input(f"Enter {provider.upper()} API Key: ").strip()
            config_data["AI_MODEL"] = input(f"Enter Model Name (e.g. gpt-4o, gemini-1.5-flash...): ").strip()
        if provider == "openai":
            config_data["AI_BASE_URL"] = input("Enter Base URL (optional, press Enter for default): ").strip()
    else:
        print(f"\n🔑 Configuring OAuth for {provider.upper()}...")
        config_data["AI_CLIENT_ID"] = input("Enter Client ID: ").strip()
        config_data["AI_CLIENT_SECRET"] = input("Enter Client Secret: ").strip()
        config_data["AI_REFRESH_TOKEN"] = input("Enter Refresh Token: ").strip()
        config_data["AI_MODEL"] = input(f"Enter Model Name: ").strip()

    # Update BOTH .env files
    for env_path in [NEWS_DIR / ".env", HUB_DIR / ".env"]:
        if not env_path.parent.exists(): continue
        lines = env_path.read_text().splitlines() if env_path.exists() else []
        new_lines = []
        
        updates = config_data.copy()
        if env_path.parent == HUB_DIR:
            updates["LLM_API_STYLE"] = "openai" if provider != "ollama" else "ollama"
            updates["LLM_BASE_URL"] = config_data["AI_BASE_URL"]
            updates["CHAT_MODEL"] = config_data["AI_MODEL"]
            updates["DIGEST_MODEL"] = config_data["AI_MODEL"]

        seen_keys = set()
        for line in lines:
            if "=" not in line: 
                new_lines.append(line)
                continue
            k = line.split("=")[0]
            if k in updates:
                new_lines.append(f"{k}={updates[k]}")
                seen_keys.add(k)
            else:
                new_lines.append(line)
                
        for k, v in updates.items():
            if k not in seen_keys:
                new_lines.append(f"{k}={v}")
                
        env_path.write_text("\n".join(new_lines))
    
    print(f"✅ AI Configuration updated successfully for {provider.upper()}.")
    print("🔄 Restarting services to apply changes...")
    restart()

def install():
    print("🚀 Installing ISD Ecosystem...")
    is_windows = sys.platform.startswith('win')
    
    use_redis_input = input("❓ Do you want to use Redis? (Y/n): ").strip().lower()
    use_redis = "True" if use_redis_input != 'n' else "False"

    python_cmds = ["python", "py", "python3"]
    py_cmd = "python"
    for cmd in python_cmds:
        try:
            subprocess.run(f"{cmd} --version", shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            py_cmd = cmd
            break
        except: continue

    if NEWS_DIR.exists():
        print(f"📦 Configuring Pipeline (isdnews) using {py_cmd}...")
        logs_dir = NEWS_DIR / "logs"
        if not logs_dir.exists(): logs_dir.mkdir(parents=True, exist_ok=True)
        venv_dir = NEWS_DIR / "venv"
        run_cmd(f"{py_cmd} -m venv venv", cwd=NEWS_DIR)
        
        exec_p = "Scripts" if is_windows else "bin"
        pip_path = venv_dir / exec_p / "pip"
        python_path = venv_dir / exec_p / "python"
        
        print("📥 Installing Python dependencies...")
        run_cmd(f'"{pip_path}" install -r requirements.txt', cwd=NEWS_DIR)
        run_cmd(f'"{python_path}" -m playwright install chromium', cwd=NEWS_DIR)
        
        if not (NEWS_DIR / ".env").exists():
            if (NEWS_DIR / ".env.example").exists():
                lines = (NEWS_DIR / ".env.example").read_text().splitlines()
                new_lines = [f"USE_REDIS={use_redis}" if l.startswith("USE_REDIS=") else l for l in lines]
                (NEWS_DIR / ".env").write_text("\n".join(new_lines))
            else:
                (NEWS_DIR / ".env").write_text(f"DEBUG=True\nUSE_REDIS={use_redis}\nAI_PROVIDER=ollama\n")
        
        configure_ai()
        print("🗄️ Migrating Database...")
        run_cmd(f'"{python_path}" manage.py migrate', cwd=NEWS_DIR)
        print("📁 Collecting static files...")
        run_cmd(f'"{python_path}" manage.py collectstatic --noinput', cwd=NEWS_DIR)
    
    if HUB_DIR.exists():
        print("📦 Configuring Dashboard (isdnews-hub)...")
        if not (HUB_DIR / "data").exists(): (HUB_DIR / "data").mkdir(parents=True, exist_ok=True)
        run_cmd("npm install", cwd=HUB_DIR)
        if not (HUB_DIR / ".env").exists():
            env_content = f"PORT=8787\nSOURCE_DB_PATH={str(NEWS_DIR/'db.sqlite3').replace('\\','/')}\nHUB_DB_PATH={str(HUB_DIR/'data'/'hub.sqlite3').replace('\\','/')}\nLLM_BASE_URL=http://127.0.0.1:11434\n"
            (HUB_DIR / ".env").write_text(env_content)
    print("\n✅ Setup complete! Use 'isd start' to run.")

def start():
    print("▶️ Starting ISD Services...")
    is_windows = sys.platform.startswith('win')
    try:
        subprocess.run("pm2 --version", shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        print("❌ Error: 'pm2' not found. Install it: npm install -g pm2"); return

    ecosystem_path = BASE_DIR / "ecosystem.config.js"
    news_dir_esc = str(NEWS_DIR).replace("\\", "\\\\")
    hub_dir_esc = str(HUB_DIR).replace("\\", "\\\\")
    py_path = str(NEWS_DIR / "venv" / ("Scripts" if is_windows else "bin") / "python").replace("\\", "\\\\")
    pool_flag = " --pool=solo" if is_windows else ""

    ecosystem_content = f"""
module.exports = {{
  apps : [
    {{ name: 'isd-core', script: 'manage.py', cwd: '{news_dir_esc}', interpreter: '{py_path}', args: 'runserver 0.0.0.0:8000', windowsHide: true, env: {{ PYTHONPATH: '{news_dir_esc}' }} }},
    {{ name: 'isd-worker', script: '{py_path}', cwd: '{news_dir_esc}', args: '-m celery -A isdnews worker --loglevel=info{pool_flag}', windowsHide: true, env: {{ PYTHONPATH: '{news_dir_esc}' }} }},
    {{ name: 'isd-beat', script: '{py_path}', cwd: '{news_dir_esc}', args: '-m celery -A isdnews beat --loglevel=info', windowsHide: true, env: {{ PYTHONPATH: '{news_dir_esc}' }} }},
    {{ name: 'isd-api', script: 'apps/api/server.js', cwd: '{hub_dir_esc}', windowsHide: true }}
  ]
}};"""
    ecosystem_path.write_text(ecosystem_content, encoding='utf-8')
    run_cmd("pm2 start ecosystem.config.js", cwd=BASE_DIR)
    run_cmd("pm2 save")
    print("\n✅ Services started! Check with 'pm2 status'.")

def stop(): run_cmd("pm2 stop isd-worker isd-beat isd-api isd-core || true")
def restart(): stop(); start()
def status(): run_cmd("pm2 list | grep isd || echo 'No services.'")

def show_config():
    print("\n--- 🔍 Current ISD Configuration ---")
    env_path = NEWS_DIR / ".env"
    if not env_path.exists():
        print("❌ Configuration file (.env) not found. Run 'isd install' first.")
        return

    lines = env_path.read_text().splitlines()
    config = {}
    for line in lines:
        if "=" in line:
            k, v = line.split("=", 1)
            config[k.strip()] = v.strip()

    provider = config.get("AI_PROVIDER", "Not set")
    model = config.get("AI_MODEL", "Not set")
    auth = config.get("AI_AUTH_METHOD", "apikey")
    redis = config.get("USE_REDIS", "True")

    print(f"🤖 AI Provider : {provider.upper()}")
    print(f"📦 AI Model    : {model}")
    print(f"🔑 Auth Method : {'OAuth 2.0' if auth == 'oauth' else 'API Key'}")
    print(f"💾 Using Redis : {'Yes' if redis == 'True' else 'No (SQLite Broker)'}")
    print(f"📂 Install Dir : {BASE_DIR}")
    print("-" * 35)

def configure_telegram():
    print("\n--- 📱 Telegram Per-Team Configuration ---")
    if not NEWS_DIR.exists():
        print("❌ isdnews directory not found.")
        return

    is_win = sys.platform.startswith('win')
    py = str(NEWS_DIR / "venv" / ("Scripts" if is_win else "bin") / ("python.exe" if is_win else "python"))
    
    # Get list of teams from DB via python script
    get_teams_script = """
import os, sys, django
sys.path.append('.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'isdnews.settings')
django.setup()
from collector.models import Team
teams = list(Team.objects.all().values('code', 'name'))
import json
print(json.dumps(teams))
"""
    try:
        output = subprocess.check_output(f'"{py}" -c "{get_teams_script}"', cwd=NEWS_DIR, shell=True).decode()
        teams = json.loads(output.splitlines()[-1])
    except Exception as e:
        print(f"❌ Error fetching teams: {e}")
        return

    if not teams:
        print("⚠️ No teams found in database. Run 'isd install' and check sources first.")
        return

    team_options = [f"{t['name']} ({t['code']})" for t in teams]
    selected_team_str = pick("Select team to configure Telegram", team_options)
    selected_team_code = selected_team_str.split('(')[1].split(')')[0]

    chat_id = input(f"Enter Telegram Chat ID for team {selected_team_code}: ").strip()
    
    if not chat_id:
        print("❌ Chat ID cannot be empty.")
        return

    # Update DB via python script
    update_db_script = f"""
import os, sys, django
sys.path.append('.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'isdnews.settings')
django.setup()
from collector.models import Team, SystemConfig
team = Team.objects.get(code='{selected_team_code}')
cfg, created = SystemConfig.objects.get_or_create(
    key='telegram_chat_id', 
    team=team,
    defaults={{'key_type': 'webhook', 'value': '{chat_id}', 'is_active': True}}
)
if not created:
    cfg.value = '{chat_id}'
    cfg.save()
print("SUCCESS")
"""
    try:
        subprocess.check_call(f'"{py}" -c "{update_db_script}"', cwd=NEWS_DIR, shell=True)
        print(f"✅ Telegram Chat ID updated for team {selected_team_code}!")
    except Exception as e:
        print(f"❌ Error updating database: {e}")

def usage():
    print("""
ISD Ecosystem CLI
Sử dụng:
  isd install         - Cài đặt môi trường từ đầu (venv, npm, db)
  isd config ai       - Cấu hình AI Provider (Multi-Vendor + OAuth)
  isd config telegram - Cấu hình Group Telegram riêng cho từng Team
  isd config show     - Kiểm tra Model và Vendor hiện tại
  isd admin           - Tạo tài khoản Admin (Superuser)
  isd start           - Chạy tất cả dịch vụ bằng PM2
  isd stop            - Dừng tất cả dịch vụ
  isd restart         - Khởi động lại dịch vụ
  isd status          - Xem tình trạng các dịch vụ
  isd model <name>    - Đổi nhanh model (VD: isd model qwen3:30b)
    """)

if __name__ == "__main__":
    if len(sys.argv) < 2: usage(); sys.exit(0)
    cmd = sys.argv[1]
    if cmd == "install": install()
    elif cmd == "admin": 
        is_win = sys.platform.startswith('win')
        py = str(NEWS_DIR / "venv" / ("Scripts" if is_win else "bin") / ("python.exe" if is_win else "python"))
        run_cmd(f'"{py}" manage.py createsuperuser', cwd=NEWS_DIR)
    elif cmd == "config" and len(sys.argv) > 2:
        if sys.argv[2] == "ai": configure_ai()
        elif sys.argv[2] == "telegram": configure_telegram()
        elif sys.argv[2] == "show": show_config()
        else: usage()
    elif cmd == "start": start()
    elif cmd == "stop": stop()
    elif cmd == "restart": restart()
    elif cmd == "status": status()
    elif cmd == "model" and len(sys.argv) > 2: set_model(sys.argv[2])
    else: usage()
