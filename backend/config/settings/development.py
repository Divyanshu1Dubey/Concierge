from .base import *

DEBUG = True
DEMO_ACCOUNTS_ENABLED = env_flag('ENABLE_DEMO_ACCOUNTS', default=True)
if 'testserver' not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append('testserver')

# Debug toolbar disabled in development to prevent UI interference with widget and demo pages
# if needed, can be toggled via DJANGO_ENABLE_DEBUG_TOOLBAR=True
if os.environ.get('DJANGO_ENABLE_DEBUG_TOOLBAR', 'False').lower() in ('true', '1'):
    INSTALLED_APPS += ['debug_toolbar']
    MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware']

INTERNAL_IPS = [
    '127.0.0.1',
    'localhost',
]

# Email: configured in base.py (EMAIL_* or SMTP_* from the environment / .env).
# Without credentials, messages are printed to the console instead of being sent.

# Allow all origins in dev
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOWED_ORIGINS = ['http://localhost:3000', 'http://localhost:3001', 'http://localhost:5173', 'http://localhost:5174']

# Local-friendly cache / channels (no Redis required)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'heyjarvis-local',
    }
}
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    },
}
