# Gunicorn configuration file
bind = "0.0.0.0:1997"
workers = 3
timeout = 120
keepalive = 5
errorlog = "logs/gunicorn-error.log"
accesslog = "logs/gunicorn-access.log"
loglevel = "info"
