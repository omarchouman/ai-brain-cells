"""
Django settings for ai-brain-cells.

A single-user, local-first tool. There is deliberately no database: the
markdown files under `brain/` are the only source of truth, and sessions
ride in signed cookies. If you find yourself adding a model, check first
whether the filesystem already answers the question.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# The brain itself: its own git repo, ignored by this repo. Created on first
# run by copying `brain-template/`.
BRAIN_PATH = Path(os.environ.get("BRAIN_PATH", BASE_DIR / "brain"))
BRAIN_TEMPLATE_PATH = BASE_DIR / "brain-template"

SECRET_KEY = os.environ.get(
    "SECRET_KEY", "dev-only-key-this-app-binds-to-localhost-and-stores-nothing"
)
DEBUG = os.environ.get("DEBUG", "1") == "1"
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]

INSTALLED_APPS = [
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
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
                "django.template.context_processors.request",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# No database. Sessions are signed cookies; nothing else persists in Django.
DATABASES = {}
SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
MESSAGE_STORAGE = "django.contrib.messages.storage.cookie.CookieStorage"

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
