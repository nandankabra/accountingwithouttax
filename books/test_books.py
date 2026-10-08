import csv
import io
from decimal import Decimal
from django.contrib.auth.models import User
from django.test import TestCase
from .models import Account,Item
from .services import create_workspace
from .tests import Fixtures


class BookNavigationTests(Fixtures,TestCase):
    def setUp(self):
        self.setup_workspace()
        self.client.force_login(self.owner)
        self.period={'start':'2026-10-01','end':'2026-10-31'}

    def ledger_fixture(self):
        first=self.post(self.payload('REC',rate='100.00',narration='Collect first invoice'))
        self.post(self.payload('PAY',rate='25.00',day='2026-10-02',narration='Office cost'))
        last=self.post(self.payload('REC',rate='50.00',day='2026-10-03',narration='Collect second invoice'))
        return first,last

    def test_ledger_filter_does_not_change_period_balances(self):
        first,_=self.ledger_fixture()
        result=self.client.get('/api/ledger/',{**self.period,'account':str(self.cash.id),'q':'Collect first','direction':'debit','sort':'newest'}).json()
        self.assertEqual(result['count'],1)
        self.assertEqual(result['rows'][0]['voucher'],first['id'])
        self.assertEqual(Decimal(result['debit']),Decimal('150'))
        self.assertEqual(Decimal(result['credit']),Decimal('25'))
        self.assertEqual(Decimal(result['closing']),Decimal('125'))
        exact=self.client.get('/api/ledger/',{**self.period,'account':str(self.cash.id),'q':'rec-000001'}).json()
        self.assertEqual(exact['rows'][0]['voucher'],first['id'])

    def test_filtered_newest_ledger_export_keeps_actual_running_balances(self):
        first,last=self.ledger_fixture()
        response=self.client.get('/api/export/ledger.csv',{**self.period,'account':str(self.cash.id),'q':'Collect','direction':'debit','sort':'newest'})
        self.assertEqual(response.status_code,200)
        records=list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
        index=next(i for i,row in enumerate(records) if row and row[0]=='Date')
        rows=records[index+1:]
        self.assertEqual([row[1] for row in rows],[last['id'],first['id']])
        self.assertEqual([Decimal(row[-1]) for row in rows],[Decimal('125'),Decimal('100')])
        self.assertIn(['Search','Collect','Direction','debit','Sort','newest'],records)

    def test_inventory_filters_preserve_stock_balances_and_export_order(self):
        purchase=self.post(self.payload())
        sale=self.post(self.payload('SAL',qty='2',day='2026-10-02',narration='Customer delivery'))
        args={**self.period,'item':str(self.item.id),'direction':'outward','q':'Customer'}
        result=self.client.get('/api/inventory/',args).json()
        self.assertEqual(result['count'],1)
        self.assertEqual(result['rows'][0]['voucher'],sale['id'])
        self.assertEqual(Decimal(result['closing']['quantity']),Decimal('8'))
        newest=self.client.get('/api/inventory/',{**self.period,'item':str(self.item.id),'sort':'newest'}).json()
        self.assertEqual([r['voucher'] for r in newest['rows']],[sale['id'],purchase['id']])
        export=self.client.get('/api/export/inventory.csv',{**args,'sort':'newest'})
        records=list(csv.reader(io.StringIO(export.content.decode('utf-8-sig'))))
        index=next(i for i,row in enumerate(records) if row and row[0]=='Date')
        self.assertEqual(len(records[index+1:]),1)
        self.assertEqual(records[index+1][1],sale['id'])
        self.assertEqual(Decimal(records[index+1][-1]),Decimal('800'))

    def test_invalid_book_controls_are_rejected(self):
        for path,master in [('/api/ledger/',{'account':str(self.cash.id)}),('/api/inventory/',{'item':str(self.item.id)})]:
            for invalid in ({'sort':'random'},{'direction':'unknown'},{'q':'x'*121}):
                self.assertEqual(self.client.get(path,{**self.period,**master,**invalid}).status_code,400)

    def test_master_pages_and_bootstrap_are_bounded_and_searchable(self):
        Account.objects.bulk_create([Account(workspace=self.ws,name=f'A customer {i:02}',kind='customer') for i in range(30)])
        Item.objects.bulk_create([Item(workspace=self.ws,name=f'Product {i:02}',unit='pcs') for i in range(30)])
        bootstrap=self.client.get('/api/bootstrap/').json()
        self.assertEqual(len(bootstrap['accounts']),25)
        self.assertEqual(len(bootstrap['items']),25)
        self.assertEqual(bootstrap['default_cash']['id'],str(self.cash.id))
        first=self.client.get('/api/masters/accounts/',{'kinds':'customer','q':'A customer'}).json()
        second=self.client.get('/api/masters/accounts/',{'kinds':'customer','q':'A customer','page':2}).json()
        self.assertEqual(first['count'],30)
        self.assertEqual(len(first['rows']),25)
        self.assertEqual(len(second['rows']),5)
        self.assertFalse({r['id'] for r in first['rows']} & {r['id'] for r in second['rows']})
        descending=self.client.get('/api/masters/items/',{'q':'Product','sort':'name-desc'}).json()
        self.assertEqual(descending['rows'][0]['name'],'Product 29')
        hidden=Account.objects.get(workspace=self.ws,name='A customer 29')
        lookup=self.client.get('/api/masters/accounts/',{'ids':str(hidden.id)}).json()
        self.assertEqual(lookup['rows'][0]['name'],hidden.name)

    def test_master_lookup_filters_never_expose_other_workspaces(self):
        other=User.objects.create_user('other-master@example.test')
        foreign_ws=create_workspace(other,'Other masters')
        foreign=Account.objects.create(workspace=foreign_ws,name='Private foreign account',kind='customer')
        result=self.client.get('/api/masters/accounts/',{'ids':f'{foreign.id},{self.customer.id}'}).json()
        self.assertEqual([r['id'] for r in result['rows']],[str(self.customer.id)])
        self.assertEqual(self.client.get('/api/masters/accounts/',{'q':'Private foreign'}).json()['count'],0)
        non_system=self.client.get('/api/masters/accounts/',{'non_system':'1'}).json()
        self.assertTrue(all(r['code'] is None for r in non_system['rows']))
        self.assertEqual(self.client.get('/api/masters/accounts/',{'ids':','.join([str(self.cash.id)]*201)}).status_code,400)
        self.assertEqual(self.client.get('/api/masters/accounts/',{'kinds':'administrator'}).status_code,400)
