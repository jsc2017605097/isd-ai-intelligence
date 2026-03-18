import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'isdnews.settings')
app = Celery('isdnews')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

app.conf.beat_schedule = {
    'run-crawl-job': {
        'task': 'collector.tasks.collect_data_from_all_sources',
        'schedule': crontab(minute='*/5'),
    },
    'run-openrouter-job': {
        'task': 'collector.tasks.process_openrouter_job',
        'schedule': crontab(minute='*/30'),
    },
}
