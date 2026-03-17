"""
WSGI config for isdnews project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

# Sử dụng settings_prod trên môi trường production
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'isdnews.settings_prod')

application = get_wsgi_application()
