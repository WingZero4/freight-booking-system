"""
Test-specific settings.

Overrides production security settings that break Django's test client
(which makes HTTP requests, not HTTPS).

Usage: python manage.py test --settings=config.test_settings
"""
import os

os.environ.setdefault('DJANGO_DEBUG', 'true')

from config.settings import *  # noqa: F401, F403

# Disable SSL redirect — test client uses HTTP
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
