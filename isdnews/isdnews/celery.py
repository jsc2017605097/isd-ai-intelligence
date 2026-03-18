import os
from celery import Celery
from celery.schedules import crontab
from pathlib import Path

# Load environment variables
try:
    from dotenv import load_dotenv
    BASE_DIR = Path(__file__).resolve().parent.parent
    load_dotenv(os.path.join(BASE_DIR, '.env'))
except ImportError:
    pass

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'isdnews.settings')
app = Celery('isdnews')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Job schedules are now managed via Database Scheduler (Django Admin)
# Configured during 'isd install' or manually in Admin panel.
app.conf.beat_schedule = {}
