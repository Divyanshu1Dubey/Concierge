from .base import *

DEBUG = False
DEMO_ACCOUNTS_ENABLED = False
ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    'DEFAULT_THROTTLE_RATES': {
        'login': '1000/min', 'auth': '1000/min', 'widget': '1000/min', 'widget_submit': '1000/min',
    },
}
CHANNEL_LAYERS = {'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}}

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

CELERY_TASK_ALWAYS_EAGER = True
CELERY_BROKER_URL = 'memory://'
CELERY_RESULT_BACKEND = 'cache+memory://'

PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
EMAIL_ASYNC = False
AI_PROVIDER = 'none'
GEMINI_API_KEY = GROQ_API_KEY = OPENAI_API_KEY = ANTHROPIC_API_KEY = ''
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}
