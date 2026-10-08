#!/usr/bin/env python3
"""Local/operator backup entry point. Never overwrites an existing database."""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from ops.encrypted_backup import init_key,create_backup,verify_backup,restore_backup


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--key-file',default=os.getenv('BACKUP_KEY_FILE'))
    sub=parser.add_subparsers(dest='command',required=True)
    init=sub.add_parser('init-key');init.add_argument('path')
    create=sub.add_parser('create');create.add_argument('--directory',default=os.getenv('BACKUP_DIRECTORY','.runtime/backups'))
    verify=sub.add_parser('verify');verify.add_argument('backup')
    restore=sub.add_parser('restore');restore.add_argument('backup');restore.add_argument('--database',required=True)
    args=parser.parse_args()
    try:
        if args.command=='init-key':result={'key_file':str(init_key(args.path))}
        else:
            if not args.key_file:parser.error('Set BACKUP_KEY_FILE or pass --key-file before the subcommand.')
            if args.command=='create':result=create_backup(args.directory,args.key_file)
            elif args.command=='verify':result=verify_backup(args.backup,args.key_file)
            else:result=restore_backup(args.backup,args.key_file,args.database)
        print(json.dumps(result,indent=2))
    except Exception as exc:
        # Exception type is useful for alerting; avoid echoing any connection secrets.
        print(json.dumps({'ok':False,'operation':args.command,'error_type':type(exc).__name__,'message':'Backup operation failed. Existing source data was not overwritten. Check the key, file, connection and destination.'}),file=sys.stderr)
        return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
