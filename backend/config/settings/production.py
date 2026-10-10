from django.core.exceptions import ImproperlyConfigured

from .base import *

DEBUG = False

if SECRET_KEY == INSECURE_DEV_SECRET_KEY or len(SECRET_KEY) < 32:
    # The secret key signs JWTs and derives the at-rest encryption key for SMTP
    # credentials; a known/short key lets anyone forge admin tokens.
    raise ImproperlyConfigured('Set a strong DJANGO_SECRET_KEY (>= 32 chars) for production.')

if DATABASES['default']['ENGINE'].endswith('sqlite3') and not os.environ.get('SQLITE_PATH'):
    # Without this the database silently lands inside the container image and is lost on redeploy.
    raise ImproperlyConfigured('Set SQLITE_PATH to a file on a persistent volume (e.g. /data/heyjarvis.sqlite3) for production.')

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

# Email: always real SMTP in production (EMAIL_* or SMTP_* variables, see base.py).
EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')

# Static files (Django admin, DRF) served by WhiteNoise with compression.
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage' if WHITENOISE_AVAILABLE
        else 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}

# Error monitoring (optional): set SENTRY_DSN. Request bodies and user PII are not sent.
SENTRY_DSN = os.environ.get('SENTRY_DSN', '')
if SENTRY_DSN:
    try:
        import sentry_sdk
        sentry_sdk.init(
            dsn=SENTRY_DSN,
            send_default_pii=False,
            traces_sample_rate=float(os.environ.get('SENTRY_TRACES_SAMPLE_RATE', 0)),
            environment=os.environ.get('SENTRY_ENVIRONMENT', 'production'),
        )
    except Exception:  # monitoring must never stop the app from booting
        pass

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

# API schema / Swagger UI expose the full API surface: platform admins only in production.
SPECTACULAR_SETTINGS = {
    **SPECTACULAR_SETTINGS,
    'SERVE_PERMISSIONS': ['apps.core.permissions.IsAgencyAdmin'],
}
