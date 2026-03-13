"""
Minimal Django settings for running the plugin test suite.

Pretix's own settings module is used as the base so that all required
apps, middleware, and settings are present.  Environment variables are
set before the import so pretix does not complain about missing config.
"""
import os

# Minimum env vars pretix needs to start without a pretix.cfg file
os.environ.setdefault("DATA_DIR", "/tmp/pretix-test-data")
os.environ.setdefault("PRETIX_INSTANCE_NAME", "Test")
os.environ.setdefault("SITE_URL", "http://localhost")

from pretix.settings import *  # noqa: E402, F401, F403

# ---------------------------------------------------------------------------
# Database – use in-memory SQLite for speed
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
        "TEST": {"NAME": ":memory:"},
    }
}

# ---------------------------------------------------------------------------
# Make sure our plugin is loaded
# ---------------------------------------------------------------------------
if "pretix_email_restrictions" not in INSTALLED_APPS:
    INSTALLED_APPS.append("pretix_email_restrictions")

# ---------------------------------------------------------------------------
# Speed-up tweaks for tests
# ---------------------------------------------------------------------------
# Use a fast hasher so user creation is quick
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Disable async celery tasks
CELERY_ALWAYS_EAGER = True

# Dummy cache – avoids state leaking between tests
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

SECRET_KEY = "pretix-email-restrictions-test-secret-key"  # noqa: S105 – test only

# Prevent pretix from trying to send real emails
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

DEBUG = True
