"""Configuration settings for the school management system."""
import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

# Load local .env file if present, without overwriting existing environment variables.
env_file = BASE_DIR / ".env"
if env_file.is_file():
    try:
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key, val = key.strip(), val.strip().strip("'\"")
                alt_key = key[7:] if key.startswith("DJANGO_") else f"DJANGO_{key}"
                # Do not overwrite if either the variable or its prefixed/unprefixed variant is already in os.environ
                if key not in os.environ and alt_key not in os.environ:
                    os.environ[key] = val
    except OSError:
        pass


def get_env(name, default=None):
    """Retrieve configuration variable supporting both plain names and DJANGO_-prefixed names."""
    if name in os.environ:
        return os.environ[name]
    prefixed = f"DJANGO_{name}"
    if prefixed in os.environ:
        return os.environ[prefixed]
    return default


# Debug and environment mode
raw_debug = get_env("DEBUG")
if raw_debug is not None:
    DEBUG = raw_debug.strip().lower() in {"1", "true", "yes", "on"}
else:
    env_mode = get_env("ENV", get_env("ENVIRONMENT", "development")).strip().lower()
    DEBUG = env_mode in {"development", "dev", "local", "test"}

# Secret key
DEV_SECRET_KEY = "development-only-change-before-production"
SECRET_KEY = get_env("SECRET_KEY", DEV_SECRET_KEY if DEBUG else "")
if not DEBUG and (not SECRET_KEY or SECRET_KEY == DEV_SECRET_KEY):
    raise ImproperlyConfigured("A secret key must be set in production when DEBUG is False.")

# Allowed hosts
raw_hosts = get_env("ALLOWED_HOSTS", "")
ALLOWED_HOSTS = [host.strip() for host in raw_hosts.split(",") if host.strip()]
if not ALLOWED_HOSTS and DEBUG:
    ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "academics",
    "timetable",
    "attendance",
    "grades",
    "homework",
    "fees",
    "dashboard",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "school_project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

WSGI_APPLICATION = "school_project.wsgi.application"

# Database configuration
db_engine = get_env("DATABASE_ENGINE", "sqlite3").lower()
if "postgres" in db_engine or get_env("DATABASE_URL", "").startswith("postgres"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": get_env("DATABASE_NAME", get_env("DB_NAME", "school_db")),
            "USER": get_env("DATABASE_USER", get_env("DB_USER", "postgres")),
            "PASSWORD": get_env("DATABASE_PASSWORD", get_env("DB_PASSWORD", "")),
            "HOST": get_env("DATABASE_HOST", get_env("DB_HOST", "localhost")),
            "PORT": get_env("DATABASE_PORT", get_env("DB_PORT", "5432")),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": get_env("DATABASE_PATH", str(BASE_DIR / "db.sqlite3")),
        }
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

PASSWORD_RESET_TIMEOUT = int(get_env("PASSWORD_RESET_TIMEOUT", "86400"))  # 24 hours

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Karachi"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "dashboard:home"

# Email configuration for notifications and password reset
EMAIL_BACKEND = get_env(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend" if DEBUG else "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = get_env("EMAIL_HOST", "localhost")
EMAIL_PORT = int(get_env("EMAIL_PORT", "587"))
EMAIL_HOST_USER = get_env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = get_env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = get_env("EMAIL_USE_TLS", "1").lower() in {"1", "true", "yes", "on"}
DEFAULT_FROM_EMAIL = get_env("DEFAULT_FROM_EMAIL", "webmaster@localhost")

# Cache configuration
cache_backend = get_env("CACHE_BACKEND")
if cache_backend:
    CACHES = {
        "default": {
            "BACKEND": cache_backend,
            "LOCATION": get_env("CACHE_LOCATION", "school_cache"),
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "unique-snowflake",
        }
    }

# Security and HTTPS settings in production
if not DEBUG:
    SESSION_COOKIE_SECURE = get_env("SESSION_COOKIE_SECURE", "1").lower() in {"1", "true", "yes", "on"}
    CSRF_COOKIE_SECURE = get_env("CSRF_COOKIE_SECURE", "1").lower() in {"1", "true", "yes", "on"}
    SECURE_SSL_REDIRECT = get_env("SECURE_SSL_REDIRECT", "0").lower() in {"1", "true", "yes", "on"}
    SECURE_HSTS_SECONDS = int(get_env("SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = get_env("SECURE_HSTS_INCLUDE_SUBDOMAINS", "1").lower() in {"1", "true", "yes", "on"}
    SECURE_HSTS_PRELOAD = get_env("SECURE_HSTS_PRELOAD", "1").lower() in {"1", "true", "yes", "on"}
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
    if get_env("SECURE_PROXY_SSL_HEADER"):
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Internal acceleration header support (e.g. X-Accel-Redirect for Nginx)
USE_X_ACCEL_REDIRECT = get_env("USE_X_ACCEL_REDIRECT", "0").lower() in {"1", "true", "yes", "on"}
