from datetime import timedelta
from pathlib import Path

import dj_database_url
from decouple import config


BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config(
    "SECRET_KEY",
    default="django-insecure-dev-key",
)

DEBUG = config(
    "DEBUG",
    default=True,
    cast=bool,
)

if not DEBUG and SECRET_KEY == "django-insecure-dev-key":
    raise ValueError("Defina SECRET_KEY no ambiente de produção.")


def config_list(name: str, default: str = "") -> list[str]:
    return [
        value.strip()
        for value in config(name, default=default).split(",")
        if value.strip()
    ]


ALLOWED_HOSTS = config_list(
    "ALLOWED_HOSTS",
    "daruix-engenharia.vps-kinghost.net,hub.daruix-engenharia.vps-kinghost.net,localhost,127.0.0.1,192.168.0.74,192.168.15.11,10.0.2.2",
)


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "django_filters",
    "accounts",
    "memorando_remessas.apps.MemorandoRemessasConfig",
]


AUTH_USER_MODEL = "accounts.User"


REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "accounts.authentication.SessionJWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}


SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(hours=12),
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
}

SESSION_IDLE_TIMEOUT_MINUTES = config(
    "SESSION_IDLE_TIMEOUT_MINUTES",
    default=30,
    cast=int,
)


SPECTACULAR_SETTINGS = {
    "TITLE": "Daruix Hub API",
    "DESCRIPTION": "API interna do Daruix Hub",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


CORS_ALLOWED_ORIGINS = config_list(
    "CORS_ALLOWED_ORIGINS",
    (
        "http://localhost:4200,"
        "http://localhost:8100,"
        "http://localhost:4300,"
        "http://127.0.0.1:4300,"
        "http://192.168.0.73:4300,"
        "http://192.168.0.74:4300,"
        "http://192.168.15.11:4300,"
        "http://10.0.2.2:4300,"
        "https://localhost"
    ),
)

CSRF_TRUSTED_ORIGINS = config_list(
    "CSRF_TRUSTED_ORIGINS",
)


ROOT_URLCONF = "config.urls"


TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


WSGI_APPLICATION = "config.wsgi.application"


DATABASES = {
    "default": dj_database_url.config(
        default=config(
            "DATABASE_URL",
            default="postgresql://postgres:admin@localhost:5432/sgo-daruix-web",
        ),
        conn_max_age=600,
        conn_health_checks=True,
    )
}


AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "MinimumLengthValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "CommonPasswordValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "NumericPasswordValidator"
        ),
    },
]


LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True


STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage.CompressedManifestStaticFilesStorage"
        ),
    },
}

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


LEGACY_AUTH_ENABLED = config(
    "LEGACY_AUTH_ENABLED",
    default=True,
    cast=bool,
)

LEGACY_DB_PATH = config(
    "LEGACY_DB_PATH",
    default="",
)

LEGACY_PYTHON_PATH = config(
    "LEGACY_PYTHON_PATH",
    default=str(BASE_DIR / ".venv32" / "Scripts" / "python.exe"),
)

LEGACY_AUTH_BRIDGE_PATH = config(
    "LEGACY_AUTH_BRIDGE_PATH",
    default=str(BASE_DIR / "legacy_reader" / "auth_bridge.py"),
)

LEGACY_MEMORANDO_REMESSAS_BRIDGE_PATH = config(
    "LEGACY_MEMORANDO_REMESSAS_BRIDGE_PATH",
    default=str(
        BASE_DIR
        / "legacy_reader"
        / "memorando_remessas_bridge.py"
    ),
)

LEGACY_BRIDGE_TIMEOUT_SECONDS = config(
    "LEGACY_BRIDGE_TIMEOUT_SECONDS",
    default=30,
    cast=int,
)


SHIPMENT_MEMO_MAX_FILE_SIZE_MB = config(
    "SHIPMENT_MEMO_MAX_FILE_SIZE_MB",
    default=20,
    cast=int,
)

SHIPMENT_MEMO_MAX_FILES_PER_MEMO = config(
    "SHIPMENT_MEMO_MAX_FILES_PER_MEMO",
    default=20,
    cast=int,
)

SHIPMENT_MEMO_ALLOWED_FILE_EXTENSIONS = [
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".jpg",
    ".jpeg",
    ".png",
    ".zip",
]

SHIPMENT_MEMO_RECIPIENT_EMAIL = config(
    "SHIPMENT_MEMO_RECIPIENT_EMAIL",
    default="",
).strip().lower()

SHIPMENT_MEMO_CC_EMAILS = [
    email.strip().lower()
    for email in config(
        "SHIPMENT_MEMO_CC_EMAILS",
        default="",
    ).split(",")
    if email.strip()
]


EMAIL_BACKEND = config(
    "EMAIL_BACKEND",
    default=(
        "django.core.mail.backends.console.EmailBackend"
        if DEBUG
        else "django.core.mail.backends.smtp.EmailBackend"
    ),
)

EMAIL_HOST = config(
    "EMAIL_HOST",
    default="",
)

EMAIL_PORT = config(
    "EMAIL_PORT",
    default=587,
    cast=int,
)

EMAIL_HOST_USER = config(
    "EMAIL_HOST_USER",
    default="",
)

EMAIL_HOST_PASSWORD = config(
    "EMAIL_HOST_PASSWORD",
    default="",
)

EMAIL_USE_TLS = config(
    "EMAIL_USE_TLS",
    default=True,
    cast=bool,
)

EMAIL_USE_SSL = config(
    "EMAIL_USE_SSL",
    default=False,
    cast=bool,
)

EMAIL_TIMEOUT = config(
    "EMAIL_TIMEOUT",
    default=30,
    cast=int,
)

DEFAULT_FROM_EMAIL = config(
    "DEFAULT_FROM_EMAIL",
    default=EMAIL_HOST_USER or "Daruix Hub <no-reply@daruix.com.br>",
)

SERVER_EMAIL = config(
    "SERVER_EMAIL",
    default=DEFAULT_FROM_EMAIL,
)

if EMAIL_USE_TLS and EMAIL_USE_SSL:
    raise ValueError(
        "EMAIL_USE_TLS e EMAIL_USE_SSL não podem estar ativos ao mesmo tempo."
    )
