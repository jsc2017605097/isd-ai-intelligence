from .settings import *

DEBUG = True
ALLOWED_HOSTS = []

# Database cho development
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Celery configuration cho development
CELERY_BROKER_URL = 'redis://default:4x5g4ml4ajnj4HehdDIzZ77z7dNGOtPM@redis-17407.c275.us-east-1-4.ec2.redns.redis-cloud.com:17407/0'
CELERY_RESULT_BACKEND = 'redis://default:4x5g4ml4ajnj4HehdDIzZ77z7dNGOtPM@redis-17407.c275.us-east-1-4.ec2.redns.redis-cloud.com:17407/0'
