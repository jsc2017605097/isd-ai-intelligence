#!/usr/bin/env python3
import os
import sys
import subprocess
import json
from pathlib import Path

# ISD Ecosystem CLI - v1.4.0
# Distribution Version (Multi-Vendor & OAuth Support)

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
    """Simple cross-platform arrow-key menu selector"""
    import curses
    
    def _pick(stdscr):
        curses.curs_set(0)
        current_row = 0
        
        while True:
            stdscr.clear()
            stdscr.addstr(0, 0, f"=== {title} ===")
            stdscr.addstr(1, 0, "(Use arrow keys to move, Enter to select)")
            
            for idx, option in enumerate(options):
                if idx == current_row:
                    stdscr.addstr(idx + 3, 0, f"> {option}", curses.A_REVERSE)
                else:
                    stdscr.addstr(idx + 3, 0, f"  {option}")
            
            key = stdscr.getch()
            
            if key == curses.KEY_UP and current_row > 0:
                current_row -= 1
            elif key == curses.KEY_DOWN and current_row < len(options) - 1:
                current_row += 1
            elif key == ord('\n'):
                return options[current_row]
    
    # Standard terminal input fallback if curses fails
    try:
        return curses.wrapper(_pick)
    except:
        print(f"\n{title}")
        for i, o in enumerate(options):
            print(f"{i+1}. {o}")
        c = input(f"Select [1-{len(options)}]: ").strip()
        return options[int(c)-1] if c.isdigit() and 1 <= int(c) <= len(options) else options[0]

def configure_ai():
    print("\n--- 🤖 AI Configuration ---")
    
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
        
        # Prepare mapping for current env
        updates = config_data.copy()
        if env_path.parent == HUB_DIR:
            # Hub uses some specific naming
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

def install():
    print("🚀 Installing ISD Ecosystem...")
    is_windows = sys.platform.startswith('win')
    
    # Ask for Redis
    use_redis_input = input("❓ Do you want to use Redis? (Y/n): ").strip().lower()
    use_redis = "True" if use_redis_input != 'n' else "False"

    # Find python
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
        
        # Configure AI during install
        configure_ai()
        
        print("🗄️ Migrating Database...")
        run_cmd(f'"{python_path}" manage.py migrate', cwd=NEWS_DIR)
        print("📁 Collecting static files...")
        run_cmd(f'"{python_path}" manage.py collectstatic --noinput', cwd=NEWS_DIR)
    
    # Setup Hub
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
    
    if is_windows:
        py_path = f"{news_dir_esc}\\\\venv\\\\Scripts\\\\python.exe"
        pool_flag = " --pool=solo"
    else:
        py_path = f"{news_dir_esc}/venv/bin/python"
        pool_flag = ""

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

def usage():
    print("""
ISD Ecosystem CLI
Usage:
  isd install      - Full environment setup
  isd config ai    - Configure AI LLM Provider (Multi-Vendor + OAuth)
  isd admin        - Create Admin account
  isd start        - Run services
  isd stop         - Stop services
  isd restart      - Restart services
  isd status       - Show status
    """)

if __name__ == "__main__":
    if len(sys.argv) < 2: usage(); sys.exit(0)
    cmd = sys.argv[1]
    if cmd == "install": install()
    elif cmd == "admin": 
        is_win = sys.platform.startswith('win')
        py = str(NEWS_DIR / "venv" / ("Scripts" if is_win else "bin") / ("python.exe" if is_win else "python"))
        run_cmd(f'"{py}" manage.py createsuperuser', cwd=NEWS_DIR)
    elif cmd == "config" and len(sys.argv) > 2 and sys.argv[2] == "ai": configure_ai()
    elif cmd == "start": start()
    elif cmd == "stop": stop()
    elif cmd == "restart": restart()
    elif cmd == "status": status()
    else: usage()
