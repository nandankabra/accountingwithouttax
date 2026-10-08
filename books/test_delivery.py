from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from io import BytesIO
import uuid
from django.contrib.auth.models import User
from django.test import TestCase,Client,RequestFactory,override_settings
from django.utils import timezone
from pypdf import PdfReader
from .models import Workspace,Subscription,SubscriptionPlan,VoucherRevision,AuditEvent,Account
from .tests import Fixtures
from .engine import PostingError


class DeliveryTests(Fixtures,TestCase):
    def setUp(self):
        self.setup_workspace();self.client.force_login(self.owner)
        self.operator=User.objects.create_superuser('operator-test@example.test',password='Operator-testing-password-729')

    def test_company_update_validation_isolation_and_stale_version(self):
        data={'name':'Updated books','mobile':'+91 98765 43210','email':'company@example.test','address':'12 Market Road\nSecond floor','city':'Surat','postcode':'395001','version':1}
        self.assertEqual(self.client.post('/company/',data).status_code,302)
        self.ws.refresh_from_db();self.assertEqual(self.ws.name,'Updated books');self.assertEqual(self.ws.profile_version,2)
        self.assertContains(self.client.post('/company/',{**data,'name':'Stale name'}),'changed on another device')
        self.ws.refresh_from_db();self.assertEqual(self.ws.name,'Updated books')
        self.assertContains(self.client.post('/company/',{**data,'version':2,'mobile':'not a phone'}),'valid mobile')
        self.assertTrue(AuditEvent.objects.filter(action='company.updated').exists())
        other=User.objects.create_user('company-other@example.test');from .services import create_workspace
        foreign=create_workspace(other,'Other company');self.client.force_login(other)
        self.client.post('/company/',{**data,'version':1,'name':'Other updated'})
        self.ws.refresh_from_db();self.assertEqual(self.ws.name,'Updated books')

    def test_owner_cannot_access_provider_admin_even_with_staff_flag(self):
        self.assertEqual(self.client.get('/admin/').status_code,302)
        self.owner.is_staff=True;self.owner.save();self.assertEqual(self.client.get('/admin/books/workspace/add/').status_code,302)
        self.client.force_login(self.operator);self.assertEqual(self.client.get('/admin/').status_code,200)
        self.assertEqual(self.client.get('/').status_code,302)

    def test_provider_login_uses_shared_throttling(self):
        self.client.logout()
        self.assertRedirects(self.client.get('/admin/login/'),'/login/')
        with override_settings(LOGIN_IP_LIMIT=1):
            self.client.post('/login/',{'username':self.operator.username,'password':'Wrong password'})
            self.assertContains(self.client.post('/login/',{'username':self.operator.username,'password':'Operator-testing-password-729'}),'Too many attempts')
            self.assertNotIn('_auth_user_id',self.client.session)

    def test_provider_account_creation_validates_credentials_and_never_promotes_existing_users(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError
        from unittest.mock import patch
        with patch.dict('os.environ',{'OPERATOR_PASSWORD':'Operator-testing-password-729'}):
            with self.assertRaises(CommandError):call_command('create_operator',email='invalid-email')
            with self.assertRaises(CommandError):call_command('create_operator',email=self.owner.username)
        self.owner.refresh_from_db();self.assertFalse(self.owner.is_superuser)

    def test_provider_managed_signup_mode_hides_and_rejects_self_signup(self):
        self.client.logout()
        with override_settings(ALLOW_SELF_SIGNUP=False):
            self.assertNotContains(self.client.get('/login/'),'Create a workspace')
            self.assertEqual(self.client.get('/signup/').status_code,403)
            self.assertEqual(self.client.post('/signup/',{}).status_code,403)

    def test_provider_creates_customer_password_and_balanced_workspace(self):
        self.client.force_login(self.operator)
        data={'name':'Client demo','customer_email':'client-demo@example.test','password1':'Client-demo-password-841','password2':'Client-demo-password-841','mobile':'919876543210','address':'Market Road','email':'office@example.test','city':'Surat','postcode':'395001','_save':'Save'}
        result=self.client.post('/admin/books/workspace/add/',data)
        self.assertEqual(result.status_code,302,result.content[:500])
        customer=User.objects.get(username=data['customer_email'])
        self.assertTrue(customer.check_password(data['password1']));self.assertFalse(customer.is_staff or customer.is_superuser)
        self.assertTrue(Subscription.objects.filter(workspace__owner=customer).exists())
        self.assertEqual(Account.objects.filter(workspace__owner=customer).count(),9)
        self.assertEqual(self.client.post('/admin/books/workspace/add/',data).status_code,200)
        self.assertEqual(User.objects.filter(username=data['customer_email']).count(),1)

    def test_expired_subscription_blocks_writes_but_preserves_read_export_and_retry(self):
        posted=self.post(self.payload(),key=uuid.UUID('00000000-0000-4000-8000-000000000001'))
        sub=self.ws.subscription;today=timezone.localdate();sub.starts_on=today-timedelta(days=10);sub.expires_on=today-timedelta(days=1);sub.save()
        with self.assertRaises(PostingError):self.post(self.payload('SAL',qty='1'))
        self.assertEqual(self.client.post('/api/masters/items/',data='{"name":"Blocked"}',content_type='application/json').status_code,403)
        self.assertEqual(self.client.get('/api/dashboard/').status_code,200)
        self.assertEqual(self.client.get(f"/api/vouchers/{posted['id']}/pdf/").status_code,200)
        repeated=self.post(self.payload(),key=uuid.UUID('00000000-0000-4000-8000-000000000001'));self.assertTrue(repeated['duplicate'])
        sub.expires_on=today+timedelta(days=30);sub.status='active';sub.save();self.post(self.payload('SAL',qty='1'))

    def test_subscription_suspension_and_renewal_are_audited(self):
        self.client.force_login(self.operator);sub=self.ws.subscription
        plan=SubscriptionPlan.objects.create(name='Monthly',price='500.00',duration_days=30)
        data={'plan':plan.pk,'status':'suspended','starts_on':sub.starts_on.isoformat(),'expires_on':sub.expires_on.isoformat(),'notes':'Manual renewal check','_save':'Save'}
        self.assertEqual(self.client.post(f'/admin/books/subscription/{sub.pk}/change/',data).status_code,302)
        self.assertTrue(AuditEvent.objects.filter(action='provider.subscription_updated').exists())
        self.ws.refresh_from_db()
        with self.assertRaises(PostingError):self.post(self.payload())

    def test_all_voucher_types_have_private_pdf_and_revision_history_is_hidden(self):
        opening=self.post(dict(kind='OPN',date='2026-09-30',balances=[dict(account=str(self.cash.id),side='debit',amount='100')],lines=[],expected_total='100'))
        purchase=self.post(self.payload());sale=self.post(self.payload('SAL',qty='2',day='2026-10-02'))
        credit=self.post(self.payload('CN',qty='1',day='2026-10-03',reference=sale['id']))
        debit=self.post(self.payload('DN',qty='1',day='2026-10-03',reference=purchase['id']))
        payment=self.post(self.payload('PAY'));receipt=self.post(self.payload('REC'))
        reversal=self.post(dict(version=1,date='2026-10-04',reason='Cancelled receipt'),voucher_id=receipt['id'],reverse=True)
        for result in [opening,purchase,sale,credit,debit,payment,receipt,reversal]:
            response=self.client.get(f"/api/vouchers/{result['id']}/pdf/")
            self.assertEqual(response.status_code,200)
            self.assertEqual(response['Content-Type'],'application/pdf')
            content='\n'.join(page.extract_text() for page in PdfReader(BytesIO(response.content)).pages)
            self.assertIn('Test books',content);self.assertIn(result['number'],content);self.assertIn('₹',content);self.assertNotIn('Revision history',content)
            self.assertNotIn('history',self.client.get(f"/api/vouchers/{result['id']}/").json())
        self.assertEqual(VoucherRevision.objects.count(),8)
        other=User.objects.create_user('pdf-other@example.test');from .services import create_workspace
        create_workspace(other,'Private company');self.client.force_login(other)
        self.assertEqual(self.client.get(f"/api/vouchers/{sale['id']}/pdf/").status_code,404)
        self.client.logout();self.assertEqual(self.client.get(f"/api/vouchers/{sale['id']}/pdf/").status_code,401)

    def test_company_details_and_long_item_names_render_without_html_injection(self):
        self.ws.name='Client <script> books';self.ws.mobile='919876543210';self.ws.address='Address with <b> literal text';self.ws.save()
        self.item.name='A long item name '*7;self.item.save()
        result=self.post(self.payload(narration='<b>Literal narration</b>'))
        response=self.client.get(f"/api/vouchers/{result['id']}/pdf/")
        content='\n'.join(page.extract_text() for page in PdfReader(BytesIO(response.content)).pages)
        self.assertIn('<script>',content);self.assertIn('919876543210',content);self.assertIn('<b>Literal narration</b>',content)

    def test_provider_profile_save_preserves_a_newer_financial_run(self):
        from .admin import provider_site
        stale=Workspace.objects.get(pk=self.ws.pk)
        result=self.post(self.payload())
        self.ws.refresh_from_db();run_id=self.ws.active_run_id
        stale.name='Provider correction'
        request=RequestFactory().post('/admin/');request.user=self.operator
        provider_site._registry[Workspace].save_model(request,stale,SimpleNamespace(),True)
        self.ws.refresh_from_db()
        self.assertEqual(self.ws.active_run_id,run_id)
        self.assertEqual(self.ws.name,'Provider correction')
        self.assertEqual(self.current_stock(),(Decimal('10'),Decimal('1000')))

    def test_long_pdf_repeats_headers_and_contains_every_line_without_internal_costs(self):
        from .models import Item
        items=[Item.objects.create(workspace=self.ws,name=f'Item {i:03d} with a long descriptive name for layout verification',unit='kg') for i in range(100)]
        payload=self.payload();payload['lines']=[{'item':str(item.id),'quantity':'1','rate':'100'} for item in items];payload['expected_total']='10000'
        result=self.post(payload)
        pdf=PdfReader(BytesIO(self.client.get(f"/api/vouchers/{result['id']}/pdf/").content))
        self.assertGreater(len(pdf.pages),2)
        content='\n'.join(page.extract_text() for page in pdf.pages)
        for i in range(100):self.assertIn(f'Item {i:03d}',content)
        self.assertIn('₹10,000.00',content);self.assertNotIn('Accounting entries',content)
        self.assertIn('Quantity',pdf.pages[1].extract_text())

    def test_provider_rejects_weak_credentials_and_invalid_subscription_dates(self):
        self.client.force_login(self.operator)
        response=self.client.post('/admin/books/workspace/add/',{'name':'Rejected customer','customer_email':'weak@example.test','password1':'password','password2':'password','_save':'Save'})
        self.assertEqual(response.status_code,200);self.assertFalse(User.objects.filter(username='weak@example.test').exists())
        sub=self.ws.subscription
        response=self.client.post(f'/admin/books/subscription/{sub.pk}/change/',{'status':'active','starts_on':'2026-10-20','expires_on':'2026-10-01','_save':'Save'})
        self.assertEqual(response.status_code,200)
        sub.refresh_from_db();self.assertNotEqual(str(sub.expires_on),'2026-10-01')
