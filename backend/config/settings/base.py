import os
from pathlib import Path
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'dev-secret-key-change-in-production')

DEBUG = os.environ.get('DJANGO_DEBUG', 'True') == 'True'

_raw_hosts = os.environ.get('DJANGO_ALLOWED_HOSTS') or os.environ.get('ALLOWED_HOSTS') or 'localhost,127.0.0.1,testserver,*'
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
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': BASE_DIR / 'heyjarvis.sqlite3',
            }
        }
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
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'heyjarvis.sqlite3',
        }
    }

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
        'rest_framework_simplejwt.authentication.JWTAuthentication',
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
}

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
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_AUTHENTICATION_METHOD = 'email'
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

# Always trust Railway domains for CSRF in production
if not any('*.up.railway.app' in u for u in CSRF_TRUSTED_ORIGINS):
    CSRF_TRUSTED_ORIGINS.append('https://*.up.railway.app')

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

# Email
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'noreply@heyjarvis.ai')

# AI Configuration
AI_PROVIDER = os.environ.get('AI_PROVIDER', 'openai')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
OPENAI_BASE_URL = os.environ.get('OPENAI_BASE_URL', 'https://api.openai.com/v1')
OPENAI_MODEL = os.environ.get('OPENAI_MODEL', 'gpt-4o-mini')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
ANTHROPIC_BASE_URL = os.environ.get('ANTHROPIC_BASE_URL', 'https://api.anthropic.com')
ANTHROPIC_MODEL = os.environ.get('ANTHROPIC_MODEL', 'claude-3-5-haiku-20241022')

# Centralized Public URL Configuration
APP_PUBLIC_URL = os.environ.get('APP_PUBLIC_URL', '').rstrip('/')
FRONTEND_URL = os.environ.get('FRONTEND_URL', '').rstrip('/')
WIDGET_URL = f"{APP_PUBLIC_URL}/widget.js" if APP_PUBLIC_URL else "/widget.js"
CONCIERGE_URL = f"{FRONTEND_URL}/concierge" if FRONTEND_URL else "/dashboard/concierge"
API_URL = f"{APP_PUBLIC_URL}/api" if APP_PUBLIC_URL else "/api"

