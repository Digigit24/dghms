import os
from pathlib import Path
from decouple import config, Csv
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Security / Hosts ---
SECRET_KEY = config('SECRET_KEY')
DEBUG = True
# DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='127.0.0.1,localhost', cast=Csv())
CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', default='', cast=Csv())








LOG_DIR = Path(BASE_DIR) / "logs"
os.makedirs(LOG_DIR, exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,

    "formatters": {
        "verbose": {
            "format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        },
    },

    "handlers": {
        "file": {
            "class": "logging.FileHandler",
            "filename": str(LOG_DIR / "django_errors.log"),
            "formatter": "verbose",
        },
        "debug_file": {
            "class": "logging.FileHandler",
            "filename": str(LOG_DIR / "jwt_debug.log"),
            "formatter": "verbose",
        },
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },

    "loggers": {
        # JWT authentication middleware logger
        "common.middleware": {
            "handlers": ["console", "file", "debug_file"],
            "level": "DEBUG",  # Show all debug info for auth issues
            "propagate": False,
        },
        # Nuvi API logger
        "nuviapi": {
            "handlers": ["console", "file"],
            "level": "DEBUG",  # Show all debug info for nuvi form submissions
            "propagate": False,
        },
    },

    "root": {  # catches all logs
        "handlers": ["console", "file"],
        "level": "ERROR",   # only errors go to the file
    },
}

# If behind Nginx TLS termination:
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True

# --- Apps ---
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # 3rd-party
    'rest_framework',
    'rest_framework.authtoken',
    'corsheaders',
    'django_filters',
    'drf_spectacular',
    'import_export',

    # Common - MUST be before local apps for proper auth setup
    'common',

    # Local apps
    # Note: accounts app removed - using SuperAdmin for authentication only
    # 'apps.accounts',
    'apps.doctors',
    'apps.patients',
    'apps.hospital',
    'apps.appointments',
    'apps.orders',
    'apps.payments',
    'apps.pharmacy',
    'apps.services',
    'apps.opd',
    'apps.ipd',
    'apps.diagnostics',
    'apps.panchakarma',
    'apps.nuviapi',
]

# --- Middleware ---
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # 'whitenoise.middleware.WhiteNoiseMiddleware',  # Temporarily disabled
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'common.middleware.JWTAuthenticationMiddleware',  # JWT authentication for API requests
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',  # Required by Django admin
    'common.middleware.CustomAuthenticationMiddleware',  # Override with our custom auth
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'hms.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
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

WSGI_APPLICATION = 'hms.wsgi.application'

# --- Database ---
# Support both DATABASE_URL and discrete env vars for backward compatibility
DATABASE_URL = config('DATABASE_URL', default=None)

if DATABASE_URL:
    # Use DATABASE_URL if provided
    DATABASES = {
        'default': dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    # Fall back to discrete env vars
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME':     config('DB_NAME'),
            'USER':     config('DB_USER'),
            'PASSWORD': config('DB_PASSWORD'),
            'HOST':     config('DB_HOST', default='localhost'),
            'PORT':     config('DB_PORT', default='5432'),
            'CONN_MAX_AGE': 600,
            'OPTIONS': {},
        }
    }

# --- Auth / Passwords ---
# NO LOCAL USER MODEL - Using SuperAdmin exclusively
# User authentication is handled via JWT tokens from SuperAdmin
# Admin authentication uses TenantUser (non-database user)

# Authentication backends for SuperAdmin integration
AUTHENTICATION_BACKENDS = [
    'common.auth_backends.SuperAdminAuthBackend',
    'common.auth_backends.JWTAuthBackend',
]

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# --- JWT Settings (must match SuperAdmin) ---
JWT_SECRET_KEY = config('JWT_SECRET_KEY', default='your-jwt-secret-key-change-in-production')
JWT_ALGORITHM = config('JWT_ALGORITHM', default='HS256')
JWT_LEEWAY = config('JWT_LEEWAY', default=30, cast=int)  # Clock skew tolerance in seconds

# --- SuperAdmin Integration ---
SUPERADMIN_URL = config('SUPERADMIN_URL', default='https://admin.celiyo.com')

# --- Session Settings (for admin authentication) ---
SESSION_COOKIE_AGE = 3600 * 8  # 8 hours
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# --- DRF ---
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'common.drf_auth.JWTAuthentication',  # Primary: JWT authentication via middleware
        'rest_framework.authentication.SessionAuthentication',  # Fallback for admin/browsable API
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'common.drf_auth.IsAuthenticated',  # Use custom IsAuthenticated that works with JWT
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

# --- drf-spectacular Settings ---
SPECTACULAR_SETTINGS = {
    'TITLE': 'DigiHMS API',
    'DESCRIPTION': 'Hospital Management System API Documentation',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'SCHEMA_PATH_PREFIX': '/api/',
    'COMPONENT_SPLIT_REQUEST': True,
}

# --- CORS Settings ---
CORS_ALLOW_ALL_ORIGINS = config('CORS_ALLOW_ALL_ORIGINS', default=False, cast=bool)
CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000',
    cast=Csv()
)

# Allow credentials (cookies, authorization headers, etc.)
CORS_ALLOW_CREDENTIALS = True

# Allow all headers (including custom tenant headers)
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
    # Custom tenant headers
    'x-tenant-id',
    'x-tenant-slug',
    'tenanttoken',
]

# Allow common HTTP methods
CORS_ALLOW_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]

# Expose headers to the browser
CORS_EXPOSE_HEADERS = [
    'content-type',
    'x-tenant-id',
    'x-tenant-slug',
]

# Cache preflight requests for 1 hour
CORS_PREFLIGHT_MAX_AGE = 3600

# --- I18N / TZ ---
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

# --- Static / Media ---
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
# STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'  # Temporarily disabled

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# --- Meta (Facebook) Conversions API & Google Sheets ---
META_PIXEL_ID = config('META_PIXEL_ID', default='876692741374254')
META_ACCESS_TOKEN = config('META_ACCESS_TOKEN', default='EAAMS6cNGH0YBQKKZBtCHGUzvTMoublHaxJrLZCoQuM1FC7PdWoZCE4e2FV5wO5wAga0C6wI7fEwa8uQ03mniEnT5HglyIZBVEfuVwcC2HZCJbQqqcuu6aMKMMRYa9PA2BlkNmqhT7rE75UQMn7XLkLYjjSGtVeiZAZCeWw3JYzD4rezv3jxubXd1yZCIgZBX1aAZDZD')
GOOGLE_SHEETS_API_URL = config('GOOGLE_SHEETS_API_URL', default='https://script.google.com/macros/s/AKfycby2ILM2o0y1jqZbjdOY5CQdhgmFjVMI61fZ_JrxJIEu5oQB-By7qwW4uoVE3QYPZrBQ/exec')

# --- Razorpay Settings ---
RAZORPAY_KEY_ID = config('RAZORPAY_KEY_ID', default='')
RAZORPAY_KEY_SECRET = config('RAZORPAY_KEY_SECRET', default='')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- Celery Settings ---
CELERY_BROKER_URL = config('CELERY_BROKER_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND', default='redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes max per task
CELERY_RESULT_EXPIRES = 3600  # Results expire after 1 hour
