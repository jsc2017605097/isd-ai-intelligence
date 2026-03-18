try:
    from .celery import app as celery_app
    __all__ = ('celery_app',)
except Exception:
    # Fail silently or log if celery cannot be loaded (e.g. on restricted windows env)
    pass
