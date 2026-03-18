#!/usr/bin/env python3
import os
import sys
import subprocess
import json
from pathlib import Path

# ISD Ecosystem CLI - v1.5.0
# Smart Installer Edition

BASE_DIR = Path(__file__).parent.absolute()
NEWS_DIR = BASE_DIR / "isdnews"
HUB_DIR = BASE_DIR / "isdnews-hub"
DB_PATH = NEWS_DIR / "db.sqlite3"

def run_cmd(cmd, cwd=None, shell=True):
    try:
        subprocess.run(cmd, cwd=cwd, shell=shell, check=True)
    except subprocess.CalledProcessError:
        print(f"Error executing: {cmd}")
        sys.exit(1)

def run_django_script(script_content):
    temp_script = NEWS_DIR / "_temp_script.py"
    full_content = f"""
import os, sys, django
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'isdnews.settings')
django.setup()
{script_content}
"""
    temp_script.write_text(full_content, encoding='utf-8')
    try:
        is_win = sys.platform.startswith('win')
        py = str(NEWS_DIR / "venv" / ("Scripts" if is_win else "bin") / ("python.exe" if is_win else "python"))
        subprocess.check_call(f'"{py}" _temp_script.py', cwd=NEWS_DIR, shell=True)
    finally:
        if temp_script.exists(): temp_script.unlink()

def pick(title, options):
    print(f"\n=== {title} ===")
    print("(Use arrow keys/WASD to move, Enter to select)")
    current_idx = 0
    is_windows = sys.platform.startswith('win')
    if is_windows:
        import msvcrt
        def get_key():
            ch = msvcrt.getch()
            if ch in [b'\x00', b'\xe0']:
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
            old = termios.tcgetattr(fd)
            try:
                tty.setraw(sys.stdin.fileno())
                ch = sys.stdin.read(1)
                if ch == '\x1b':
                    ch2 = sys.stdin.read(2)
                    if ch2 == '[A': return 'up'
                    if ch2 == '[B': return 'down'
                if ch in ['\r', '\n']: return 'enter'
                if ch == 'w': return 'up'
                if ch == 's': return 'down'
            finally: termios.tcsetattr(fd, termios.TCSADRAIN, old)
            return None
    def show_menu(idx):
        for _ in range(len(options)): sys.stdout.write("\033[K")
        sys.stdout.write(f"\033[{len(options)}A")
        for i, opt in enumerate(options):
            if i == idx: print(f"\033[96m> {opt}\033[0m")
            else: print(f"  {opt}")
    for _ in range(len(options)): print("")
    while True:
        show_menu(current_idx)
        k = get_key()
        if k == 'up' and current_idx > 0: current_idx -= 1
        elif k == 'down' and current_idx < len(options) - 1: current_idx += 1
        elif k == 'enter': return options[current_idx]

def step_title(num, title):
    print(f"\n--- [Step {num}] {title} ---")

def configure_ai():
    step_title(4, "AI LLM Configuration")
    providers = ["ollama", "openai", "google", "anthropic", "openrouter"]
    provider = pick("Select AI Provider", providers)
    auth_methods = ["API Key"]
    if provider in ["google", "openai", "anthropic"]: auth_methods.append("OAuth 2.0")
    auth_method = pick(f"Authentication Method", auth_methods)
    
    config = {
        "AI_PROVIDER": provider,
        "AI_AUTH_METHOD": "oauth" if auth_method == "OAuth 2.0" else "apikey",
        "AI_MODEL": "qwen3:30b-a3b" if provider == "ollama" else "gpt-4o"
    }
    
    if config["AI_AUTH_METHOD"] == "apikey":
        if provider != "ollama":
            config["AI_API_KEY"] = input(f"Enter {provider.upper()} API Key: ").strip()
            config["AI_MODEL"] = input(f"Enter Model Name [default: {config['AI_MODEL']}]: ").strip() or config["AI_MODEL"]
    else:
        config["AI_CLIENT_ID"] = input("Enter Client ID: ").strip()
        config["AI_CLIENT_SECRET"] = input("Enter Client Secret: ").strip()
        config["AI_REFRESH_TOKEN"] = input("Enter Refresh Token: ").strip()
        config["AI_MODEL"] = input(f"Enter Model Name: ").strip()

    # Save to .env
    for env_path in [NEWS_DIR / ".env", HUB_DIR / ".env"]:
        if not env_path.exists(): continue
        lines = env_path.read_text().splitlines()
        new_lines = []
        updates = config.copy()
        if env_path.parent == HUB_DIR:
            updates.update({"CHAT_MODEL": config["AI_MODEL"], "DIGEST_MODEL": config["AI_MODEL"]})
        seen = set()
        for line in lines:
            if "=" not in line: new_lines.append(line); continue
            k = line.split("=")[0]
            if k in updates: new_lines.append(f"{k}={updates[k]}"); seen.add(k)
            else: new_lines.append(line)
        for k, v in updates.items():
            if k not in seen: new_lines.append(f"{k}={v}")
        env_path.write_text("\n".join(new_lines))
    print("✅ AI Configured.")

def configure_jobs():
    step_title(6, "Job Configuration")
    crawl_limit = input("Crawl Job - Articles per source [default: 10]: ").strip() or "10"
    crawl_interval = input("Crawl Job - Frequency in minutes [default: 5]: ").strip() or "5"
    
    ai_limit = input("AI Job - Articles per run [default: 5]: ").strip() or "5"
    ai_interval = input("AI Job - Frequency in minutes [default: 30]: ").strip() or "30"
    
    script = f"""
from collector.models import JobConfig
from django_celery_beat.models import PeriodicTask, IntervalSchedule
import json

# Update JobConfig
JobConfig.objects.update_or_create(job_type='crawl', defaults={{'enabled': True, 'limit': {crawl_limit}}})
JobConfig.objects.update_or_create(job_type='openrouter', defaults={{'enabled': True, 'limit': {ai_limit}}})

# Update Schedules in DB
c_int, _ = IntervalSchedule.objects.get_or_create(every={crawl_interval}, period=IntervalSchedule.MINUTES)
PeriodicTask.objects.update_or_create(
    name='run-crawl-job-db', 
    defaults={{'task': 'collector.tasks.collect_data_from_all_sources', 'interval': c_int, 'enabled': True}}
)

a_int, _ = IntervalSchedule.objects.get_or_create(every={ai_interval}, period=IntervalSchedule.MINUTES)
PeriodicTask.objects.update_or_create(
    name='run-openrouter-job-db', 
    defaults={{'task': 'collector.tasks.process_openrouter_job', 'interval': a_int, 'enabled': True}}
)
"""
    run_django_script(script)
    print(f"✅ Jobs configured: Crawl every {crawl_interval}m (limit {crawl_limit}), AI every {ai_interval}m (limit {ai_limit})")

def configure_telegram_bot():
    step_title(3, "Telegram Bot Configuration")
    token = input("Enter Telegram Bot Token: ").strip()
    chat_id = input("Enter Default Chat ID: ").strip()
    if token:
        for env_path in [NEWS_DIR / ".env", HUB_DIR / ".env"]:
            if not env_path.exists(): continue
            lines = env_path.read_text().splitlines()
            new_lines = []
            updates = {"TELEGRAM_BOT_TOKEN": token, "TELEGRAM_CHAT_ID": chat_id}
            seen = set()
            for line in lines:
                if "=" not in line: new_lines.append(line); continue
                k = line.split("=")[0]
                if k in updates: new_lines.append(f"{k}={updates[k]}"); seen.add(k)
                else: new_lines.append(line)
            for k, v in updates.items():
                if k not in seen: new_lines.append(f"{k}={v}")
            env_path.write_text("\n".join(new_lines))
    print("✅ Telegram configured.")

def configure_telegram_per_team():
    print("\n--- 📱 Telegram Per-Team Configuration ---")
    is_win = sys.platform.startswith('win')
    py = str(NEWS_DIR / "venv" / ("Scripts" if is_win else "bin") / ("python.exe" if is_win else "python"))
    get_teams = "import os, sys, django, json; sys.path.append('.'); os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'isdnews.settings'); django.setup(); from collector.models import Team; print(json.dumps(list(Team.objects.all().values('code', 'name'))))"
    try:
        out = subprocess.check_output(f'"{py}" -c "{get_teams}"', cwd=NEWS_DIR, shell=True).decode()
        teams = json.loads(out.splitlines()[-1])
        if not teams: print("⚠️ No teams found."); return
        opt = [f"{t['name']} ({t['code']})" for t in teams]
        sel = pick("Select team", opt)
        code = sel.split('(')[1].split(')')[0]
        cid = input(f"Enter Chat ID for {code}: ").strip()
        if cid:
            run_django_script(f"from collector.models import Team, SystemConfig; team=Team.objects.get(code='{code}'); SystemConfig.objects.update_or_create(key='telegram_chat_id', team=team, defaults={{'value': '{cid}', 'key_type': 'webhook', 'is_active': True}})")
            print("✅ Updated.")
    except: print("❌ Error.")

def show_config():
    print("\n--- 🔍 Current Configuration ---")
    env = NEWS_DIR / ".env"
    if env.exists():
        c = dict(l.split("=",1) for l in env.read_text().splitlines() if "=" in l)
        print(f"🤖 AI Provider : {c.get('AI_PROVIDER','N/A').upper()}")
        print(f"📦 AI Model    : {c.get('AI_MODEL','N/A')}")
        print(f"🔑 Auth Method : {c.get('AI_AUTH_METHOD','apikey')}")
        print(f"💾 Using Redis : {c.get('USE_REDIS','True')}")
    else: print("No config found.")

def install():
    print("🚀 ISD Ecosystem Smart Installer")
    is_win = sys.platform.startswith('win')
    
    # Kích hoạt ANSI cho Windows
    if is_win:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)

    mode = "fresh"
    if DB_PATH.exists():
        print(f"\n⚠️ Existing database found.")
        mode = "resume" if pick("Installation Mode", ["Resume (Keep data)", "Fresh Install (Wipe all)"]) == "Resume (Keep data)" else "fresh"
        
        if mode == "fresh":
            print("🛑 Stopping all services to release file locks...")
            try: subprocess.run("pm2 stop all", shell=True, capture_output=True)
            except: pass
            
            print("🗑️ Wiping existing data...")
            import shutil
            import time
            
            # Thử xóa venv và db nhiều lần nếu bị lock
            for _ in range(3):
                try:
                    if DB_PATH.exists(): DB_PATH.unlink()
                    venv_dir = NEWS_DIR / "venv"
                    if venv_dir.exists(): shutil.rmtree(venv_dir)
                    break
                except Exception as e:
                    print(f"⏳ Waiting for processes to release files... ({e})")
                    time.sleep(2)
            
            if DB_PATH.exists():
                print("❌ Fatal: Could not delete database. Please close all CMD windows and try again.")
                return

    # Step 1: Environment Setup
    python_cmds = ["python", "py", "python3"]
    py_cmd = "python"
    for cmd in python_cmds:
        try:
            subprocess.run(f"{cmd} --version", shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            py_cmd = cmd; break
        except: continue

    use_redis = "True" if input("❓ Use Redis? (y/N) [default: n]: ").strip().lower() == 'y' else "False"
    
    if NEWS_DIR.exists():
        (NEWS_DIR/"logs").mkdir(parents=True, exist_ok=True)
        venv_dir = NEWS_DIR / "venv"
        if mode == "fresh":
            print("📦 Creating virtual environment...")
            run_cmd(f"{py_cmd} -m venv venv", cwd=NEWS_DIR)
        
        exec_p = "Scripts" if is_win else "bin"
        pip = venv_dir / exec_p / "pip"
        python = venv_dir / exec_p / "python"
        
        print("📥 Installing Python dependencies...")
        run_cmd(f'"{pip}" install -r requirements.txt', cwd=NEWS_DIR)
        run_cmd(f'"{python}" -m playwright install chromium', cwd=NEWS_DIR)
        
        if not (NEWS_DIR / ".env").exists() or mode == "fresh":
            example = NEWS_DIR / ".env.example"
            lines = example.read_text().splitlines() if example.exists() else []
            new_lines = []
            for l in lines:
                if l.startswith("USE_REDIS="): new_lines.append(f"USE_REDIS={use_redis}")
                elif l.startswith("CELERY_BROKER_URL=") and use_redis == "False": new_lines.append(f"# {l}")
                elif l.startswith("DEBUG="): new_lines.append("DEBUG=True")
                else: new_lines.append(l)
            (NEWS_DIR / ".env").write_text("\n".join(new_lines))
        
        run_cmd(f'"{python}" manage.py migrate', cwd=NEWS_DIR)
        run_cmd(f'"{python}" manage.py collectstatic --noinput', cwd=NEWS_DIR)

    if HUB_DIR.exists():
        (HUB_DIR / "data").mkdir(parents=True, exist_ok=True)
        run_cmd("npm install", cwd=HUB_DIR)
        if not (HUB_DIR / ".env").exists() or mode == "fresh":
            db_rel = str(NEWS_DIR/'db.sqlite3').replace('\\','/')
            (HUB_DIR / ".env").write_text(f"PORT=8787\nSOURCE_DB_PATH={db_rel}\nHUB_DB_PATH=./data/hub.sqlite3\n")

    if mode == "fresh":
        step_title(2, "Admin Account")
        run_cmd(f'"{python}" manage.py createsuperuser', cwd=NEWS_DIR)
        configure_telegram_bot()
        configure_ai()
        step_title(5, "Initial Teams & Sources")
        while True:
            t_name = input("\nTeam Name (e.g. Developer) [Enter to finish]: ").strip()
            if not t_name: break
            t_code = input(f"Team Code for '{t_name}': ").strip().lower()
            
            default_p = "You are a Senior Engineering Coach, specializing in developer interview prep. Focus on production, trade-offs, and debugging. Response in Vietnamese."
            print(f"Default Prompt: {default_p}")
            t_prompt = input("Custom System Prompt [Enter for default]: ").strip() or default_p
            
            t_chat = input(f"Telegram Chat ID for '{t_code}' [optional]: ").strip()
            
            script = f"from collector.models import Team, SystemConfig; team, _ = Team.objects.get_or_create(code='{t_code}', defaults={{'name': '{t_name}', 'system_prompt': \"\"\"{t_prompt}\"\"\", 'is_active': True}}); \nif not _: team.system_prompt = \"\"\"{t_prompt}\"\"\"; team.save(); \nif '{t_chat}': SystemConfig.objects.update_or_create(key='telegram_chat_id', team=team, defaults={{'value': '{t_chat}', 'key_type': 'webhook', 'is_active': True}})"
            run_django_script(script)
            while True:
                s_url = input(f"  RSS URL for '{t_name}' [Enter to finish]: ").strip()
                if not s_url: break
                s_name = input(f"  Source Name: ").strip()
                run_django_script(f"from collector.models import Team, Source; team=Team.objects.get(code='{t_code}'); Source.objects.get_or_create(url='{s_url}', defaults={{'source': '{s_name}', 'type': 'rss', 'team': team, 'is_active': True}})")
        configure_jobs()

    print("\n✅ Setup complete! Use 'isd start' to run.")

def start():
    is_win = sys.platform.startswith('win')
    
    # Sử dụng os.path để chuẩn hoá đường dẫn Windows/Linux
    import os
    
    venv_bin = "Scripts" if is_win else "bin"
    py_exec = "python.exe" if is_win else "python"
    
    # Đường dẫn tuyệt đối chuẩn xác
    py_path_raw = NEWS_DIR / "venv" / venv_bin / py_exec
    
    # Kiểm tra sự tồn tại của môi trường ảo trước khi chạy
    if not py_path_raw.exists():
        print(f"❌ Lỗi: Không tìm thấy môi trường ảo tại: {py_path_raw}")
        print("👉 Sếp vui lòng chạy lệnh 'isd install' trước để khởi tạo môi trường nhé!")
        return

    # Chuẩn hoá đường dẫn cho file cấu hình JS (Sử dụng forward slashes cho PM2 trên Win là an toàn nhất)
    py_path = str(py_path_raw).replace("\\", "/")
    news_dir_path = str(NEWS_DIR).replace("\\", "/")
    hub_dir_path = str(HUB_DIR).replace("\\", "/")
    
    pool_flag = " --pool=solo" if is_win else ""
    
    print(f"▶️ Đang khởi động các dịch vụ từ: {news_dir_path}")
    
    try:
        subprocess.run("pm2 --version", shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        print("❌ Error: 'pm2' not found. Install it: npm install -g pm2"); return

    ecosystem_content = f"""
module.exports = {{
  apps : [
    {{
      name: 'isd-core',
      script: 'manage.py',
      cwd: '{news_dir_path}',
      interpreter: '{py_path}',
      args: 'runserver 127.0.0.1:8000',
      windowsHide: true,
      env: {{ PYTHONPATH: '{news_dir_path}' }}
    }},
    {{
      name: 'isd-worker',
      script: '{py_path}',
      cwd: '{news_dir_path}',
      args: '-m celery -A isdnews worker --loglevel=info{pool_flag}',
      windowsHide: true,
      env: {{ PYTHONPATH: '{news_dir_path}' }}
    }},
    {{
      name: 'isd-beat',
      script: '{py_path}',
      cwd: '{news_dir_path}',
      args: '-m celery -A isdnews beat --loglevel=info',
      windowsHide: true,
      env: {{ PYTHONPATH: '{news_dir_path}' }}
    }},
    {{
      name: 'isd-api',
      script: 'apps/api/server.js',
      cwd: '{hub_dir_path}',
      windowsHide: true
    }}
  ]
}};"""
    (BASE_DIR / "ecosystem.config.js").write_text(ecosystem_content, encoding='utf-8')
    
    run_cmd("pm2 start ecosystem.config.js", cwd=BASE_DIR)
    run_cmd("pm2 save")
    print("\n✅ Hệ thống đã được khởi động! Sếp dùng 'pm2 status' để kiểm tra nhé.")
    run_cmd("pm2 start ecosystem.config.js", cwd=BASE_DIR)
    run_cmd("pm2 save")
    print("\n✅ Started.")

def stop(): run_cmd("pm2 stop all || true", cwd=BASE_DIR)
def restart(): stop(); start()
def status(): run_cmd("pm2 list | grep isd || echo 'None.'")

def usage():
    print("""
ISD Ecosystem CLI v1.5.0
Usage:
  isd install             - Setup or Resume installation
  isd admin               - Create Admin account
  isd config ai           - Configure AI Provider
  isd config telegram     - Configure Team Group IDs
  isd config telegram-bot - Configure Main Bot Token
  isd config show         - Show current config
  isd start/stop/restart  - Manage services
  isd status              - Show status
    """)

if __name__ == "__main__":
    if len(sys.argv) < 2: usage(); sys.exit(0)
    cmd = sys.argv[1]
    if cmd == "install": install()
    elif cmd == "admin": 
        is_win = sys.platform.startswith('win')
        py = str(NEWS_DIR / "venv" / ("Scripts" if is_win else "bin") / ("python.exe" if is_win else "python"))
        run_cmd(f'"{py}" manage.py createsuperuser', cwd=NEWS_DIR)
    elif cmd in ["start", "stop", "restart", "status"]: globals()[cmd]()
    elif cmd == "config" and len(sys.argv) > 2:
        sub = sys.argv[2]
        if sub == "ai": configure_ai()
        elif sub == "telegram": configure_telegram_per_team()
        elif sub == "telegram-bot": configure_telegram_bot()
        elif sub == "show": show_config()
    else: usage()
