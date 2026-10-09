#!/usr/bin/env python3
"""Prepare an audited offline Windows payload and build its NSIS installer."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent.parent
STAGE = ROOT / 'tmp/windows-local'
CACHE = ROOT / '.runtime/windows-build'
PYTHON_VERSION = '3.13.16'
PYTHON_SHA256 = '97dae5274cc54867065e8d5a3226e48c35017ed332a0fdb0e27d5b5821961297'


def run(args, **kwargs):
    subprocess.run([str(arg) for arg in args], cwd=kwargs.pop('cwd', ROOT), check=True, **kwargs)


def prepare():
    CACHE.mkdir(parents=True, exist_ok=True)
    archive = CACHE / f'python-{PYTHON_VERSION}-embed-amd64.zip'
    if not archive.exists():
        with urllib.request.urlopen(f'https://www.python.org/ftp/python/{PYTHON_VERSION}/{archive.name}', timeout=60) as response:
            archive.write_bytes(response.read())
    if hashlib.sha256(archive.read_bytes()).hexdigest() != PYTHON_SHA256:
        raise SystemExit('Official Python archive checksum mismatch. Remove the cached archive and retry.')
    wheels = CACHE / 'wheels'
    wheels.mkdir(exist_ok=True)
    run([sys.executable, '-m', 'pip', 'download', '--only-binary=:all:', '--platform', 'win_amd64', '--python-version', '3.13', '--implementation', 'cp', '--abi', 'cp313', '-r', ROOT / 'desktop/requirements-local.txt', '-d', wheels])
    if STAGE.exists():
        shutil.rmtree(STAGE)
    python = STAGE / 'python'
    python.mkdir(parents=True)
    with zipfile.ZipFile(archive) as source:
        source.extractall(python)
    site = python / 'Lib/site-packages'
    site.mkdir(parents=True)
    # Select pip's current resolution rather than extracting stale cached versions.
    resolved = CACHE / 'resolved'
    if resolved.exists():
        shutil.rmtree(resolved)
    run([sys.executable, '-m', 'pip', 'download', '--only-binary=:all:', '--platform', 'win_amd64', '--python-version', '3.13', '--implementation', 'cp', '--abi', 'cp313', '-r', ROOT / 'desktop/requirements-local.txt', '-d', resolved, '--no-index', '--find-links', wheels])
    dependencies = []
    for wheel in sorted(resolved.glob('*.whl')):
        dependencies.append({'file': wheel.name, 'sha256': hashlib.sha256(wheel.read_bytes()).hexdigest()})
        with zipfile.ZipFile(wheel) as source:
            source.extractall(site)
    # The embeddable runtime ignores registry/PYTHONPATH; explicit application roots only.
    (python / 'python313._pth').write_text('python313.zip\n.\nLib/site-packages\n../backend\nimport site\n')
    backend = STAGE / 'backend'
    backend.mkdir()
    for directory in ('books', 'config'):
        shutil.copytree(ROOT / directory, backend / directory, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'test*.py', '*_test*.py'))
    (backend / 'desktop').mkdir()
    shutil.copyfile(ROOT / 'desktop/local_server.py', backend / 'desktop/local_server.py')
    shutil.copyfile(ROOT / 'manage.py', backend / 'manage.py')
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    sys.path.insert(0, str(ROOT))
    import django
    django.setup()
    from books.offline_licensing import public_key_bytes
    public = public_key_bytes()
    (backend / 'config/offline-public.pem').write_bytes(public)
    (ROOT / '.runtime/offline-public.pem').write_bytes(public)
    from django.core.management import call_command
    from django.test import override_settings
    with override_settings(STATIC_ROOT=backend / 'staticfiles'):
        call_command('collectstatic', interactive=False, verbosity=0)
    (STAGE / 'runtime-manifest.json').write_text(json.dumps({'python': PYTHON_VERSION, 'python_sha256': PYTHON_SHA256, 'dependencies': dependencies, 'public_key_sha256': hashlib.sha256(public).hexdigest()}, indent=2) + '\n')
    print('Standalone payload ready. Private signing key remains in .runtime only.', flush=True)


if __name__ == '__main__':
    prepare()
    if '--prepare-only' not in sys.argv:
        run(['npm', 'run', 'build:win'], cwd=ROOT / 'desktop')
