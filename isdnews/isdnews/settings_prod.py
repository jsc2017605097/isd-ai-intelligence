from .settings import *

DEBUG = False
ALLOWED_HOSTS = ['isdnews.telehub.vn']  # Thay thế bằng domain thực tế của bạn
CSRF_TRUSTED_ORIGINS = ['https://isdnews.telehub.vn']
# Security settings
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Static files
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATIC_URL = '/static/'
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, "collector/static"),
]

# Celery configuration cho production
CELERY_BROKER_URL = 'redis://default:4x5g4ml4ajnj4HehdDIzZ77z7dNGOtPM@redis-17407.c275.us-east-1-4.ec2.redns.redis-cloud.com:17407/0'
CELERY_RESULT_BACKEND = 'redis://default:4x5g4ml4ajnj4HehdDIzZ77z7dNGOtPM@redis-17407.c275.us-east-1-4.ec2.redns.redis-cloud.com:17407/0'

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': '/home/bsvdev/var/log/django/error.log',
        },
        'console': {
            'level': 'ERROR',
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file', 'console'],
            'level': 'ERROR',
            'propagate': True,
        },
        'celery': {
            'handlers': ['file', 'console'],
            'level': 'ERROR',
            'propagate': True,
        },
    },
}
