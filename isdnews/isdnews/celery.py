import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'isdnews.settings')
app = Celery('isdnews')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Job schedules are now managed via Database Scheduler (Django Admin)
# Configured during 'isd install' or manually in Admin panel.
app.conf.beat_schedule = {}
