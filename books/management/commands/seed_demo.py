"""Create an isolated, clearly labelled synthetic workspace for local review."""
import getpass
import os
import uuid
from decimal import Decimal
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from books.models import Account, Item
from books.services import create_workspace, mutate
from books.engine import money


class Command(BaseCommand):
    help = 'Create a new local demo workspace. Does not modify existing users.'

    def add_arguments(self, parser):
        parser.add_argument('--email', default='demo@example.test')

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError('Demo seeding is available only in development.')
        email = options['email'].lower()
        if User.objects.filter(username=email).exists():
            raise CommandError('This user already exists. Choose a different --email.')
        password = os.getenv('DEMO_PASSWORD') or getpass.getpass('Choose a local demo password (12+ characters): ')
        if len(password) < 12:
            raise CommandError('Use at least 12 characters.')
        owner = User.objects.create_user(email, password=password)
        ws = create_workspace(owner,'Mogra Trading · Demo')
        customer = Account.objects.create(workspace=ws,name='Mehta Stores',kind='customer')
        supplier = Account.objects.create(workspace=ws,name='Surat Textiles',kind='supplier')
        rent = Account.objects.create(workspace=ws,name='Shop rent',kind='expense')
        cash = Account.objects.get(workspace=ws,kind='cash')
        bag = Item.objects.create(workspace=ws,name='Cotton tote bag',unit='pcs')
        shirt = Item.objects.create(workspace=ws,name='Linen shirt',unit='pcs')
        day = timezone.localdate().isoformat()

        def post(kind, account, lines=None, amount=None, narration='', reference=None):
            data = dict(kind=kind,date=day,account=str(account.id),narration=narration)
            if lines:
                data['lines'] = [dict(item=str(i.id),quantity=q,rate=r) for i,q,r in lines]
                data['expected_total'] = str(sum((money(Decimal(q)*Decimal(r)) for _,q,r in lines),Decimal(0)))
            else:
                data.update(amount=amount,expected_total=amount,cash_account=str(cash.id))
            if reference:data['reference']=reference['id']
            return mutate(owner,data,uuid.uuid4())

        purchase=post('PUR',supplier,[(bag,'100','320.00'),(shirt,'80','600.00')],narration='New season stock · sample')
        post('PUR',supplier,[(bag,'50','360.00')],narration='Additional totes · sample')
        sale=post('SAL',customer,[(bag,'35','480.00'),(shirt,'25','950.00')],narration='Mehta Stores order · sample')
        post('REC',customer,amount='28000.00',narration='Part payment received · sample')
        post('PAY',supplier,amount='20000.00',narration='Supplier payment · sample')
        post('PAY',rent,amount='6500.00',narration='Shop rent · sample')
        post('CN',customer,[(bag,'2','480.00')],narration='Customer return · sample',reference=sale)
        post('DN',supplier,[(shirt,'3','600.00')],narration='Supplier return · sample',reference=purchase)
        self.stdout.write(self.style.SUCCESS(f'Created synthetic workspace for {email}. Sign in at http://127.0.0.1:8017/'))
