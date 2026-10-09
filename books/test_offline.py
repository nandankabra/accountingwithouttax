import json
import tempfile
import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.contrib.auth.models import User
from django.test import TestCase, RequestFactory, override_settings
from django.utils import timezone
from .models import OfflineLicense, Workspace, Account, JournalEntry, CalculationRun, Voucher
from .offline_licensing import b64, verify_key, licence_access, issue_offline_key
from .local_desktop import LocalOnlyMiddleware
from .services import create_workspace, mutate
from .engine import PostingError


class OfflineTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.signer = Ed25519PrivateKey.generate()
        self.installation = str(uuid.uuid4())
        public = Path(self.temp.name) / 'public.pem'
        public.write_bytes(self.signer.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        self.settings = override_settings(LOCAL_DESKTOP=True, INSTALLATION_ID=self.installation, OFFLINE_PUBLIC_KEY=str(public), LOCAL_SERVICE_TOKEN='local-test-capability')
        self.settings.enable()
        self.addCleanup(self.settings.disable)
        today = timezone.localdate()
        self.packet = {'v': 2, 'installation': self.installation, 'customer': str(uuid.uuid4()), 'company': 'Client Company', 'email': 'client@example.test', 'starts': str(today), 'expires': str(today + timedelta(days=30)), 'issued': timezone.now().isoformat()}

    def key(self, **changes):
        packet = {**self.packet, **changes}
        payload = json.dumps(packet, sort_keys=True, separators=(',', ':')).encode()
        return 'SB2.' + b64(payload) + '.' + b64(self.signer.sign(payload))

    def activate(self, key=None):
        return self.client.post('/api/activation/', json.dumps({'key': key or self.key()}), content_type='application/json')

    def test_activation_creates_empty_local_company_with_unusable_password(self):
        self.assertEqual(self.activate().status_code, 200)
        ws = Workspace.objects.get()
        self.assertEqual(str(ws.pk), self.packet['customer'])
        self.assertEqual(ws.name, 'Client Company')
        self.assertFalse(ws.owner.has_usable_password())
        self.assertFalse(Voucher.objects.exists())
        self.assertEqual(Account.objects.count(), 9)
        self.assertEqual(self.client.get('/api/bootstrap/').status_code, 200)

    def test_bad_keys_never_create_company(self):
        key = self.key()
        for value in ('SB1.invalid', key[:-1], self.key(installation=str(uuid.uuid4())), 'SB2.e30.' + 'a' * 86, self.key(v=3)):
            self.assertEqual(self.activate(value).status_code, 400)
            self.assertFalse(Workspace.objects.exists())

    def test_signature_rejects_altered_expiry(self):
        key = self.key()
        prefix, body, sig = key.split('.')
        altered = json.dumps({**self.packet, 'expires': '2099-12-31'}).encode()
        with self.assertRaises(ValueError):
            verify_key(prefix + '.' + b64(altered) + '.' + sig)

    def test_wrong_signer_is_rejected(self):
        payload = json.dumps(self.packet).encode()
        key = 'SB2.' + b64(payload) + '.' + b64(Ed25519PrivateKey.generate().sign(payload))
        self.assertEqual(self.activate(key).status_code, 400)

    def test_future_and_expired_keys_are_rejected(self):
        today = timezone.localdate()
        self.assertEqual(self.activate(self.key(starts=str(today + timedelta(days=1)))).status_code, 400)
        self.assertEqual(self.activate(self.key(starts=str(today - timedelta(days=2)), expires=str(today - timedelta(days=1)))).status_code, 400)
        self.assertFalse(Workspace.objects.exists())

    def test_expiry_blocks_writes_but_preserves_reads_and_resume(self):
        self.activate()
        ws = Workspace.objects.get()
        later = timezone.localdate() + timedelta(days=31)
        with patch('django.utils.timezone.localdate', return_value=later):
            self.assertEqual(licence_access(ws), (True, False))
            self.assertFalse(self.client.get('/api/bootstrap/').json()['subscription']['can_write'])
            self.assertEqual(self.client.post('/api/local/resume/', '{}', content_type='application/json').status_code, 200)
            self.assertEqual(self.client.post('/api/masters/items/', json.dumps({'name': 'Blocked', 'unit': 'pcs'}), content_type='application/json').status_code, 403)
            self.assertEqual(self.client.get('/api/vouchers/').status_code, 200)

    def test_renewal_preserves_company_and_vouchers(self):
        self.activate()
        ws = Workspace.objects.get()
        cash = Account.objects.get(workspace=ws, kind='cash')
        expense = Account.objects.get(workspace=ws, name='General expenses')
        result = mutate(ws.owner, {'kind': 'PAY', 'date': str(timezone.localdate()), 'amount': '10.10', 'expected_total': '10.10', 'account': str(expense.pk), 'cash_account': str(cash.pk), 'narration': 'Client expense'}, uuid.uuid4())
        key = self.key(expires=str(timezone.localdate() + timedelta(days=90)), issued=timezone.now().isoformat())
        self.assertEqual(self.activate(key).status_code, 200)
        self.assertEqual(Workspace.objects.count(), 1)
        self.assertTrue(Voucher.objects.filter(pk=result['id']).exists())
        self.assertEqual(Workspace.objects.get().subscription.expires_on, timezone.localdate() + timedelta(days=90))

    def test_foreign_company_and_old_renewal_are_rejected(self):
        self.activate()
        self.assertEqual(self.activate(self.key(customer=str(uuid.uuid4()))).status_code, 400)
        newer = self.key(issued=(timezone.now() + timedelta(seconds=1)).isoformat())
        self.assertEqual(self.activate(newer).status_code, 200)
        self.assertEqual(self.activate(self.key()).status_code, 400)

    def test_clock_rollback_and_direct_date_edit_do_not_extend_signed_expiry(self):
        self.activate()
        ws = Workspace.objects.get()
        state = OfflineLicense.objects.get()
        state.last_seen_date = timezone.localdate() + timedelta(days=1)
        state.save(update_fields=['last_seen_date'])
        self.assertEqual(licence_access(ws), (True, False))
        self.assertEqual(self.activate().status_code, 400)
        ws.subscription.expires_on = timezone.localdate() + timedelta(days=1000)
        ws.subscription.save(update_fields=['expires_on'])
        with patch('django.utils.timezone.localdate', return_value=timezone.localdate() + timedelta(days=31)):
            self.assertEqual(licence_access(ws), (True, False))

    def test_tampered_stored_key_disables_access(self):
        self.activate()
        OfflineLicense.objects.update(signed_key='SB2.invalid.invalid')
        self.assertEqual(licence_access(Workspace.objects.get()), (False, False))
        self.assertFalse(self.client.post('/api/local/resume/', '{}', content_type='application/json').json()['activated'])

    def test_backup_on_new_installation_needs_new_matching_key(self):
        self.activate()
        ws = Workspace.objects.get()
        new_id = str(uuid.uuid4())
        with override_settings(INSTALLATION_ID=new_id):
            self.assertEqual(licence_access(ws), (False, False))
            self.assertEqual(self.activate(self.key()).status_code, 400)
            renewal = self.key(installation=new_id, issued=timezone.now().isoformat())
            self.assertEqual(self.activate(renewal).status_code, 200)
            self.assertEqual(licence_access(ws), (True, True))
            self.assertEqual(Workspace.objects.count(), 1)

    def test_private_service_denies_browser_and_network_requests(self):
        factory = RequestFactory()
        middleware = LocalOnlyMiddleware(lambda request: __import__('django.http', fromlist=['HttpResponse']).HttpResponse('ok'))
        self.assertEqual(middleware(factory.get('/', REMOTE_ADDR='127.0.0.1')).status_code, 403)
        self.assertEqual(middleware(factory.get('/', REMOTE_ADDR='10.0.0.2', HTTP_X_SIMPLEBOOKS_LOCAL='local-test-capability')).status_code, 403)
        self.assertEqual(middleware(factory.get('/', REMOTE_ADDR='127.0.0.1', HTTP_X_SIMPLEBOOKS_LOCAL='local-test-capability')).status_code, 200)
        self.assertEqual(middleware(factory.get('/admin/', REMOTE_ADDR='127.0.0.1', HTTP_X_SIMPLEBOOKS_LOCAL='local-test-capability')).status_code, 404)

    def test_only_provider_can_sign_offline_keys(self):
        owner = User.objects.create_user('customer@example.test', email='customer@example.test')
        ws = create_workspace(owner, 'Provider customer')
        with self.assertRaises(PermissionError):
            issue_offline_key(ws.subscription, owner, self.installation)
        operator = User.objects.create_superuser('provider@example.test', email='provider@example.test', password='a-testing-password')
        with patch('books.offline_licensing.initialize_signer', return_value=self.signer):
            packet = verify_key(issue_offline_key(ws.subscription, operator, self.installation))
        self.assertEqual(packet['customer'], str(ws.pk))

    def test_provider_panel_generates_installation_bound_offline_key(self):
        customer = User.objects.create_user('customer@example.test', email='customer@example.test')
        ws = create_workspace(customer, 'Panel customer')
        operator = User.objects.create_superuser('provider@example.test', email='provider@example.test', password='a-testing-password')
        url = f'/admin/books/subscription/{ws.subscription.pk}/issue-offline-key/'
        self.client.force_login(customer)
        self.assertEqual(self.client.get(url, follow=True).status_code, 403)
        self.client.force_login(operator)
        with patch('books.offline_licensing.initialize_signer', return_value=self.signer):
            response = self.client.post(url, {'installation': self.installation})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'SB2.')
        self.assertEqual(verify_key(response.context['key'])['installation'], self.installation)


class ExactLocalMoneyTests(TestCase):
    def test_large_money_values_roundtrip_exactly(self):
        owner = User.objects.create_user('precision@example.test')
        ws = create_workspace(owner, 'Precision')
        cash = Account.objects.get(workspace=ws, kind='cash')
        expense = Account.objects.get(workspace=ws, name='General expenses')
        amount = '999999999.99'
        result = mutate(owner, {'kind': 'PAY', 'date': str(timezone.localdate()), 'amount': amount, 'expected_total': amount, 'account': str(expense.pk), 'cash_account': str(cash.pk), 'narration': ''}, uuid.uuid4())
        self.assertEqual(JournalEntry.objects.get(voucher_id=result['id'], debit__gt=0).debit, Decimal(amount))
        self.client.force_login(owner)
        data = self.client.get('/api/dashboard/').json()
        self.assertEqual(Decimal(data['totals']['PAY']), Decimal(amount))
        # Storage remains exact even above the product's per-input limit.
        run = CalculationRun.objects.create(workspace=ws, reason='Precision storage check')
        entry = JournalEntry.objects.create(run=run, voucher_id=result['id'], account=cash, date=timezone.localdate(), debit=Decimal('999999999999999.99'), credit=0)
        entry.refresh_from_db()
        self.assertEqual(entry.debit, Decimal('999999999999999.99'))
