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

# Email Configuration: Support both SMTP (when credentials configured) and console fallback
EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True').lower() in ('true', '1')
EMAIL_USE_SSL = os.environ.get('EMAIL_USE_SSL', 'False').lower() in ('true', '1')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'HeyJarvis Concierge <noreply@heyjarvis.ai>')

# Automatically switch to real SMTP if credentials are provided in .env
if EMAIL_HOST_USER and EMAIL_HOST_PASSWORD and EMAIL_BACKEND == 'django.core.mail.backends.console.EmailBackend':
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'

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
