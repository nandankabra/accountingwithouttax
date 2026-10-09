"""Private single-PC service. No external server or database installation."""
from .settings import *

LOCAL_DESKTOP = True
DESKTOP_DATA_DIR = Path(os.environ['SIMPLEBOOKS_DATA_DIR'])
INSTALLATION_ID = os.environ['SIMPLEBOOKS_INSTALLATION_ID']
LOCAL_SERVICE_TOKEN = os.environ['SIMPLEBOOKS_LOCAL_TOKEN']
OFFLINE_PUBLIC_KEY = os.environ['SIMPLEBOOKS_PUBLIC_KEY']
DEBUG = False
ALLOWED_HOSTS = ['127.0.0.1']
DATABASES = {'default': {'ENGINE': 'config.sqlite_backend', 'NAME': DESKTOP_DATA_DIR / 'books.sqlite3', 'OPTIONS': {'timeout': 30, 'transaction_mode': 'IMMEDIATE'}}}
MIDDLEWARE = ['books.local_desktop.LocalOnlyMiddleware', 'whitenoise.middleware.WhiteNoiseMiddleware'] + MIDDLEWARE
MIDDLEWARE.insert(MIDDLEWARE.index('django.contrib.auth.middleware.AuthenticationMiddleware') + 1, 'books.local_desktop.LocalSessionMiddleware')
PASSWORD_HASHERS = ['django.contrib.auth.hashers.Argon2PasswordHasher']
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
STATIC_ROOT = BASE_DIR / 'staticfiles'
EMAIL_BACKEND = 'django.core.mail.backends.dummy.EmailBackend'
ALLOW_SELF_SIGNUP = False
