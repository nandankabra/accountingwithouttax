"""Test-only TRUNCATE equivalent; production append-only guards stay enforced."""
from django.test.runner import DiscoverRunner
from unittest.mock import patch
from .sqlite_backend.base import ExactDecimalOperations


class SQLiteRunner(DiscoverRunner):
    def run_tests(self, *args, **kwargs):
        original = ExactDecimalOperations.sql_flush
        def test_flush(ops, style, tables, **options):
            with ops.connection.cursor() as cursor:
                cursor.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'")
                triggers = cursor.fetchall()
            return [f'DROP TRIGGER {ops.quote_name(name)};' for name, sql in triggers] + original(ops, style, tables, **options) + [sql + ';' for name, sql in triggers]
        with patch.object(ExactDecimalOperations, 'sql_flush', test_flush):
            return super().run_tests(*args, **kwargs)
