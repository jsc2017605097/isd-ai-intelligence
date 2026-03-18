#!/usr/bin/env python3
import os
import sys
import subprocess
import json
from pathlib import Path

# ISD Ecosystem CLI - v1.3.0
# Distribution Version (Multi-Vendor AI Support)

BASE_DIR = Path(__file__).parent.absolute()
NEWS_DIR = BASE_DIR / "isdnews"
HUB_DIR = BASE_DIR / "isdnews-hub"

def run_cmd(cmd, cwd=None, shell=True):
    try:
        subprocess.run(cmd, cwd=cwd, shell=shell, check=True)
    except subprocess.CalledProcessError:
        print(f"Error executing: {cmd}")
        sys.exit(1)

def configure_ai():
    print("\n--- 🤖 AI Configuration (OpenClaw Style) ---")
    providers = ["ollama", "openai", "google", "anthropic", "openrouter"]
    for i, p in enumerate(providers):
        print(f"{i+1}. {p}")
    
    choice = input("Select AI Provider [1-5] (default: 1): ").strip()
    provider = providers[int(choice)-1] if choice.isdigit() and 1 <= int(choice) <= len(providers) else "ollama"
    
    api_key = ""
    base_url = ""
    model = "qwen3:30b-a3b" # Default for ollama
    
    if provider != "ollama":
        api_key = input(f"Enter {provider.upper()} API Key: ").strip()
        model = input(f"Enter Model Name (e.g. gpt-4o, claude-3-5-sonnet...): ").strip()
        if provider == "openai":
            base_url = input("Enter Base URL (optional, press Enter for default): ").strip()
    
    # Update BOTH .env files
    for env_path in [NEWS_DIR / ".env", HUB_DIR / ".env"]:
        if not env_path.parent.exists(): continue
        lines = env_path.read_text().splitlines() if env_path.exists() else []
        new_lines = []
        
        current_keys = keys_to_update.copy()
        if env_path.parent == HUB_DIR:
            # Map News keys to Hub expected keys
            current_keys = {
                "AI_PROVIDER": provider,
                "AI_API_KEY": api_key,
                "LLM_BASE_URL": base_url if base_url else (OLLAMA_BASE_URL if provider == "ollama" else ""),
                "CHAT_MODEL": model,
                "DIGEST_MODEL": model,
                "AI_MODEL": model,
                "LLM_API_STYLE": "openai" if provider != "ollama" else "ollama"
            }

        seen_keys = set()
        for line in lines:
            matched = False
            for k, v in current_keys.items():
                if line.startswith(f"{k}="):
                    new_lines.append(f"{k}={v}")
                    seen_keys.add(k)
                    matched = True
                    break
            if not matched: new_lines.append(line)
                
        for k, v in current_keys.items():
            if k not in seen_keys: new_lines.append(f"{k}={v}")
                
        env_path.write_text("\n".join(new_lines))
    
    print(f"✅ AI Provider set to {provider.upper()} for both Pipeline and Dashboard.")

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
    
    # Setup Hub
    if HUB_DIR.exists():
        print("📦 Configuring Dashboard (isdnews-hub)...")
        if not (HUB_DIR / "data").exists(): (HUB_DIR / "data").mkdir(parents=True, exist_ok=True)
        run_cmd("npm install", cwd=HUB_DIR)
        if not (HUB_DIR / ".env").exists():
            env_content = f"PORT=8787\nSOURCE_DB_PATH={str(NEWS_DIR/'db.sqlite3').replace('\\','/')}\nLLM_BASE_URL=http://127.0.0.1:11434\n"
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
    py_path = str(NEWS_DIR / ("Scripts" if is_windows else "bin") / "python").replace("\\", "\\\\")
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

def usage():
    print("""
ISD Ecosystem CLI
Usage:
  isd install      - Full environment setup
  isd config ai    - Configure AI LLM Provider
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
        py = str(NEWS_DIR / ("Scripts" if sys.platform.startswith('win') else "bin") / "python")
        run_cmd(f'"{py}" manage.py createsuperuser', cwd=NEWS_DIR)
    elif cmd == "config" and len(sys.argv) > 2 and sys.argv[2] == "ai": configure_ai()
    elif cmd == "start": start()
    elif cmd == "stop": stop()
    elif cmd == "restart": restart()
    elif cmd == "status": status()
    else: usage()
