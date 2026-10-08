import json
import os
from pathlib import Path
import secrets
import uuid
from django.conf import settings
from django.contrib.auth import SESSION_KEY,BACKEND_SESSION_KEY,HASH_SESSION_KEY
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.contrib.sessions.backends.db import SessionStore
from django.core.management.base import BaseCommand,CommandError
from django.db import transaction
from django.utils import timezone
from books.models import Account,Item,Workspace
from books.services import create_workspace,mutate


class Command(BaseCommand):
    help='Seed synthetic, independent workspaces in a dedicated load-test database only.'

    def add_arguments(self,parser):
        parser.add_argument('--users',type=int,default=1000)
        parser.add_argument('--output',required=True)

    def handle(self,*args,**options):
        if not settings.DATABASES['default']['NAME'].startswith('simplebooks_load_'):
            raise CommandError('Use a separate database whose name begins simplebooks_load_.')
        if Workspace.objects.exists():raise CommandError('Load-test seeding requires an empty database.')
        count=options['users']
        if not 1<=count<=1000:raise CommandError('Use 1–1000 users.')
        day=timezone.localdate().isoformat()
        password=make_password(secrets.token_urlsafe(48))
        fixtures=[]
        for index in range(count):
            with transaction.atomic():
                owner=User.objects.create(username=f'load-{index}@example.test',email=f'load-{index}@example.test',password=password)
                ws=create_workspace(owner,f'Load workspace {index}')
                cash=Account.objects.get(workspace=ws,kind='cash')
                customer=Account.objects.create(workspace=ws,name='Customer',kind='customer')
                supplier=Account.objects.create(workspace=ws,name='Supplier',kind='supplier')
                item=Item.objects.create(workspace=ws,name='Sample item',unit='pcs')
                for kind,quantity,rate,account in [('PUR','10','100.00',supplier),('SAL','2','150.00',customer)]:
                    from decimal import Decimal
                    mutate(owner,dict(kind=kind,date=day,account=str(account.id),lines=[dict(item=str(item.id),quantity=quantity,rate=rate)],expected_total=str(Decimal(quantity)*Decimal(rate)),narration='Load seed'),uuid.uuid4())
                mutate(owner,dict(kind='REC',date=day,account=str(customer.id),cash_account=str(cash.id),amount='100.00',expected_total='100.00',narration='Load seed'),uuid.uuid4())
                session=SessionStore()
                session[SESSION_KEY]=str(owner.pk)
                session[BACKEND_SESSION_KEY]='django.contrib.auth.backends.ModelBackend'
                session[HASH_SESSION_KEY]=owner.get_session_auth_hash()
                session.save()
                fixtures.append(dict(workspace=str(ws.id),session=session.session_key,csrf=secrets.token_hex(16),cash=str(cash.id),customer=str(customer.id),item=str(item.id),date=day))
            if (index+1)%100==0:self.stdout.write(f'Seeded {index+1} synthetic users')
        output=Path(options['output'])
        descriptor=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(descriptor,'w') as stream:json.dump(fixtures,stream)
        self.stdout.write(f'Fixture ready: {count} independent workspaces, 3 vouchers each.')
