import os
import secrets
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = os.getenv('APP_ENV', 'development') == 'development'
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured('SECRET_KEY is required outside development.')
    key_file = BASE_DIR / '.runtime' / 'dev-key'
    key_file.parent.mkdir(exist_ok=True)
    if not key_file.exists():
        key_file.write_text(secrets.token_urlsafe(64))
        key_file.chmod(0o600)
    SECRET_KEY = key_file.read_text()
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1,[::1],testserver').split(',')
INSTALLED_APPS = ['django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions', 'django.contrib.staticfiles', 'books']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware', 'django.contrib.sessions.middleware.SessionMiddleware', 'django.middleware.common.CommonMiddleware', 'django.middleware.csrf.CsrfViewMiddleware', 'django.contrib.auth.middleware.AuthenticationMiddleware', 'django.middleware.clickjacking.XFrameOptionsMiddleware', 'books.middleware.RequestMiddleware']
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [], 'APP_DIRS': True, 'OPTIONS': {'context_processors': ['django.template.context_processors.request', 'django.contrib.auth.context_processors.auth','books.context_processors.assets']}}]
WSGI_APPLICATION = 'config.wsgi.application'
DATABASES = {'default': {'ENGINE': 'django.db.backends.postgresql', 'NAME': os.getenv('PGDATABASE', 'simplebooks'), 'USER': os.getenv('PGUSER', ''), 'PASSWORD': os.getenv('PGPASSWORD', ''), 'HOST': os.getenv('PGHOST', str(BASE_DIR / '.runtime/socket')), 'PORT': os.getenv('PGPORT', '55439'), 'CONN_MAX_AGE': 60}}
PASSWORD_HASHERS = ['django.contrib.auth.hashers.Argon2PasswordHasher']
AUTH_PASSWORD_VALIDATORS = [{'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 12}}, {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'}, {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'}]
LANGUAGE_CODE = 'en-in'
TIME_ZONE = 'Asia/Kolkata'
USE_TZ = True
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
SESSION_COOKIE_AGE = int(os.getenv('SESSION_IDLE_SECONDS', '1800'))
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Strict'
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
X_FRAME_OPTIONS = 'DENY'
DATA_UPLOAD_MAX_MEMORY_SIZE = 256 * 1024
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'
LOGGING = {'version': 1, 'disable_existing_loggers': False, 'filters': {'redact_tokens': {'()':'books.security.RedactResetTokens'}}, 'handlers': {'console': {'class': 'logging.StreamHandler','filters':['redact_tokens']}}, 'loggers': {'simplebooks': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},'django.server':{'handlers':['console'],'level':'INFO','propagate':False}}}
LOGIN_IP_LIMIT=int(os.getenv('LOGIN_IP_LIMIT','2000'))
PASSWORD_RESET_TIMEOUT=900
APP_PUBLIC_URL=os.getenv('APP_PUBLIC_URL','http://127.0.0.1:8017')
EMAIL_BACKEND=os.getenv('EMAIL_BACKEND','django.core.mail.backends.filebased.EmailBackend' if DEBUG else 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_FILE_PATH=BASE_DIR/'.runtime/mail'
if DEBUG:
    EMAIL_FILE_PATH.mkdir(parents=True,exist_ok=True,mode=0o700)
    EMAIL_FILE_PATH.chmod(0o700)
EMAIL_HOST=os.getenv('EMAIL_HOST','')
EMAIL_PORT=int(os.getenv('EMAIL_PORT','587'))
EMAIL_HOST_USER=os.getenv('EMAIL_HOST_USER','')
EMAIL_HOST_PASSWORD=os.getenv('EMAIL_HOST_PASSWORD','')
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=os.getenv('DEFAULT_FROM_EMAIL','Simple Books <no-reply@example.test>')
EMAIL_TIMEOUT=10
