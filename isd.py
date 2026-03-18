#!/usr/bin/env python3
import os
import sys
import subprocess
from pathlib import Path

# ISD Ecosystem CLI - v1.2.0
# Distribution Version (English/ASCII only for robustness)

BASE_DIR = Path(__file__).parent.absolute()
NEWS_DIR = BASE_DIR / "isdnews"
HUB_DIR = BASE_DIR / "isdnews-hub"

def run_cmd(cmd, cwd=None, shell=True):
    try:
        subprocess.run(cmd, cwd=cwd, shell=shell, check=True)
    except subprocess.CalledProcessError:
        print(f"Error executing: {cmd}")
        sys.exit(1)

def install():
    print(" Installing ISD Ecosystem...")
    is_windows = sys.platform.startswith('win')
    
    # Ask for Redis
    use_redis_input = input(" Do you want to use Redis? (Y/n): ").strip().lower()
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
        print(f" Configuring Pipeline (isdnews) using {py_cmd}...")
        
        logs_dir = NEWS_DIR / "logs"
        if not logs_dir.exists():
            logs_dir.mkdir(parents=True, exist_ok=True)
            print(" Created logs directory.")

        venv_dir = NEWS_DIR / "venv"
        run_cmd(f"{py_cmd} -m venv venv", cwd=NEWS_DIR)
        
        if is_windows:
            pip_path = venv_dir / "Scripts" / "pip.exe"
            python_path = venv_dir / "Scripts" / "python.exe"
        else:
            pip_path = venv_dir / "bin" / "pip"
            python_path = venv_dir / "bin" / "python"
        
        print(" Installing Python dependencies...")
        run_cmd(f'"{pip_path}" install -r requirements.txt', cwd=NEWS_DIR)
        
        print(" Installing Playwright Browser...")
        run_cmd(f'"{python_path}" -m playwright install chromium', cwd=NEWS_DIR)
        
        if not (NEWS_DIR / ".env").exists():
            if (NEWS_DIR / ".env.example").exists():
                lines = (NEWS_DIR / ".env.example").read_text().splitlines()
                new_lines = []
                for line in lines:
                    if line.startswith("USE_REDIS="):
                        new_lines.append(f"USE_REDIS={use_redis}")
                    elif line.startswith("DEBUG="):
                        new_lines.append("DEBUG=True")
                    elif line.startswith("CELERY_BROKER_URL=") and use_redis == "False":
                        new_lines.append(f"# {line} (Disabled for No-Redis mode)")
                    else:
                        new_lines.append(line)
                (NEWS_DIR / ".env").write_text("\n".join(new_lines))
                print(f" Created .env file (USE_REDIS={use_redis})")
            else:
                (NEWS_DIR / ".env").write_text(f"DEBUG=True\nUSE_REDIS={use_redis}\nAI_PROVIDER=ollama\nOLLAMA_BASE_URL=http://127.0.0.1:11434\n")
        
        print(" Migrating Database...")
        run_cmd(f'"{python_path}" manage.py migrate', cwd=NEWS_DIR)
        print(" Collecting static files...")
        run_cmd(f'"{python_path}" manage.py collectstatic --noinput', cwd=NEWS_DIR)
    
    # Setup Hub
    if HUB_DIR.exists():
        print(" Configuring Dashboard (isdnews-hub)...")
        hub_data_dir = HUB_DIR / "data"
        if not hub_data_dir.exists():
            hub_data_dir.mkdir(parents=True, exist_ok=True)
            print(" Created data directory for Hub.")

        run_cmd("npm install", cwd=HUB_DIR)
        if not (HUB_DIR / ".env").exists():
            db_path = str(NEWS_DIR / "db.sqlite3").replace("\\", "/")
            hub_db = str(HUB_DIR / "data" / "hub.sqlite3").replace("\\", "/")
            env_content = f"PORT=8787\nSOURCE_DB_PATH={db_path}\nHUB_DB_PATH={hub_db}\nLLM_BASE_URL=http://127.0.0.1:11434\n"
            (HUB_DIR / ".env").write_text(env_content)

    print("\n Setup complete! Use 'isd start' to run the system.")

def start():
    print(" Starting ISD Services...")
    is_windows = sys.platform.startswith('win')
    
    try:
        subprocess.run("pm2 --version", shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        print(" Error: 'pm2' command not found.")
        print(" Please install PM2: npm install -g pm2")
        return

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
    {{
      name: 'isd-core',
      script: 'manage.py',
      cwd: '{news_dir_esc}',
      interpreter: '{py_path}',
      args: 'runserver 0.0.0.0:8000',
      autorestart: true,
      watch: false,
      windowsHide: true,
      env: {{
        PYTHONPATH: '{news_dir_esc}'
      }}
    }},
    {{
      name: 'isd-worker',
      script: '{py_path}',
      cwd: '{news_dir_esc}',
      args: '-m celery -A isdnews worker --loglevel=info{pool_flag}',
      autorestart: true,
      watch: false,
      max_memory_restart: '1G',
      windowsHide: true,
      env: {{
        PYTHONPATH: '{news_dir_esc}'
      }}
    }},
    {{
      name: 'isd-beat',
      script: '{py_path}',
      cwd: '{news_dir_esc}',
      args: '-m celery -A isdnews beat --loglevel=info',
      autorestart: true,
      watch: false,
      windowsHide: true,
      env: {{
        PYTHONPATH: '{news_dir_esc}'
      }}
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
    run_cmd(f"pm2 start ecosystem.config.js", cwd=BASE_DIR)
    run_cmd("pm2 save")
    print("\n Services started! Use 'pm2 status' to check.")

def stop():
    print(" Stopping ISD Services...")
    run_cmd("pm2 stop isd-worker isd-beat isd-api isd-core || true")

def restart():
    print(" Restarting ISD Services...")
    stop()
    start()

def status():
    run_cmd("pm2 list | grep isd || echo 'No active services.'")

def set_model(model_name):
    print(f" Switching model to: {model_name}")
    env_path = NEWS_DIR / ".env"
    if env_path.exists():
        lines = env_path.read_text().splitlines()
        new_lines = [l if not l.startswith("AI_MODEL=") else f"AI_MODEL={model_name}" for l in lines]
        if not any(l.startswith("AI_MODEL=") for l in lines):
            new_lines.append(f"AI_MODEL={model_name}")
        env_path.write_text("\n".join(new_lines))
    restart()

def create_superuser():
    print(" Creating Admin Account (Superuser)...")
    if NEWS_DIR.exists():
        is_windows = sys.platform.startswith('win')
        python_path = NEWS_DIR / "venv" / ("Scripts" if is_windows else "bin") / ("python.exe" if is_windows else "python")
        run_cmd(f'"{python_path}" manage.py createsuperuser', cwd=NEWS_DIR)

def usage():
    print("""
ISD Ecosystem CLI
Usage:
  isd install      - Full environment setup (venv, npm, db)
  isd admin        - Create Admin superuser account
  isd start        - Run all services via PM2
  isd stop         - Stop all services
  isd restart      - Restart all services
  isd status       - Show service status
  isd model <name> - Switch AI model (e.g. isd model qwen3:30b)
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
