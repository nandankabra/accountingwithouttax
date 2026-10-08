import json
import csv
import io
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from unittest.mock import patch
from django.contrib.auth.models import User
from django.db import connection, connections, close_old_connections, transaction, DatabaseError
from django.db.models import Sum
from django.test import TestCase, TransactionTestCase, Client
from .engine import PostingError, money
from .models import Account, Item, Voucher, JournalEntry, StockMovement, VoucherRevision, AuditEvent, CalculationRun, Mutation
from .services import create_workspace, mutate


class Fixtures:
    def setup_workspace(self, username='owner@example.test'):
        self.owner = User.objects.create_user(username=username, password='Test-password-long-2847')
        self.ws = create_workspace(self.owner, 'Test books')
        self.customer = Account.objects.create(workspace=self.ws,name='Customer',kind='customer')
        self.supplier = Account.objects.create(workspace=self.ws,name='Supplier',kind='supplier')
        self.expense = Account.objects.get(workspace=self.ws,name='General expenses')
        self.cash = Account.objects.get(workspace=self.ws,kind='cash')
        self.item = Item.objects.create(workspace=self.ws,name='Rice',unit='kg')

    def payload(self, kind='PUR', qty='10', rate='100.00', day='2026-10-01', **extra):
        if kind in ('PAY','REC'):
            result = dict(kind=kind,date=day,account=str(self.expense.id if kind=='PAY' else self.customer.id),cash_account=str(self.cash.id),amount=rate,expected_total=rate,narration='Test entry')
        else:
            result = dict(kind=kind,date=day,account=str(self.customer.id if kind in ('SAL','CN') else self.supplier.id),lines=[dict(item=str(self.item.id),quantity=qty,rate=rate)],expected_total=str(money(Decimal(qty)*Decimal(rate))),narration='Test entry')
        result.update(extra)
        return result

    def post(self, payload, key=None, **kwargs):
        return mutate(self.owner,payload,key or uuid.uuid4(),**kwargs)

    def current_stock(self):
        self.ws.refresh_from_db()
        sums=StockMovement.objects.filter(run=self.ws.active_run,item=self.item).aggregate(q=Sum('quantity'),v=Sum('value'))
        return (sums['q'] or Decimal(0),sums['v'] or Decimal(0))


class AccountingTests(Fixtures, TestCase):
    def setUp(self):
        self.setup_workspace()

    def test_all_six_types_reconcile_perpetual_inventory(self):
        purchase=self.post(self.payload())
        self.post(self.payload(qty='10',rate='200.00',day='2026-10-02'))
        sale=self.post(self.payload('SAL',qty='5',rate='250.00',day='2026-10-03'))
        self.post(self.payload('CN',qty='1',rate='250.00',day='2026-10-04',reference=sale['id']))
        self.post(self.payload('DN',qty='2',rate='100.00',day='2026-10-05',reference=purchase['id']))
        self.post(self.payload('PAY',rate='50.00'))
        self.post(self.payload('REC',rate='100.00'))
        self.assertEqual(self.current_stock(),(Decimal('14'),Decimal('2200')))
        entries=JournalEntry.objects.filter(run=self.ws.active_run)
        for voucher in Voucher.objects.all():
            totals=entries.filter(voucher=voucher).aggregate(d=Sum('debit'),c=Sum('credit'))
            self.assertEqual(totals['d'],totals['c'])
        inv=entries.filter(account__code='inventory').aggregate(d=Sum('debit'),c=Sum('credit'))
        self.assertEqual(inv['d']-inv['c'],Decimal('2200'))
        cogs=entries.filter(account__code='cogs').aggregate(d=Sum('debit'),c=Sum('credit'))
        self.assertEqual(cogs['d']-cogs['c'],Decimal('600'))

    def test_duplicate_submission_and_payload_conflict(self):
        key=uuid.uuid4();p=self.payload()
        first=self.post(p,key);second=self.post(p,key)
        self.assertEqual(first['id'],second['id'])
        self.assertTrue(second['duplicate'])
        self.assertEqual(Voucher.objects.count(),1)
        with self.assertRaises(PostingError):
            self.post(self.payload(qty='11'),key)

    def test_rounding_half_up_and_tampered_total(self):
        self.assertEqual(money('1.005'),Decimal('1.01'))
        self.post(self.payload(qty='0.005',rate='1.00'))
        self.assertEqual(self.current_stock(),(Decimal('.005'),Decimal('.01')))
        with self.assertRaises(PostingError):
            self.post(self.payload(expected_total='1.00'))
        with self.assertRaises(PostingError):
            self.post(self.payload('PAY',rate='0.001'))

    def test_large_document_total_is_exact_and_sub_paise_tampering_rejected(self):
        self.post(self.payload(qty='20000',rate='100000.00'))
        self.assertEqual(self.current_stock()[1],Decimal('2000000000.00'))
        with self.assertRaises(PostingError):
            self.post(self.payload('PAY',rate='1.00',expected_total='1.004'))

    def test_negative_stock_rolls_back_every_record(self):
        self.post(self.payload(qty='1'))
        counts=[m.objects.count() for m in (Voucher,VoucherRevision,CalculationRun,JournalEntry,StockMovement,AuditEvent,Mutation)]
        with self.assertRaises(PostingError):
            self.post(self.payload('SAL',qty='2',day='2026-10-02'))
        self.assertEqual(counts,[m.objects.count() for m in (Voucher,VoucherRevision,CalculationRun,JournalEntry,StockMovement,AuditEvent,Mutation)])

    def test_exception_during_audit_rolls_back_journal_and_stock(self):
        with patch('books.services.AuditEvent.objects.create',side_effect=RuntimeError('injected failure')):
            with self.assertRaises(RuntimeError):
                self.post(self.payload())
        for model in (Voucher,VoucherRevision,CalculationRun,JournalEntry,StockMovement,Mutation):
            self.assertEqual(model.objects.count(),0)
        self.ws.refresh_from_db();self.assertIsNone(self.ws.active_run_id)

    def test_backdated_post_and_edit_recalculate_keep_history(self):
        original=self.post(self.payload(day='2026-10-02',rate='100.00'))
        sale=self.post(self.payload('SAL',qty='5',rate='200.00',day='2026-10-03'))
        self.assertEqual(self.current_stock()[1],Decimal('500'))
        old_run=self.ws.active_run_id
        self.post(self.payload(day='2026-10-01',rate='200.00'))
        self.assertEqual(self.current_stock()[1],Decimal('2250'))
        self.post(self.payload(day='2026-10-02',rate='120.00',version=1,reason='Correct invoice cost'),voucher_id=original['id'])
        self.assertEqual(self.current_stock()[1],Decimal('2400'))
        self.assertEqual(VoucherRevision.objects.filter(voucher_id=original['id']).count(),2)
        self.assertEqual(StockMovement.objects.filter(run_id=old_run).aggregate(v=Sum('value'))['v'],Decimal('500'))
        sale_cost=JournalEntry.objects.get(run=self.ws.active_run,voucher_id=sale['id'],account__code='cogs').debit
        self.assertEqual(sale_cost,Decimal('800'))

    def test_stale_edit_and_invalid_backdate_leave_current_revision(self):
        original=self.post(self.payload())
        self.post(self.payload('SAL',qty='8',day='2026-10-02'))
        with self.assertRaises(PostingError):
            self.post(self.payload(qty='5',version=1,reason='Wrong quantity'),voucher_id=original['id'])
        self.assertEqual(Voucher.objects.get(pk=original['id']).version,1)
        with self.assertRaises(PostingError):
            self.post(self.payload(version=0,reason='Stale'),voucher_id=original['id'])
        self.assertEqual(self.current_stock(),(Decimal('2'),Decimal('200')))

    def test_partial_returns_source_cost_quantity_and_link_validation(self):
        self.post(self.payload(qty='3',rate='0.01'))
        sale=self.post(self.payload('SAL',qty='3',rate='1.00',day='2026-10-02'))
        for day in ('2026-10-03','2026-10-04','2026-10-05'):
            self.post(self.payload('CN',qty='1',rate='1.00',day=day,reference=sale['id']))
        self.assertEqual(self.current_stock(),(Decimal('3'),Decimal('.03')))
        with self.assertRaises(PostingError):
            self.post(self.payload('CN',qty='1',rate='1.00',day='2026-10-06',reference=sale['id']))
        with self.assertRaises(PostingError):
            self.post(self.payload('CN',qty='1',rate='2.00',day='2026-10-06',reference=sale['id']))

    def test_reversal_retains_original_and_is_idempotent(self):
        p=self.post(self.payload())
        s=self.post(self.payload('SAL',qty='5',day='2026-10-02'))
        key=uuid.uuid4();payload=dict(version=1,date='2026-10-03',reason='Sale cancelled')
        first=self.post(payload,key,voucher_id=s['id'],reverse=True)
        second=self.post(payload,key,voucher_id=s['id'],reverse=True)
        self.assertEqual(first['id'],second['id'])
        self.assertEqual(self.current_stock(),(Decimal('10'),Decimal('1000')))
        self.assertTrue(Voucher.objects.filter(pk=s['id']).exists())
        with self.assertRaises(PostingError):
            self.post(payload,voucher_id=s['id'],reverse=True)

    def test_cannot_reverse_source_with_active_return(self):
        self.post(self.payload())
        sale=self.post(self.payload('SAL',qty='3',day='2026-10-02'))
        returned=self.post(self.payload('CN',qty='1',day='2026-10-03',reference=sale['id']))
        p=dict(version=1,date='2026-10-04',reason='Cancellation')
        with self.assertRaises(PostingError):
            self.post(p,voucher_id=sale['id'],reverse=True)
        self.post(p,voucher_id=returned['id'],reverse=True)
        self.post(p,voucher_id=sale['id'],reverse=True)
        self.assertEqual(self.current_stock()[0],Decimal('10'))

    def test_foreign_master_and_voucher_rejected(self):
        other=User.objects.create_user('other@example.test')
        ws=create_workspace(other,'Other books')
        account=Account.objects.get(workspace=ws,kind='cash')
        with self.assertRaises(PostingError):
            self.post(self.payload('PAY',account=str(account.id)))
        foreign_item=Item.objects.create(workspace=ws,name='Foreign')
        p=self.payload();p['lines'][0]['item']=str(foreign_item.id)
        with self.assertRaises(PostingError):self.post(p)
        original=self.post(self.payload())
        with self.assertRaises(PostingError):
            mutate(other,dict(version=1,date='2026-10-01',reason='Attack'),uuid.uuid4(),original['id'],True)

    def test_input_nonfinite_float_missing_fields(self):
        for value in ('NaN','Infinity','-2','0','1.001',10.1):
            with self.assertRaises(PostingError):self.post(self.payload('PAY',rate=value))

    def test_history_cannot_be_updated_or_deleted(self):
        self.post(self.payload())
        for model in (AuditEvent,VoucherRevision,CalculationRun,JournalEntry,StockMovement,Mutation):
            row=model.objects.first()
            with self.assertRaises(DatabaseError), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(f'UPDATE {model._meta.db_table} SET id=id WHERE id=%s',[row.pk])
            with self.assertRaises(DatabaseError), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(f'DELETE FROM {model._meta.db_table} WHERE id=%s',[row.pk])

    def test_database_rejects_cross_workspace_journal(self):
        self.post(self.payload());self.ws.refresh_from_db()
        other=User.objects.create_user('other@example.test');ws=create_workspace(other,'Other')
        account=Account.objects.get(workspace=ws,kind='cash')
        with self.assertRaises(DatabaseError), transaction.atomic():
            JournalEntry.objects.create(run=self.ws.active_run,voucher=Voucher.objects.first(),account=account,date='2026-10-01',debit=1,credit=0)

    def test_fractional_return_cannot_over_refund_source(self):
        self.post(self.payload(qty='1',rate='0.01'))
        sale=self.post(self.payload('SAL',qty='1',rate='0.01',day='2026-10-02'))
        self.post(self.payload('CN',qty='0.5',rate='0.01',day='2026-10-03',reference=sale['id']))
        with self.assertRaises(PostingError):
            self.post(self.payload('CN',qty='0.5',rate='0.01',day='2026-10-04',reference=sale['id']))


class ApiTests(Fixtures, TestCase):
    def setUp(self):
        self.setup_workspace();self.client.force_login(self.owner)

    def test_every_page_and_authenticated_api(self):
        self.assertEqual(self.client.get('/').status_code,200)
        for path in ('/api/bootstrap/','/api/dashboard/','/api/vouchers/','/api/audit/'):
            self.assertEqual(self.client.get(path).status_code,200,path)
        self.client.logout()
        self.assertEqual(self.client.get('/api/bootstrap/').status_code,401)
        self.assertEqual(self.client.get('/').status_code,302)

    def test_reports_reconcile_with_vouchers_and_export_metadata(self):
        self.post(self.payload());self.post(self.payload('SAL',qty='2',day='2026-10-02'))
        p={'start':'2026-10-01','end':'2026-10-31'}
        d=self.client.get('/api/dashboard/',p).json()
        self.assertEqual(Decimal(d['totals']['PUR']),Decimal('1000'))
        self.assertEqual(Decimal(d['stock_value']),Decimal('800'))
        stock=self.client.get('/api/inventory/',{**p,'item':str(self.item.id)}).json()
        self.assertEqual(Decimal(stock['closing']['value']),Decimal('800'))
        ledger=self.client.get('/api/ledger/',{**p,'account':str(self.customer.id)}).json()
        self.assertEqual(Decimal(ledger['closing']),Decimal('200'))
        export=self.client.get('/api/export/ledger.csv',{**p,'account':str(self.customer.id)})
        self.assertEqual(export.status_code,200)
        self.assertIn(b'Generated by',export.content)
        self.assertIn(b'Test books',export.content)
        self.assertTrue(AuditEvent.objects.filter(action='ledger.exported').exists())

    def test_period_opening_and_reversal_summary(self):
        self.post(self.payload())
        s=self.post(self.payload('SAL',qty='2',day='2026-10-02'))
        self.post(dict(version=1,date='2026-10-04',reason='Cancel'),voucher_id=s['id'],reverse=True)
        p={'start':'2026-10-03','end':'2026-10-04'}
        stock=self.client.get('/api/inventory/',{**p,'item':str(self.item.id)}).json()
        self.assertEqual(Decimal(stock['opening']['quantity']),Decimal('8'))
        self.assertEqual(Decimal(stock['closing']['quantity']),Decimal('10'))
        d=self.client.get('/api/dashboard/',p).json()
        self.assertEqual(Decimal(d['totals']['SAL']),Decimal('-200'))

    def test_combined_cash_bank_drillthrough_matches_dashboard(self):
        bank=Account.objects.get(workspace=self.ws,kind='bank')
        self.post(self.payload('REC',rate='100.00'))
        self.post(self.payload('REC',rate='200.00',cash_account=str(bank.id)))
        self.post(self.payload('PAY',rate='25.00'))
        p={'start':'2026-10-01','end':'2026-10-31'}
        dashboard=self.client.get('/api/dashboard/',p).json()
        ledger=self.client.get('/api/ledger/',{**p,'account':'cash-bank'}).json()
        self.assertEqual(ledger['closing'],dashboard['cash'])
        self.assertEqual(Decimal(ledger['closing']),Decimal('275.00'))
        self.assertEqual({r['account'] for r in ledger['rows']},{'Cash','Bank'})

    def test_idor_and_csrf(self):
        p=self.post(self.payload())
        other=User.objects.create_user('other@example.test');create_workspace(other,'Other')
        self.client.force_login(other)
        self.assertEqual(self.client.get('/api/vouchers/'+p['id']+'/').status_code,404)
        self.assertEqual(self.client.get('/api/ledger/',{'account':str(self.cash.id)}).status_code,404)
        self.assertEqual(self.client.get('/api/inventory/',{'item':str(self.item.id)}).status_code,404)
        client=Client(enforce_csrf_checks=True);client.force_login(self.owner)
        self.assertEqual(client.post('/api/vouchers/',data=json.dumps(self.payload()),content_type='application/json').status_code,403)

    def test_errors_and_security_headers(self):
        response=self.client.post('/api/vouchers/',data='[1]',content_type='application/json')
        self.assertEqual(response.status_code,400)
        self.assertIn('reference_id',response.json())
        self.assertEqual(response['Cache-Control'],'no-store')
        self.assertIn("frame-ancestors 'none'",response['Content-Security-Policy'])
        self.assertEqual(self.client.get('/api/dashboard/',{'start':'bad'}).status_code,400)

    def test_signin_signout_and_signup(self):
        self.client.logout()
        self.assertEqual(self.client.get('/signup/').status_code,200)
        r=self.client.post('/signup/',{'business':'Fresh books','username':'fresh@example.test','password1':'Fresh-testing-pass-731','password2':'Fresh-testing-pass-731'})
        self.assertEqual(r.status_code,302)
        self.assertEqual(self.client.get('/api/bootstrap/').json()['workspace']['name'],'Fresh books')
        self.assertEqual(self.client.get('/logout/').status_code,405)
        self.assertEqual(self.client.post('/logout/').status_code,302)
        self.assertEqual(self.client.post('/login/',{'username':'FRESH@example.test','password':'Fresh-testing-pass-731'}).status_code,302)


class OpeningBalanceTests(Fixtures,TestCase):
    def setUp(self):self.setup_workspace()

    def opening(self, **changes):
        p=dict(kind='OPN',date='2026-09-30',balances=[dict(account=str(self.cash.id),side='debit',amount='1000.00'),dict(account=str(self.supplier.id),side='credit',amount='400.00')],lines=[dict(item=str(self.item.id),quantity='10.000',amount='500.00')],expected_total='1500.00')
        p.update(changes)
        return p

    def test_opening_posts_stock_and_balances_without_revenue_or_purchase(self):
        result=self.post(self.opening())
        self.ws.refresh_from_db()
        entries=JournalEntry.objects.filter(run=self.ws.active_run)
        total=entries.aggregate(d=Sum('debit'),c=Sum('credit'))
        self.assertEqual(total,dict(d=Decimal('1500'),c=Decimal('1500')))
        self.assertEqual(entries.get(account__code='opening_equity').credit,Decimal('1100'))
        self.assertEqual(self.current_stock(),(Decimal('10'),Decimal('500')))
        self.client.force_login(self.owner)
        d=self.client.get('/api/dashboard/',{'start':'2026-09-01','end':'2026-10-31'}).json()
        self.assertEqual(Decimal(d['cash']),Decimal('1000'))
        self.assertEqual(Decimal(d['stock_value']),Decimal('500'))
        self.assertEqual(Decimal(d['totals']['PUR']),Decimal('0'))
        self.assertEqual(self.client.get('/api/opening/').json()['voucher']['id'],result['id'])
        stock=self.client.get('/api/inventory/',{'start':'2026-10-01','end':'2026-10-31','item':str(self.item.id)}).json()
        self.assertEqual(Decimal(stock['opening']['value']),Decimal('500'))

    def test_opening_can_precede_existing_same_date_purchase(self):
        self.post(self.payload(qty='10',rate='100.00'))
        self.post(self.payload('SAL',qty='5',rate='150.00'))
        self.post(self.opening(date='2026-10-01'))
        self.assertEqual(self.current_stock(),(Decimal('15'),Decimal('1125')))

    def test_opening_edit_recalculates_later_cost_and_preserves_version(self):
        opening=self.post(self.opening())
        self.post(self.payload('SAL',qty='5',rate='150.00'))
        p=self.opening(lines=[dict(item=str(self.item.id),quantity='10',amount='600.00')],expected_total='1600.00',version=1,reason='Correct starting valuation')
        self.post(p,voucher_id=opening['id'])
        self.assertEqual(self.current_stock(),(Decimal('5'),Decimal('300')))
        self.assertEqual(VoucherRevision.objects.filter(voucher_id=opening['id']).count(),2)
        with self.assertRaises(PostingError):
            self.post(self.opening(lines=[],expected_total='1000.00',version=2,reason='Remove stock'),voucher_id=opening['id'])
        self.assertEqual(Voucher.objects.get(pk=opening['id']).version,2)

    def test_one_opening_and_no_reversal(self):
        opening=self.post(self.opening())
        with self.assertRaises(PostingError):self.post(self.opening())
        with self.assertRaises(PostingError):self.post(dict(version=1,date='2026-10-01',reason='Reverse'),voucher_id=opening['id'],reverse=True)

    def test_opening_date_and_earlier_posting_rejected(self):
        self.post(self.opening())
        with self.assertRaises(PostingError):self.post(self.payload('REC',day='2026-09-29'))
        self.post(self.payload('REC',day='2026-10-01'))
        original=Voucher.objects.get(kind='OPN')
        with self.assertRaises(PostingError):self.post(self.opening(date='2026-10-02',version=1,reason='Move opening'),voucher_id=original.id)

    def test_opening_master_validation_and_total_tampering(self):
        with self.assertRaises(PostingError):self.post(self.opening(expected_total='1400.00'))
        system=Account.objects.get(workspace=self.ws,code='inventory')
        with self.assertRaises(PostingError):self.post(self.opening(balances=[dict(account=str(system.id),side='debit',amount='1000.00')]))
        with self.assertRaises(PostingError):self.post(self.opening(lines=[dict(item=str(self.item.id),quantity='0',amount='500.00')]))
        with self.assertRaises(PostingError):self.post(self.opening(balances=self.opening()['balances']*2))

    def test_zero_cost_stock_and_fully_balanced_financial_opening(self):
        equity=Account.objects.create(workspace=self.ws,name='Owner capital',kind='equity')
        self.post(self.opening(balances=[dict(account=str(self.cash.id),side='debit',amount='1000.00'),dict(account=str(equity.id),side='credit',amount='1000.00')],lines=[dict(item=str(self.item.id),quantity='10',amount='0.00')],expected_total='1000.00'))
        self.assertEqual(self.current_stock(),(Decimal('10'),Decimal('0')))
        self.assertFalse(JournalEntry.objects.filter(run=self.ws.active_run,account__code='opening_equity').exists())
        self.post(self.payload('SAL',qty='2',rate='5.00'))
        self.assertEqual(self.current_stock(),(Decimal('8'),Decimal('0')))

    def test_reversing_earlier_partial_return_does_not_restore_cost_twice(self):
        self.post(self.opening(balances=[],lines=[dict(item=str(self.item.id),quantity='3',amount='0.01')],expected_total='0.01'))
        sale=self.post(self.payload('SAL',qty='3',rate='1.00',day='2026-10-01'))
        first=self.post(self.payload('CN',qty='1',rate='1.00',day='2026-10-02',reference=sale['id']))
        self.post(self.payload('CN',qty='1',rate='1.00',day='2026-10-03',reference=sale['id']))
        self.post(dict(version=1,date='2026-10-04',reason='Reverse earlier partial return'),voucher_id=first['id'],reverse=True)
        for day in ('2026-10-05','2026-10-06'):
            self.post(self.payload('CN',qty='1',rate='1.00',day=day,reference=sale['id']))
        self.assertEqual(self.current_stock(),(Decimal('3'),Decimal('0.01')))


class ExportTests(Fixtures,TestCase):
    def setUp(self):
        self.setup_workspace();self.client.force_login(self.owner)
        self.period=dict(start='2026-10-01',end='2026-10-31')

    def parse_csv(self,response):
        self.assertEqual(response.status_code,200)
        return list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))

    def test_voucher_item_detail_identifiers_status_and_precision(self):
        result=self.post(self.payload(qty='1.125',rate='123.45',narration='One, two\nThree'))
        self.post(dict(version=1,date='2026-10-02',reason='Cancel'),voucher_id=result['id'],reverse=True)
        rows=self.parse_csv(self.client.get('/api/export/vouchers.csv',{**self.period,'kind':'PUR'}))
        headers=rows[4];record=dict(zip(headers,rows[5]))
        self.assertEqual(record['Voucher ID'],result['id'])
        self.assertEqual(record['Status'],'reversed')
        self.assertEqual(record['Quantity'],'1.125')
        self.assertEqual(record['Rate INR'],'123.45')
        self.assertEqual(record['Line amount INR'],'138.88')
        self.assertEqual(record['Narration'],'One, two\nThree')
        self.assertEqual(len(rows),6)
        self.assertTrue(AuditEvent.objects.filter(action='vouchers.exported').exists())

    def test_inventory_export_has_opening_closing_and_source(self):
        source=self.post(self.payload(day='2026-09-30'))
        sale=self.post(self.payload('SAL',qty='2'))
        rows=self.parse_csv(self.client.get('/api/export/inventory.csv',{**self.period,'item':str(self.item.id)}))
        self.assertEqual(rows[4][1],'10.000')
        self.assertEqual(rows[5][1],'8.000')
        record=rows[next(i for i,row in enumerate(rows) if row and row[0]=='Date')+1]
        self.assertEqual(record[1],sale['id'])
        self.assertEqual(record[5],'2.000')
        self.assertTrue(AuditEvent.objects.filter(action='inventory.exported').exists())

    def test_export_text_cannot_be_a_spreadsheet_formula(self):
        self.item.name='=DANGEROUS()';self.item.save()
        self.post(self.payload(narration=' +FORMULA()'))
        rows=self.parse_csv(self.client.get('/api/export/vouchers.csv',self.period))
        record=dict(zip(rows[4],rows[5]))
        self.assertEqual(record['Item'],"'=DANGEROUS()")
        self.assertEqual(record['Narration'],"'+FORMULA()")

    def test_exports_are_workspace_isolated(self):
        original=self.post(self.payload())
        other=User.objects.create_user('other@example.test');create_workspace(other,'Other')
        self.client.force_login(other)
        self.assertEqual(self.client.get('/api/export/inventory.csv',{**self.period,'item':str(self.item.id)}).status_code,404)
        rows=self.parse_csv(self.client.get('/api/export/vouchers.csv',self.period))
        self.assertEqual(len(rows),5)
        self.assertNotIn(original['id'],str(rows))


class ConcurrencyTests(Fixtures, TransactionTestCase):
    def setUp(self):self.setup_workspace()

    def worker(self,payload,key):
        close_old_connections()
        try:
            return mutate(User.objects.get(pk=self.owner.pk),payload,key)
        except PostingError as exc:
            return str(exc)
        finally:connections.close_all()

    def test_simultaneous_duplicate_submissions(self):
        key=uuid.uuid4()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.worker(self.payload(),key),range(2)))
        self.assertEqual(Voucher.objects.count(),1)
        self.assertEqual(len({r['id'] for r in results}),1)

    def test_simultaneous_sales_cannot_oversell(self):
        self.post(self.payload(qty='10'))
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.worker(self.payload('SAL',qty='7',day='2026-10-02'),uuid.uuid4()),range(2)))
        self.assertEqual(sum(isinstance(r,dict) for r in results),1)
        self.assertEqual(self.current_stock(),(Decimal('3'),Decimal('300')))
