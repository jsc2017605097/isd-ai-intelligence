module.exports = {
  apps: [
    {
      name: 'isdnews-gunicorn',
      script: '/home/khiemtv/sources/isdnews/venv/bin/gunicorn',
      args: '--access-logfile - --workers 3 --bind 0.0.0.0:8000 isdnews.wsgi:application',
      cwd: '/home/khiemtv/sources/isdnews',
      interpreter: 'none',
      autorestart: true,
      watch: false,
      env: {
        DJANGO_SETTINGS_MODULE: 'isdnews.settings'
      }
    },
    {
      name: 'isdnews-worker',
      script: '/home/khiemtv/sources/isdnews/venv/bin/celery',
      args: '-A isdnews worker --loglevel=INFO --logfile=/home/khiemtv/sources/isdnews/logs/celery_worker.log',
      cwd: '/home/khiemtv/sources/isdnews',
      interpreter: 'none',
      autorestart: true,
      watch: false,
      env: {
        DJANGO_SETTINGS_MODULE: 'isdnews.settings'
      }
    },
    {
      name: 'isdnews-beat',
      script: '/home/khiemtv/sources/isdnews/venv/bin/celery',
      args: '-A isdnews beat --loglevel=INFO --logfile=/home/khiemtv/sources/isdnews/logs/celery_beat.log',
      cwd: '/home/khiemtv/sources/isdnews',
      interpreter: 'none',
      autorestart: true,
      watch: false,
      env: {
        DJANGO_SETTINGS_MODULE: 'isdnews.settings'
      }
    }
  ]
};
