from django.core.exceptions import ImproperlyConfigured

from .base import *

DEBUG = False

if SECRET_KEY == INSECURE_DEV_SECRET_KEY or len(SECRET_KEY) < 32:
    # The secret key signs JWTs and derives the at-rest encryption key for SMTP
    # credentials; a known/short key lets anyone forge admin tokens.
    raise ImproperlyConfigured('Set a strong DJANGO_SECRET_KEY (>= 32 chars) for production.')

if '*' in ALLOWED_HOSTS and not env_flag('ALLOW_ANY_HOST', default=False):
    ALLOWED_HOSTS = [h for h in ALLOWED_HOSTS if h != '*']

# Demo logins (well-known passwords) are off unless explicitly enabled.
DEMO_ACCOUNTS_ENABLED = env_flag('ENABLE_DEMO_ACCOUNTS', default=False)

# Enforce HTTPS (TLS terminates at the platform proxy, e.g. Railway)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = env_flag('SECURE_SSL_REDIRECT', default=True)
# Platform health checks hit the container over plain HTTP.
SECURE_REDIRECT_EXEMPT = [r'^health/?$', r'^ready/?$', r'^api/health/?$']
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = int(os.environ.get('SECURE_HSTS_SECONDS', 31536000))
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = env_flag('SECURE_HSTS_PRELOAD', default=False)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'

# Email backend for production (configure EMAIL_HOST / EMAIL_HOST_USER / EMAIL_HOST_PASSWORD)
EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'localhost')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = env_flag('EMAIL_USE_TLS', default=True)
EMAIL_USE_SSL = env_flag('EMAIL_USE_SSL', default=False)
EMAIL_TIMEOUT = 15

# Session
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_HTTPONLY = True

# Logging: stdout only (container platforms collect it). Never log request bodies.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {'format': '%(asctime)s %(levelname)s %(name)s %(message)s'},
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'standard'},
    },
    'root': {'handlers': ['console'], 'level': os.environ.get('LOG_LEVEL', 'INFO')},
    'loggers': {
        'django.request': {'handlers': ['console'], 'level': 'WARNING', 'propagate': False},
    },
}
