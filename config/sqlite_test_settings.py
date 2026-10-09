from .settings import *

DATABASES = {'default': {'ENGINE': 'config.sqlite_backend', 'NAME': BASE_DIR / '.runtime/sqlite-test-source.sqlite3', 'TEST': {'NAME': BASE_DIR / '.runtime/sqlite-tests.sqlite3'}, 'OPTIONS': {'timeout': 30, 'transaction_mode': 'IMMEDIATE'}}}
TEST_RUNNER = 'config.sqlite_test_runner.SQLiteRunner'
