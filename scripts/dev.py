#!/usr/bin/env python3
"""Bootstrap a private, Unix-socket-only development PostgreSQL cluster."""
import os
import argparse
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--host',default='127.0.0.1',help='Listen address; use 0.0.0.0 for local-network access.')
parser.add_argument('--port',type=int,default=8017)
args=parser.parse_args()
if not 1<=args.port<=65535:parser.error('Use a port from 1 to 65535.')
if args.host not in ('127.0.0.1','localhost') and not os.getenv('ALLOWED_HOSTS'):
    parser.error('Set ALLOWED_HOSTS to this machine\'s LAN IP before enabling network access.')

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
if sys.version_info < (3, 12):
    raise SystemExit('Use Python 3.12+: on this Mac run /opt/homebrew/bin/python3 scripts/dev.py')
if os.name == 'nt':
    raise SystemExit('On Windows use an existing PostgreSQL server with the PG* environment variables; see README.md.')


def run(args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def pg(name):
    result = shutil.which(name)
    if not result:
        raise SystemExit(f'{name} is required. Install PostgreSQL and add its bin directory to PATH.')
    return result


runtime = ROOT / '.runtime'
runtime.mkdir(exist_ok=True, mode=0o700)
runtime.chmod(0o700)
socket = runtime / 'socket'
socket.mkdir(exist_ok=True)
venv = ROOT / '.venv'
if not (venv / 'bin/python').exists():
    run([sys.executable, '-m', 'venv', venv])
python = venv / 'bin/python'
stamp = venv / '.dependencies-installed'
if not stamp.exists() or stamp.stat().st_mtime < max((ROOT / name).stat().st_mtime for name in ['requirements.txt','requirements-dev.txt']):
    run([python, '-m', 'pip', 'install', '-r', 'requirements-dev.txt'])
    stamp.touch()
database = runtime / 'postgres'
if not (database / 'PG_VERSION').exists():
    run([pg('initdb'), '-D', database, '--auth-local=trust', '--auth-host=scram-sha-256', '--encoding=UTF8', '--no-locale'])
status = subprocess.run([pg('pg_ctl'), '-D',str(database),'status'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
if status.returncode:
    run([pg('pg_ctl'), '-D',database,'-l',runtime / 'postgres.log','-o',f'-k {shlex.quote(str(socket))} -p 55439 -h {shlex.quote("")}', 'start'])
os.environ.update(PGHOST=str(socket),PGPORT='55439',PGDATABASE='simplebooks')
exists = run([pg('psql'), '-d','postgres','-Atc',"SELECT 1 FROM pg_database WHERE datname='simplebooks'"],capture_output=True,text=True).stdout.strip()
if not exists:
    run([pg('createdb'),'simplebooks'])
run([python,'manage.py','migrate'])
os.execv(str(python),[str(python),'manage.py','runserver',f'{args.host}:{args.port}'])
