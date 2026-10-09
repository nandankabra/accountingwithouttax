"""Equivalent append-only and tenant guards for the single-PC database."""
TABLES = ('auditevent', 'voucherrevision', 'calculationrun', 'journalentry', 'stockmovement', 'mutation')


def install(apps, schema_editor):
    if schema_editor.connection.vendor != 'sqlite':
        return
    for table in TABLES:
        for action in ('UPDATE', 'DELETE'):
            schema_editor.execute(f"CREATE TRIGGER protect_{table}_{action.lower()} BEFORE {action} ON books_{table} BEGIN SELECT RAISE(ABORT, 'Accounting history is append-only'); END")
    for table, master in (('journalentry', 'account'), ('stockmovement', 'item')):
        schema_editor.execute(f"""CREATE TRIGGER check_{table}_tenant BEFORE INSERT ON books_{table}
            WHEN (SELECT workspace_id FROM books_calculationrun WHERE id=NEW.run_id)
                 IS NOT (SELECT workspace_id FROM books_voucher WHERE id=NEW.voucher_id)
              OR (SELECT workspace_id FROM books_calculationrun WHERE id=NEW.run_id)
                 IS NOT (SELECT workspace_id FROM books_{master} WHERE id=NEW.{master}_id)
            BEGIN SELECT RAISE(ABORT, 'Linked records must belong to the calculation workspace'); END""")


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor != 'sqlite':
        return
    for table in TABLES:
        for action in ('update', 'delete'):
            schema_editor.execute(f'DROP TRIGGER IF EXISTS protect_{table}_{action}')
    for table in ('journalentry', 'stockmovement'):
        schema_editor.execute(f'DROP TRIGGER IF EXISTS check_{table}_tenant')
