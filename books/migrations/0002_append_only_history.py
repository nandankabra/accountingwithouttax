from django.db import migrations

TABLES = ('auditevent','voucherrevision','calculationrun','journalentry','stockmovement','mutation')


def install(apps, schema_editor):
    # SQLite protection is installed after its table-rebuilding migrations.
    if schema_editor.connection.vendor == 'sqlite':
        return
    schema_editor.execute("""
        CREATE FUNCTION books_reject_history_change() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Accounting history is append-only';
        END;
        $$ LANGUAGE plpgsql;
    """)
    for table in TABLES:
        schema_editor.execute(f'CREATE TRIGGER protect_history BEFORE UPDATE OR DELETE ON books_{table} FOR EACH ROW EXECUTE FUNCTION books_reject_history_change()')
    schema_editor.execute("""
        CREATE FUNCTION books_check_tenant() RETURNS trigger AS $$
        DECLARE run_workspace uuid; linked_workspace uuid;
        BEGIN
            SELECT r.workspace_id INTO run_workspace FROM books_calculationrun r WHERE r.id = NEW.run_id;
            SELECT v.workspace_id INTO linked_workspace FROM books_voucher v WHERE v.id = NEW.voucher_id;
            IF run_workspace IS DISTINCT FROM linked_workspace THEN
                RAISE EXCEPTION 'Voucher must belong to calculation workspace';
            END IF;
            IF TG_TABLE_NAME = 'books_journalentry' THEN
                SELECT a.workspace_id INTO linked_workspace FROM books_account a WHERE a.id = NEW.account_id;
            ELSE
                SELECT i.workspace_id INTO linked_workspace FROM books_item i WHERE i.id = NEW.item_id;
            END IF;
            IF run_workspace IS DISTINCT FROM linked_workspace THEN
                RAISE EXCEPTION 'Master must belong to calculation workspace';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    for table in ('journalentry','stockmovement'):
        schema_editor.execute(f'CREATE TRIGGER check_tenant BEFORE INSERT ON books_{table} FOR EACH ROW EXECUTE FUNCTION books_check_tenant()')


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor == 'sqlite':
        return
    for table in TABLES:
        schema_editor.execute(f'DROP TRIGGER protect_history ON books_{table}')
    for table in ('journalentry','stockmovement'):
        schema_editor.execute(f'DROP TRIGGER check_tenant ON books_{table}')
    schema_editor.execute('DROP FUNCTION books_reject_history_change()')
    schema_editor.execute('DROP FUNCTION books_check_tenant()')


class Migration(migrations.Migration):
    dependencies = [('books','0001_initial')]
    operations = [migrations.RunPython(install,uninstall)]
