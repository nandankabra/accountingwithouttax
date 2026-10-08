"""Authenticated, streaming encryption for PostgreSQL custom-format dumps.

This is logical full-backup tooling. It does not claim WAL/PITR or a measured RPO.
"""
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import tempfile
import time
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

MAGIC=b'SBK1'
CHUNK=1024*1024
MAX_BYTES=32*1024**3
ROOT=Path(__file__).resolve().parent.parent


class BackupError(RuntimeError):pass


def init_key(path):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(descriptor,'wb') as output:
        output.write(base64.b64encode(secrets.token_bytes(32))+b'\n')
    return path


def read_key(path):
    path=Path(path)
    if os.name!='nt' and path.stat().st_mode & 0o077:
        raise BackupError('The encryption key must be readable only by its owner (chmod 600).')
    try:key=base64.b64decode(path.read_bytes().strip(),validate=True)
    except ValueError:raise BackupError('Invalid backup key encoding.')
    if len(key)!=32:raise BackupError('The backup key must contain 32 random bytes.')
    return key


def encrypt_stream(source,destination,key):
    nonce=secrets.token_bytes(12)
    header=MAGIC+nonce
    encryptor=Cipher(algorithms.AES(key),modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(header)
    destination.write(header)
    count=0
    while chunk:=source.read(CHUNK):
        count+=len(chunk)
        if count>MAX_BYTES:raise BackupError('Backup exceeds the 32 GiB per-file limit; use a physical-backup service for larger databases.')
        destination.write(encryptor.update(chunk))
    destination.write(encryptor.finalize())
    destination.write(encryptor.tag)
    return count


def decrypt_file(source,destination,key):
    source,destination=Path(source),Path(destination)
    if source.stat().st_size<32 or source.stat().st_size>MAX_BYTES+32:
        raise BackupError('Invalid encrypted backup size.')
    descriptor=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(descriptor,'wb') as output,source.open('rb') as encrypted:
            header=encrypted.read(16)
            if header[:4]!=MAGIC:raise BackupError('Unsupported backup format.')
            encrypted.seek(-16,os.SEEK_END)
            tag=encrypted.read(16)
            encrypted.seek(16)
            decryptor=Cipher(algorithms.AES(key),modes.GCM(header[4:],tag)).decryptor()
            decryptor.authenticate_additional_data(header)
            remaining=source.stat().st_size-32
            while remaining:
                chunk=encrypted.read(min(CHUNK,remaining))
                if not chunk:raise BackupError('Truncated backup.')
                remaining-=len(chunk)
                output.write(decryptor.update(chunk))
            # Nothing may consume this plaintext until authentication succeeds.
            output.write(decryptor.finalize())
        return destination
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def pg_environment():
    env=dict(os.environ)
    env.setdefault('PGHOST',str(ROOT/'.runtime/socket'))
    env.setdefault('PGPORT','55439')
    env.setdefault('PGDATABASE','simplebooks')
    env.setdefault('PGCONNECT_TIMEOUT','10')
    return env


def executable(name):
    path=shutil.which(name)
    if not path:raise BackupError(f'{name} must be installed and available on PATH.')
    return path


def run_pg(arguments,env):
    result=subprocess.run([executable(arguments[0]),*map(str,arguments[1:])],env=env,capture_output=True)
    if result.returncode:
        raise BackupError(f'{arguments[0]} failed (exit {result.returncode}); check connectivity, permissions, target database and PostgreSQL version.')
    return result.stdout


def create_backup(directory,key_path):
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    key=read_key(key_path)
    started=datetime.now(timezone.utc)
    timer=time.monotonic()
    name=f'simplebooks-{started.strftime("%Y%m%dT%H%M%S")}-{secrets.token_hex(4)}.sbk'
    final=directory/name
    partial=directory/(name+'.partial')
    try:
        with tempfile.TemporaryFile() as errors:
            process=subprocess.Popen([executable('pg_dump'),'--format=custom','--no-owner','--no-acl','--no-password'],env=pg_environment(),stdout=subprocess.PIPE,stderr=errors)
            try:
                descriptor=os.open(partial,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                with os.fdopen(descriptor,'wb') as output:
                    plain_bytes=encrypt_stream(process.stdout,output,key)
                    output.flush();os.fsync(output.fileno())
                if process.wait()!=0:raise BackupError('pg_dump failed. No backup was published.')
            finally:
                if process.poll() is None:
                    process.kill();process.wait()
                process.stdout.close()
        os.replace(partial,final)
        with final.open('rb') as archive:
            digest=hashlib.file_digest(archive,'sha256').hexdigest()
        metadata={'format':'SBK1 AES-256-GCM','kind':'logical-full','file':name,'snapshot_started_at':started.isoformat(),'completed_at':datetime.now(timezone.utc).isoformat(),'duration_seconds':round(time.monotonic()-timer,3),'plaintext_bytes':plain_bytes,'encrypted_bytes':final.stat().st_size,'sha256':digest,'key_id':hashlib.sha256(key).hexdigest()[:16]}
        manifest=directory/(name+'.json')
        descriptor=os.open(manifest,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(descriptor,'w') as output:json.dump(metadata,output,indent=2)
        return metadata
    except BaseException:
        partial.unlink(missing_ok=True)
        raise


def verify_backup(path,key_path):
    with tempfile.TemporaryDirectory(prefix='simplebooks-verify-') as temp:
        dump=decrypt_file(path,Path(temp)/'verified.dump',read_key(key_path))
        listing=run_pg(['pg_restore','--list',dump],pg_environment())
        return {'verified':True,'archive_bytes':dump.stat().st_size,'toc_lines':len(listing.splitlines())}


def restore_backup(path,key_path,database):
    env=pg_environment()
    if not re.fullmatch(r'[a-z][a-z0-9_]{0,62}',database):raise BackupError('Use a simple lowercase destination database name.')
    if database in (env['PGDATABASE'],'postgres','template0','template1'):
        raise BackupError('Restore must use a separate, new database. The source and system databases are protected.')
    timer=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='simplebooks-restore-') as temp:
        dump=decrypt_file(path,Path(temp)/'verified.dump',read_key(key_path))
        run_pg(['pg_restore','--list',dump],env)
        # createdb fails if the name exists. There is no --clean or DROP command.
        run_pg(['createdb','--maintenance-db=postgres',database],env)
        run_pg(['pg_restore','--exit-on-error','--single-transaction','--no-owner','--no-acl',f'--dbname={database}',dump],env)
        counts=run_pg(['psql','--dbname',database,'--tuples-only','--no-align','--command',"SELECT json_build_object('workspaces',(SELECT count(*) FROM books_workspace),'vouchers',(SELECT count(*) FROM books_voucher),'revisions',(SELECT count(*) FROM books_voucherrevision),'audit_events',(SELECT count(*) FROM books_auditevent))"],env)
        return {'restored':True,'database':database,'duration_seconds':round(time.monotonic()-timer,3),'counts':json.loads(counts)}
