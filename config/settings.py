from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env_file():
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_env_file()


def _env(name, default=""):
    value = os.environ.get(name, default).strip().strip('"').strip("'")
    return value

def _env_bool(name, default=False):
    return _env(name, "true" if default else "false").lower() in ("1", "true", "yes", "on")


SECRET_KEY = _env("DJANGO_SECRET_KEY", "django-insecure-dev-key-change-me-in-production")
DEBUG = _env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = [
    host.strip()
    for host in _env("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
    if host.strip()
]
if DEBUG and "testserver" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append("testserver")

# Hardening that only kicks in when DEBUG is off (production).
if not DEBUG:
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    SESSION_COOKIE_HTTPONLY = True
    CSRF_COOKIE_HTTPONLY = False
    X_FRAME_OPTIONS = "DENY"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",

    # local apps
    "core.apps.CoreConfig",
    "accounts",
    "products",
    "whatmobile",
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

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.access_control",
                "products.context_processors.site_stats",
                "products.context_processors.favorites",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    },
    "whatmobile": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "whatmobile.sqlite3",
    },
}

DATABASE_ROUTERS = ["whatmobile.db_router.WhatMobileRouter"]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:home"
LOGOUT_REDIRECT_URL = "core:home"

ADMIN_EMAIL = _env("ADMIN_EMAIL", "mohsantv616@gmail.com").lower()

SITE_URL = "http://127.0.0.1:8000"

EMAIL_HOST_USER = _env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = _env("EMAIL_HOST_PASSWORD").replace(" ", "")

if EMAIL_HOST_USER and EMAIL_HOST_PASSWORD:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = "smtp.gmail.com"
    EMAIL_PORT = 587
    EMAIL_USE_TLS = True
    DEFAULT_FROM_EMAIL = f"PriceVerse <{EMAIL_HOST_USER}>"
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    DEFAULT_FROM_EMAIL = "PriceVerse <alerts@priceverse.local>"

PASSWORD_RESET_TIMEOUT = 60 * 60 * 24  # 24 hours

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "priceverse-cache",
    }
}

GROQ_API_KEY = _env("GROQ_API_KEY")
GROQ_MODEL = _env("GROQ_MODEL", "llama-3.1-8b-instant")

GEMINI_API_KEY = _env("GEMINI_API_KEY") or _env("GOOGLE_GEMINI_API_KEY")
GEMINI_MODEL = _env("GEMINI_MODEL", "gemini-2.0-flash-lite")

CLAUDE_API_KEY = _env("CHATBOT") or _env("CLAUDE_API_KEY") or _env("ANTHROPIC_API_KEY")
CLAUDE_MODEL = _env("CLAUDE_MODEL", "claude-3-5-haiku-20241022")

HF_API_TOKEN = _env("HF_API_TOKEN") or _env("HUGGINGFACE_API_KEY")
HF_COMPARE_MODEL = _env("HF_COMPARE_MODEL", "Qwen/Qwen2.5-3B-Instruct")

# Meta Llama — official chatbot provider (Llama Stack + llama-models CLI)
LLAMA_MODEL_ID = _env("LLAMA_MODEL_ID", "llama3.2:3b")
LLAMA_STACK_BASE_URL = _env("LLAMA_STACK_BASE_URL", "http://localhost:8321")
LLAMA_DOWNLOAD_URL = _env("LLAMA_DOWNLOAD_URL", "")
LLAMA_MAX_TOKENS = int(_env("LLAMA_MAX_TOKENS", "1200") or "1200")
LLAMA_TEMPERATURE = float(_env("LLAMA_TEMPERATURE", "0.2") or "0.2")
LLAMA_REQUEST_TIMEOUT = float(_env("LLAMA_REQUEST_TIMEOUT", "300") or "300")
LLAMA_KEEP_ALIVE = _env("LLAMA_KEEP_ALIVE", "30m")

# Chatbot performance
CHAT_LLM_HISTORY_TURNS = int(_env("CHAT_LLM_HISTORY_TURNS", "4") or "4")
CHAT_LLM_HISTORY_CHARS = int(_env("CHAT_LLM_HISTORY_CHARS", "200") or "200")
CHAT_SESSION_HISTORY_TURNS = int(_env("CHAT_SESSION_HISTORY_TURNS", "12") or "12")
CHAT_CLIENT_TIMEOUT_MS = int(_env("CHAT_CLIENT_TIMEOUT_MS", "180000") or "180000")
CHAT_USE_STREAMING = _env("CHAT_USE_STREAMING", "true").lower() in {"1", "true", "yes"}

SCRAPE_LIMIT_PER_BRAND = int(_env("SCRAPE_LIMIT_PER_BRAND", "0") or "0")
WHATMOBILE_SCRAPE_LIMIT = int(_env("WHATMOBILE_SCRAPE_LIMIT", "0") or "0")
WHATMOBILE_MAX_CONCURRENT = int(_env("WHATMOBILE_MAX_CONCURRENT", "1") or "1")
WHATMOBILE_MIN_DELAY = float(_env("WHATMOBILE_MIN_DELAY", "1.0") or "1.0")
WHATMOBILE_MAX_DELAY = float(_env("WHATMOBILE_MAX_DELAY", "3.0") or "3.0")
WHATMOBILE_MAX_RETRIES = int(_env("WHATMOBILE_MAX_RETRIES", "6") or "6")
WHATMOBILE_RATE_LIMIT_BACKOFF = float(_env("WHATMOBILE_RATE_LIMIT_BACKOFF", "5.0") or "5.0")
WHATMOBILE_STATE_FILE = BASE_DIR / "whatmobile_scrape_state.json"
USD_TO_PKR_RATE = float(_env("USD_TO_PKR_RATE", "278") or "278")
SCRAPE_BATCH_SIZE = int(_env("SCRAPE_BATCH_SIZE", "25") or "25")
SCRAPE_BATCH_DELAY_SECONDS = int(_env("SCRAPE_BATCH_DELAY_SECONDS", "5") or "5")
SCRAPE_MAX_CONCURRENT = int(_env("SCRAPE_MAX_CONCURRENT", "4") or "4")
SCRAPE_MIN_DELAY = float(_env("SCRAPE_MIN_DELAY", "0.8") or "0.8")
SCRAPE_MAX_DELAY = float(_env("SCRAPE_MAX_DELAY", "1.6") or "1.6")
SCRAPE_REQUEST_TIMEOUT = int(_env("SCRAPE_REQUEST_TIMEOUT", "25") or "25")
SCRAPE_MAX_RETRIES = int(_env("SCRAPE_MAX_RETRIES", "3") or "3")
SCRAPE_RETRY_BACKOFF = float(_env("SCRAPE_RETRY_BACKOFF", "2.0") or "2.0")
SCRAPE_PROXY_URL = _env("SCRAPE_PROXY_URL", "")

PRODUCTS_PER_PAGE = int(_env("PRODUCTS_PER_PAGE", "30") or "30")
