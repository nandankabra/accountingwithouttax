"""Bundled service launched and stopped by Electron; all data lives in userData."""
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys
import threading
from contextlib import closing
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def snapshot(source, target):
    target = Path(target)
    if target.resolve() == Path(source).resolve():
        raise ValueError('Choose a separate backup file.')
    temporary = target.with_name(target.name + '.tmp')
    if temporary.exists():
        temporary.unlink()
    try:
        with closing(sqlite3.connect(Path(source).resolve().as_uri() + '?mode=ro', uri=True)) as src, closing(sqlite3.connect(temporary)) as dst:
            src.backup(dst)
            if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Database integrity check failed.')
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def validate_restore(source):
    with closing(sqlite3.connect(Path(source).resolve().as_uri() + '?mode=ro', uri=True)) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('The backup is damaged.')
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'books_voucher', 'books_workspace', 'books_offlinelicense', 'django_migrations'} <= tables:
            raise ValueError('Choose a Simple Books standalone backup.')
        if db.execute('SELECT count(*) FROM books_offlinelicense').fetchone()[0] != 1:
            raise ValueError('The backup must contain one activated company.')
        # Future schemas cannot safely be opened by this release.
        if db.execute("SELECT name FROM django_migrations WHERE app='books' ORDER BY name DESC LIMIT 1").fetchone()[0] != '0010_offline_license':
            raise ValueError('This backup requires a different app version.')


def main():
    command = json.loads(sys.stdin.readline())
    data = Path(command['data_dir']).resolve()
    data.mkdir(parents=True, exist_ok=True)
    database = data / 'books.sqlite3'
    backups = data / 'backups'
    backups.mkdir(exist_ok=True)
    action = command.get('action', 'serve')
    if action == 'backup':
        if not database.exists():
            raise ValueError('Activate your company before making a backup.')
        snapshot(database, command['path'])
        print(json.dumps({'ok': True}), flush=True)
        return
    if action == 'restore':
        validate_restore(command['path'])
        if database.exists():
            snapshot(database, backups / ('before-restore-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.sqlite3'))
        snapshot(command['path'], database)
        print(json.dumps({'ok': True}), flush=True)
        return
    secret = data / 'secret.key'
    if not secret.exists():
        with os.fdopen(os.open(secret, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as handle:
            handle.write(secrets.token_urlsafe(64))
    # Override inherited deployment settings; this service can never host LAN traffic.
    os.environ.update({'DJANGO_SETTINGS_MODULE': 'config.desktop_settings', 'APP_ENV': 'production', 'SECRET_KEY': secret.read_text(),
                       'SIMPLEBOOKS_DATA_DIR': str(data), 'SIMPLEBOOKS_INSTALLATION_ID': command['installation'],
                       'SIMPLEBOOKS_LOCAL_TOKEN': command['token'], 'SIMPLEBOOKS_PUBLIC_KEY': command['public_key']})
    if database.exists():
        backup = backups / ('startup-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.sqlite3')
        snapshot(database, backup)
        # Keep thirty successful startup snapshots; manual exports are never pruned.
        for previous in sorted(backups.glob('startup-*.sqlite3'))[:-30]:
            previous.unlink()
    import django
    django.setup()
    from django.core.management import call_command
    call_command('migrate', interactive=False, verbosity=0)
    from django.core.wsgi import get_wsgi_application
    from waitress import create_server
    port_file = data / 'service-port.json'
    port = 0
    if port_file.exists():
        port = json.loads(port_file.read_text())['port']
        if type(port) is not int or not 1024 <= port <= 65535:
            raise ValueError('Local service port configuration is damaged.')
    server = create_server(get_wsgi_application(), host='127.0.0.1', port=port, threads=1, expose_tracebacks=False)
    if not port_file.exists():
        port_file.write_text(json.dumps({'port': int(server.effective_port)}))
    print(json.dumps({'ready': True, 'origin': f'http://127.0.0.1:{server.effective_port}'}), flush=True)
    def watch_parent():
        sys.stdin.read()
        server.task_dispatcher.shutdown(cancel_pending=False, timeout=30)
        # Close idle Chromium keep-alive channels as well as the listener.
        # Otherwise an app close can leave the engine alive until TCP timeout.
        from waitress import wasyncore
        server.trigger.pull_trigger(lambda: wasyncore.close_all(server._map))
    threading.Thread(target=watch_parent, daemon=True).start()
    try:
        server.run()
    finally:
        from django.db import connections
        connections.close_all()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc(file=sys.stderr)
        raise SystemExit(1)
