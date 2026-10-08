#!/usr/bin/env python3
"""Loopback-only synthetic capacity baseline; never targets the application's DB.

Starts a separate HTTPS Gunicorn process and a fresh PostgreSQL database. Test
sessions are issued directly so this measures already-authenticated workloads.
"""
import argparse
import asyncio
from collections import defaultdict
from datetime import datetime,timedelta,timezone
import ipaddress
import json
import math
import os
from pathlib import Path
import secrets
import socket
import ssl
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from ops.encrypted_backup import pg_environment,run_pg


def certificate(directory):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes,serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    key=ec.generate_private_key(ec.SECP256R1())
    subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Simple Books local load test')])
    now=datetime.now(timezone.utc)
    cert=x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(days=1)).add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),critical=False).sign(key,hashes.SHA256())
    cert_path,key_path=directory/'server.crt',directory/'server.key'
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    key_path.chmod(0o600)
    return cert_path,key_path


async def workload(url,fixtures,cert_path,think_seconds):
    import httpx
    context=ssl.create_default_context(cafile=str(cert_path))
    samples=defaultdict(list);application_samples=defaultdict(list);failures=[];statuses=defaultdict(int)
    active=peak_active=inflight=peak_inflight=0
    start=time.monotonic()
    limits=httpx.Limits(max_connections=len(fixtures),max_keepalive_connections=len(fixtures),keepalive_expiry=30)
    async with httpx.AsyncClient(verify=context,limits=limits,timeout=30,trust_env=False) as client:
        async def request(user,kind,path,payload=None,key=None):
            nonlocal inflight,peak_inflight
            headers={'Cookie':f"sessionid={user['session']}; csrftoken={user['csrf']}",'X-CSRFToken':user['csrf'],'Origin':url}
            if key:headers['Idempotency-Key']=key
            inflight+=1;peak_inflight=max(peak_inflight,inflight)
            timer=time.monotonic()
            try:
                response=await client.request('POST' if payload else 'GET',url+path,headers=headers,json=payload)
                elapsed=time.monotonic()-timer
                samples[kind].append(elapsed)
                timing=response.headers.get('Server-Timing','')
                if timing.startswith('app;dur='):
                    application_samples[kind].append(float(timing.split('=',1)[1])/1000)
                statuses[str(response.status_code)]+=1
                if response.status_code not in (200,201):
                    failures.append({'kind':kind,'status':response.status_code})
                    return None
                return response.json()
            except Exception as exc:
                samples[kind].append(time.monotonic()-timer)
                failures.append({'kind':kind,'error_type':type(exc).__name__})
                return None
            finally:inflight-=1

        async def user_task(index,user):
            nonlocal active,peak_active
            active+=1;peak_active=max(peak_active,active)
            try:
                # Deterministic 5-second arrival spread, followed by think time.
                await asyncio.sleep(index/len(fixtures)*5)
                bootstrap=await request(user,'normal','/api/bootstrap/')
                if not bootstrap or bootstrap['workspace']['id']!=user['workspace']:
                    failures.append({'kind':'isolation','status':'wrong workspace or authentication failure'})
                    return
                period=f"start={user['date']}&end={user['date']}"
                paths=[('dashboard','/api/dashboard/?'+period),('normal','/api/vouchers/?'+period+'&q=seed'),('ledger','/api/ledger/?'+period+'&account='+user['cash'])]
                for kind,path in paths:
                    await asyncio.sleep(think_seconds)
                    await request(user,kind,path)
                await asyncio.sleep(think_seconds)
                sale=dict(kind='SAL',date=user['date'],account=user['customer'],lines=[dict(item=user['item'],quantity='1',rate='150.00')],expected_total='150.00',narration='Load test sale')
                key=str(uuid.uuid4())
                original=await request(user,'posting','/api/vouchers/',sale,key)
                retry=await request(user,'retry','/api/vouchers/',sale,key)
                if not original or not retry or original.get('id')!=retry.get('id') or not retry.get('duplicate'):
                    failures.append({'kind':'idempotency','status':'retry did not confirm original'})
                await asyncio.sleep(think_seconds)
                receipt=dict(kind='REC',date=user['date'],account=user['customer'],cash_account=user['cash'],amount='25.00',expected_total='25.00',narration='Load test receipt')
                await request(user,'posting','/api/vouchers/',receipt,str(uuid.uuid4()))
                await asyncio.sleep(think_seconds)
                stock=await request(user,'inventory','/api/inventory/?'+period+'&item='+user['item'])
                if stock and (str(stock['closing']['quantity'])!='7.000' or str(stock['closing']['value'])!='700.00'):
                    failures.append({'kind':'reconciliation','status':'unexpected closing stock'})
            finally:active-=1
        await asyncio.gather(*(user_task(i,u) for i,u in enumerate(fixtures)))
    def stats(values):
        values=sorted(values)
        return {'requests':len(values),'p50_ms':round(values[math.ceil(len(values)*.5)-1]*1000,2),'p95_ms':round(values[math.ceil(len(values)*.95)-1]*1000,2),'max_ms':round(max(values)*1000,2)}
    return {'users':len(fixtures),'peak_active_virtual_users':peak_active,'peak_in_flight_requests':peak_inflight,'duration_seconds':round(time.monotonic()-start,2),'think_seconds':think_seconds,'metrics':{k:stats(v) for k,v in samples.items()},'application_metrics':{k:stats(v) for k,v in application_samples.items()},'http_statuses':dict(statuses),'failures':failures[:100],'failure_count':len(failures)}


def reconcile(env,users):
    import psycopg
    with psycopg.connect(dbname=env['PGDATABASE'],host=env['PGHOST'],port=env['PGPORT'],user=env.get('PGUSER') or None,password=env.get('PGPASSWORD') or None) as db:
        counts=db.execute('SELECT (SELECT count(*) FROM books_workspace),(SELECT count(*) FROM books_voucher),(SELECT count(*) FROM books_mutation)').fetchone()
        unbalanced=db.execute('SELECT count(*) FROM (SELECT j.voucher_id FROM books_journalentry j JOIN books_workspace w ON w.active_run_id=j.run_id GROUP BY j.voucher_id HAVING sum(j.debit)<>sum(j.credit)) q').fetchone()[0]
        mismatch=db.execute("WITH inventory AS (SELECT w.id,sum(j.debit-j.credit) value FROM books_workspace w JOIN books_journalentry j ON j.run_id=w.active_run_id JOIN books_account a ON a.id=j.account_id WHERE a.code='inventory' GROUP BY w.id), stock AS (SELECT w.id,sum(s.value) value,sum(s.quantity) qty FROM books_workspace w JOIN books_stockmovement s ON s.run_id=w.active_run_id GROUP BY w.id) SELECT count(*) FROM inventory i JOIN stock s ON s.id=i.id WHERE i.value<>s.value OR s.value<>700 OR s.qty<>7").fetchone()[0]
    return {'workspaces':counts[0],'vouchers':counts[1],'mutations':counts[2],'unbalanced_vouchers':unbalanced,'stock_mismatches':mismatch,'passed':counts==(users,users*5,users*5) and unbalanced==0 and mismatch==0}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--users',type=int,default=1000)
    parser.add_argument('--think-seconds',type=float,default=2)
    parser.add_argument('--port',type=int,default=8019)
    parser.add_argument('--workers',type=int,default=4)
    parser.add_argument('--threads',type=int,default=8)
    args=parser.parse_args()
    if not 1<=args.users<=1000 or args.think_seconds<0:parser.error('Use 1–1000 users and nonnegative think time.')
    if not 1<=args.workers<=8 or not 1<=args.threads<=8:parser.error('Use 1–8 workers and 1–8 threads to stay within the local database connection budget.')
    with socket.socket() as probe:probe.bind(('127.0.0.1',args.port))
    suffix=datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')+'_'+secrets.token_hex(2)
    directory=ROOT/'.runtime'/('load_'+suffix);directory.mkdir(mode=0o700)
    env=pg_environment();database='simplebooks_load_'+suffix
    run_pg(['createdb','--maintenance-db=postgres',database],env)
    env.update(PGDATABASE=database,APP_ENV='loadtest',SECRET_KEY=secrets.token_urlsafe(64),ALLOWED_HOSTS='127.0.0.1',APP_PUBLIC_URL=f'https://127.0.0.1:{args.port}',EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    cert,key=certificate(directory)
    fixture=directory/'sessions.json'
    with (directory/'setup.log').open('w') as log:
        subprocess.run([sys.executable,'manage.py','migrate','--noinput'],cwd=ROOT,env=env,stdout=log,stderr=log,check=True)
        print(f'Preparing {args.users} synthetic workspaces in {database}',flush=True)
        subprocess.run([sys.executable,'manage.py','seed_loadtest','--users',str(args.users),'--output',str(fixture)],cwd=ROOT,env=env,stdout=log,stderr=log,check=True)
    with (directory/'server.log').open('w') as log:
        server=subprocess.Popen([str(ROOT/'.venv/bin/gunicorn'),'config.wsgi:application','--bind',f'127.0.0.1:{args.port}','--workers',str(args.workers),'--threads',str(args.threads),'--worker-class','gthread','--timeout','60','--keep-alive','30','--certfile',str(cert),'--keyfile',str(key)],cwd=ROOT,env=env,stdout=log,stderr=log)
        try:
            import httpx
            context=ssl.create_default_context(cafile=str(cert))
            url=f'https://127.0.0.1:{args.port}'
            for attempt in range(100):
                if server.poll() is not None:raise RuntimeError('Load-test server failed; inspect server.log.')
                try:
                    with httpx.Client(verify=context,trust_env=False,timeout=1) as client:
                        if client.get(url+'/login/').status_code==200:break
                except httpx.HTTPError:pass
                time.sleep(.1)
            else:raise RuntimeError('Load-test server did not become ready.')
            print('Running the HTTPS workload; the normal demo server is separate.',flush=True)
            result=asyncio.run(workload(url,json.loads(fixture.read_text()),cert,args.think_seconds))
            result['reconciliation']=reconcile(env,args.users)
            result['database']=database
            result['baseline']={'seed_vouchers_per_workspace':3,'items_per_workspace':1,'server':f'{args.workers} Gunicorn gthread workers × {args.threads} threads','tls':'local certificate explicitly trusted by test client','production_claim':False}
            thresholds={'normal':2000,'dashboard':3000,'ledger':3000,'posting':3000,'inventory':3000,'retry':3000}
            result['latency_targets_passed']=all(m['p95_ms']<=thresholds[k] for k,m in result['metrics'].items())
            result['baseline_passed']=result['failure_count']==0 and result['reconciliation']['passed'] and result['latency_targets_passed']
            (directory/'result.json').write_text(json.dumps(result,indent=2))
            print(json.dumps(result,indent=2))
            print(f'Result saved: {directory}/result.json')
            return 0 if result['baseline_passed'] else 1
        finally:
            server.terminate()
            try:server.wait(timeout=10)
            except subprocess.TimeoutExpired:server.kill();server.wait()
            # Test-only sessions/private TLS keys are retained owner-readable for diagnosis.


if __name__=='__main__':raise SystemExit(main())
