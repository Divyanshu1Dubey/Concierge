import os
from pathlib import Path
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent

# Integration credentials (AI + email) may be kept in a local .env file. Only this
# allow-list is read, and real environment variables always win: database, secret
# key, host and CORS settings must come from the process environment (Railway vars).
ENV_FILE_KEYS = {
    'AI_PROVIDER', 'OPENAI_API_KEY', 'OPENAI_MODEL', 'ANTHROPIC_API_KEY', 'ANTHROPIC_MODEL',
    'GEMINI_API_KEY', 'GEMINI_MODEL', 'GROQ_API_KEY', 'GROQ_MODEL',
    'CONCIERGE_MODEL', 'CONCIERGE_FALLBACK_MODEL', 'CONCIERGE_GROQ_MODEL',
    'EMAIL_HOST', 'EMAIL_PORT', 'EMAIL_HOST_USER', 'EMAIL_HOST_PASSWORD', 'EMAIL_USE_TLS', 'EMAIL_USE_SSL',
    'SMTP_HOST', 'SMTP_PORT', 'SMTP_USER', 'SMTP_PASSWORD', 'DEFAULT_FROM_EMAIL', 'FRONT_DESK_EMAIL',
    'SENTRY_DSN', 'IMAP_HOST', 'IMAP_USER', 'IMAP_PASSWORD',
}


def _load_env_files():
    for candidate in (BASE_DIR / 'backend' / '.env', BASE_DIR / '.env'):
        try:
            lines = candidate.read_text(encoding='utf-8').splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.strip()
            if key.startswith('export '):
                key = key[7:].strip()
            if key not in ENV_FILE_KEYS:
                continue
            value = value.split(' #', 1)[0].strip().strip('"').strip("'")
            if value:
                os.environ.setdefault(key, value)


if os.environ.get('DJANGO_LOAD_ENV_FILE', 'true').lower() in ('true', '1', 'yes'):
    _load_env_files()

INSECURE_DEV_SECRET_KEY = 'dev-secret-key-change-in-production'
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY') or os.environ.get('SECRET_KEY') or INSECURE_DEV_SECRET_KEY

DEBUG = os.environ.get('DJANGO_DEBUG', 'False').lower() in ('true', '1')


def env_flag(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ('true', '1', 'yes', 'on')

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'SAMEORIGIN'

_raw_hosts = os.environ.get('DJANGO_ALLOWED_HOSTS') or os.environ.get('ALLOWED_HOSTS') or 'localhost,127.0.0.1,testserver'
ALLOWED_HOSTS = [h.strip() for h in _raw_hosts.split(',') if h.strip()]
_app_public = os.environ.get('APP_PUBLIC_URL', '')
if _app_public:
    try:
        from urllib.parse import urlparse
        _host = urlparse(_app_public).netloc
        if _host and _host not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(_host)
    except Exception:
        pass
if '*' not in ALLOWED_HOSTS and not any('.up.railway.app' in h for h in ALLOWED_HOSTS):
    ALLOWED_HOSTS.append('.up.railway.app')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third party
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'drf_spectacular',
    'corsheaders',
    'django_filters',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'channels',

    # Local apps
    'apps.core',
    'apps.users',
    'apps.conversations',
    'apps.appointments',
    'apps.emails',
    'apps.ai_service',
    'apps.dashboard',
    'apps.practices',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
]

import importlib.util as _importlib_util

# WhiteNoise (in requirements.txt) serves collected static files in production.
WHITENOISE_AVAILABLE = _importlib_util.find_spec('whitenoise') is not None
if WHITENOISE_AVAILABLE:
    MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# Database
_db_url = os.environ.get('DATABASE_URL', '')
_db_engine = os.environ.get('DB_ENGINE', '').lower()

# SQLite file location. On hosts with ephemeral disks (e.g. Railway) point SQLITE_PATH at a
# mounted persistent volume (for example /data/heyjarvis.sqlite3); otherwise data is lost on redeploy.
SQLITE_PATH = os.environ.get('SQLITE_PATH') or str(BASE_DIR / 'heyjarvis.sqlite3')


def _sqlite_database():
    import django
    options = {'timeout': 20}
    if django.VERSION >= (5, 1):
        # Take the write lock at BEGIN so concurrent writers wait instead of failing.
        options['transaction_mode'] = 'IMMEDIATE'
    return {'ENGINE': 'django.db.backends.sqlite3', 'NAME': SQLITE_PATH, 'OPTIONS': options}

if _db_url and 'sqlite' not in _db_engine:
    try:
        import dj_database_url
        DATABASES = {
            'default': dj_database_url.config(
                default=_db_url,
                conn_max_age=600,
            )
        }
    except ImportError:
        DATABASES = {'default': _sqlite_database()}
elif os.environ.get('DB_HOST') and 'postgres' in _db_engine:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('DB_NAME', 'postgres'),
            'USER': os.environ.get('DB_USER', 'postgres'),
            'PASSWORD': os.environ.get('DB_PASSWORD', ''),
            'HOST': os.environ.get('DB_HOST'),
            'PORT': os.environ.get('DB_PORT', '5432'),
        }
    }
else:
    DATABASES = {'default': _sqlite_database()}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static & Media
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Custom User Model
AUTH_USER_MODEL = 'users.User'

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'apps.users.authentication.ActivePracticeJWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_THROTTLE_RATES': {
        'login': os.environ.get('THROTTLE_LOGIN_RATE', '10/min'),
        'auth': os.environ.get('THROTTLE_AUTH_RATE', '20/hour'),
        'widget': os.environ.get('THROTTLE_WIDGET_RATE', '60/min'),
        'widget_submit': os.environ.get('THROTTLE_WIDGET_SUBMIT_RATE', '10/min'),
    },
}

# Request size limits (JSON APIs; no file uploads are accepted)
DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000

# Demo accounts have well-known passwords: only provision/show them when explicitly enabled.
DEMO_ACCOUNTS_ENABLED = env_flag('ENABLE_DEMO_ACCOUNTS', default=DEBUG)
ALLOW_PUBLIC_REGISTRATION = env_flag('ALLOW_PUBLIC_REGISTRATION', default=False)
# Internal testing only: password applied to demo accounts when demo mode is on (never shown publicly).
DEMO_ACCOUNT_PASSWORD = os.environ.get('DEMO_ACCOUNT_PASSWORD', '')

# JWT Settings
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
}

# DRF Spectacular (OpenAPI)
SPECTACULAR_SETTINGS = {
    'TITLE': 'HeyJarvis API',
    'DESCRIPTION': 'AI Dental Concierge API',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

# Django Allauth
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']
try:
    import allauth as _allauth
    if int(_allauth.__version__.split('.')[0]) < 65:
        # Legacy names for environments still on django-allauth < 65 (requirements pin 65.x).
        ACCOUNT_EMAIL_REQUIRED = True
        ACCOUNT_USERNAME_REQUIRED = False
        ACCOUNT_AUTHENTICATION_METHOD = 'email'
except Exception:
    pass
ACCOUNT_EMAIL_VERIFICATION = 'none'
ACCOUNT_SESSION_REMEMBER = True

SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': [
            'profile',
            'email',
        ],
        'AUTH_PARAMS': {
            'access_type': 'online',
        },
        'STORAGE': 'allauth.socialaccount.models.SocialApp',
    },
}

# CORS & CSRF
_cors_env = os.environ.get('CORS_ALLOWED_ORIGINS', '')
if _cors_env:
    CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors_env.split(',') if o.strip()]
else:
    CORS_ALLOWED_ORIGINS = [
        'http://localhost:3000',
        'http://localhost:3001',
        'http://localhost:5173',
        'http://127.0.0.1:3000',
        'http://127.0.0.1:5173',
    ]

_csrf_env = os.environ.get('CSRF_TRUSTED_ORIGINS', '')
if _csrf_env:
    CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_env.split(',') if o.strip()]
else:
    CSRF_TRUSTED_ORIGINS = [
        'http://localhost:3000',
        'http://localhost:8000',
        'http://127.0.0.1:3000',
        'http://127.0.0.1:8000',
    ]

for _public_url in [os.environ.get('APP_PUBLIC_URL'), os.environ.get('FRONTEND_URL')]:
    if _public_url:
        _clean_url = _public_url.rstrip('/')
        if _clean_url not in CORS_ALLOWED_ORIGINS:
            CORS_ALLOWED_ORIGINS.append(_clean_url)
        if _clean_url not in CSRF_TRUSTED_ORIGINS:
            CSRF_TRUSTED_ORIGINS.append(_clean_url)

# NOTE: no wildcard *.up.railway.app CSRF origin — any Railway-hosted site could
# then forge session-authenticated requests. Set APP_PUBLIC_URL / CSRF_TRUSTED_ORIGINS.

CORS_ALLOW_CREDENTIALS = True

# Cache — local memory by default so Redis is optional for local demo
_REDIS_URL = os.environ.get('REDIS_URL', '')
if _REDIS_URL and not os.environ.get('USE_LOCAL_CACHE'):
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': _REDIS_URL,
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            },
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'heyjarvis-local',
        }
    }

# Celery
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 300

# Channels — InMemory for local; Redis when REDIS_URL is set
if _REDIS_URL and not os.environ.get('USE_LOCAL_CACHE'):
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                'hosts': [_REDIS_URL],
            },
        },
    }
else:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        },
    }

# Email — EMAIL_* variables, falling back to SMTP_* (e.g. a Gmail app password).
if os.environ.get('EMAIL_HOST_USER') and os.environ.get('EMAIL_HOST_PASSWORD'):
    EMAIL_HOST = os.environ.get('EMAIL_HOST', 'localhost')
    EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
    EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
    EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
else:
    EMAIL_HOST = os.environ.get('SMTP_HOST') or os.environ.get('EMAIL_HOST', 'localhost')
    EMAIL_PORT = int(os.environ.get('SMTP_PORT') or os.environ.get('EMAIL_PORT', 587))
    EMAIL_HOST_USER = os.environ.get('SMTP_USER', '')
    EMAIL_HOST_PASSWORD = (os.environ.get('SMTP_PASSWORD', '') or '').replace(' ', '')
EMAIL_USE_SSL = env_flag('EMAIL_USE_SSL', default=EMAIL_PORT == 465)
EMAIL_USE_TLS = False if EMAIL_USE_SSL else env_flag('EMAIL_USE_TLS', default=True)
EMAIL_TIMEOUT = 15
EMAIL_CONFIGURED = bool(EMAIL_HOST_USER and EMAIL_HOST_PASSWORD)
EMAIL_BACKEND = (
    'django.core.mail.backends.smtp.EmailBackend' if EMAIL_CONFIGURED
    else 'django.core.mail.backends.console.EmailBackend'
)
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL') or (
    f'HeyJarvis Concierge <{EMAIL_HOST_USER}>' if EMAIL_HOST_USER else 'HeyJarvis Concierge <noreply@heyjarvis.ai>'
)
# Send staff notifications after the request finishes (keeps patient chat fast).
EMAIL_ASYNC = env_flag('EMAIL_ASYNC', default=True)

# Inbound patient replies: an IMAP mailbox that receives replies (set the practice Reply-To to it).
# Opt in by setting IMAP_HOST; user/password default to the SMTP account.
IMAP_HOST = os.environ.get('IMAP_HOST', '')
IMAP_USER = os.environ.get('IMAP_USER') or (EMAIL_HOST_USER if IMAP_HOST else '')
IMAP_PASSWORD = (os.environ.get('IMAP_PASSWORD') or (EMAIL_HOST_PASSWORD if IMAP_HOST else '')).replace(' ', '')
# Shared secret for scheduled jobs (e.g. a Railway cron calling the reply check).
CRON_SECRET = os.environ.get('CRON_SECRET', '')

# AI Configuration
# AI_PROVIDER: gemini | groq | openai | anthropic | none. When unset, the first provider
# with an API key is used (Gemini, then Groq, then OpenAI, then Anthropic); the others
# with keys act as fallbacks. With no key the concierge runs rule-based only.
AI_PROVIDER = os.environ.get('AI_PROVIDER', '').strip().lower()
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
OPENAI_BASE_URL = os.environ.get('OPENAI_BASE_URL', 'https://api.openai.com/v1')
OPENAI_MODEL = os.environ.get('OPENAI_MODEL', 'gpt-4o-mini')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
ANTHROPIC_BASE_URL = os.environ.get('ANTHROPIC_BASE_URL', 'https://api.anthropic.com')
ANTHROPIC_MODEL = os.environ.get('ANTHROPIC_MODEL', 'claude-3-5-haiku-20241022')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
GEMINI_BASE_URL = 'https://generativelanguage.googleapis.com/v1beta/openai/'
_concierge_model = os.environ.get('CONCIERGE_MODEL', '')
GEMINI_MODEL = os.environ.get('GEMINI_MODEL') or (_concierge_model if _concierge_model.startswith('gemini') else 'gemini-3.8-flash')
GEMINI_FALLBACK_MODEL = os.environ.get('CONCIERGE_FALLBACK_MODEL', '')
GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
GROQ_BASE_URL = 'https://api.groq.com/openai/v1'
GROQ_MODEL = os.environ.get('GROQ_MODEL') or os.environ.get('CONCIERGE_GROQ_MODEL') or 'llama-3.3-70b-versatile'
AI_TIMEOUT_SECONDS = float(os.environ.get('AI_TIMEOUT_SECONDS', 15))
AI_MAX_TOKENS = int(os.environ.get('AI_MAX_TOKENS', 800))
# Cost control: maximum AI replies per practice per day (rule-based replies are unlimited).
AI_DAILY_LIMIT_PER_PRACTICE = int(os.environ.get('AI_DAILY_LIMIT_PER_PRACTICE', 300))

# Centralized Public URL Configuration
APP_PUBLIC_URL = os.environ.get('APP_PUBLIC_URL', '').rstrip('/')
FRONTEND_URL = os.environ.get('FRONTEND_URL', '').rstrip('/')
WIDGET_URL = f"{APP_PUBLIC_URL}/widget.js" if APP_PUBLIC_URL else "/widget.js"
CONCIERGE_URL = f"{FRONTEND_URL}/concierge" if FRONTEND_URL else "/dashboard/concierge"
API_URL = f"{APP_PUBLIC_URL}/api" if APP_PUBLIC_URL else "/api"

