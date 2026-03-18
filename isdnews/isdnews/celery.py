from __future__ import absolute_import, unicode_literals
import os
from pathlib import Path
from celery import Celery
from celery.schedules import crontab
from django.conf import settings

# Load environment variables from .env file
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file
env_path = BASE_DIR / '.env'
if env_path.exists():
    load_dotenv(env_path)
    print(f"[Celery] Loaded .env file from {env_path}")
else:
    print(f"[Celery] .env file not found at {env_path}")

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'isdnews.settings')

app = Celery('isdnews')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()

# Cấu hình Celery Beat
app.conf.beat_schedule = {
    'run-crawl-job': {
        'task': 'collector.tasks.collect_data_from_all_sources',
        'schedule': crontab(minute='*/5'),  # Chạy mỗi 5 phút
    },
    'run-openrouter-job': {
        'task': 'collector.tasks.process_openrouter_job',
        'schedule': crontab(minute='*/30'),  # Chạy mỗi 30 phút
    },
}

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}') 