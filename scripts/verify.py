#!/usr/bin/env python3
"""Run local release checks and retain results without changing demo books."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parent.parent
if os.getenv('APP_ENV','development')!='development':raise SystemExit('Run verification with a dedicated development/test database, not production.')
commands=[
    [sys.executable,'manage.py','check'],
    [sys.executable,'manage.py','makemigrations','--check','--dry-run'],
    [sys.executable,'-m','pip','check'],
    ['node','--check','books/static/books/app.js'],
    ['node','--check','desktop/main.cjs'],
    ['node','--check','desktop/start.cjs'],
    ['node','--check','desktop/local_runtime.cjs'],
    ['node','--check','desktop/preload.cjs'],
    ['node','--check','desktop/setup.cjs'],
    ['node','--test','desktop/policy.test.cjs'],
    [sys.executable,'manage.py','test','books','--noinput'],
    [sys.executable,'manage.py','test','books','--settings=config.sqlite_test_settings','--noinput'],
    ['node','--test','desktop/local_runtime.test.cjs'],
]
results=[]
runtime=ROOT/'.runtime';runtime.mkdir(exist_ok=True)
with (runtime/'release-checks.log').open('w') as log:
    for command in commands:
        result=subprocess.run(command,cwd=ROOT,text=True,capture_output=True)
        output=result.stdout+result.stderr
        log.write('Command: '+' '.join(command)+'\n'+output+'\n')
        entry={'command':command,'exit_code':result.returncode}
        if 'test' in command:
            match=re.search(r'Ran (\d+) tests',output)
            if match:entry['tests']=int(match.group(1))
        results.append(entry)
        print(('PASS' if result.returncode==0 else 'FAIL')+' '+' '.join(command[1:]))
        if result.returncode:print(output[-3000:]);break
report={'at':datetime.now(timezone.utc).isoformat(),'passed':len(results)==len(commands) and all(r['exit_code']==0 for r in results),'checks':results}
(runtime/'release-checks.json').write_text(json.dumps(report,indent=2)+'\n')
raise SystemExit(0 if report['passed'] else 1)
