from datetime import timedelta
import base64
import json
from django.contrib.auth.models import User
from django.test import TestCase,Client,RequestFactory,override_settings
from django.utils import timezone
from .tests import Fixtures
from .models import Subscription,AuditEvent
from .licensing import issue_key,decode_key,activate
from .engine import PostingError


class LicensingTests(Fixtures,TestCase):
    def setUp(self):
        self.setup_workspace()
        self.operator=User.objects.create_superuser('license-provider@example.test',password='Provider-test-password-915')
        self.sub=self.ws.subscription
        self.key=issue_key(self.sub,self.operator)
        self.sub.refresh_from_db()

    def activation(self,key=...,client=None):
        return (client or self.client).post('/api/activation/',json.dumps({'key':self.key if key is ... else key}),content_type='application/json')

    def test_key_is_hashed_activates_correct_account_and_never_logs_secret(self):
        self.assertNotEqual(self.key,self.sub.key_digest)
        self.assertEqual(len(self.sub.key_digest),64)
        with self.assertRaises(PostingError):self.post(self.payload())
        response=self.activation();self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(int(self.client.session['_auth_user_id']),self.owner.pk)
        self.assertEqual(self.client.session['subscription_key_version'],1)
        self.sub.refresh_from_db();self.assertIsNotNone(self.sub.activated_at)
        self.post(self.payload())
        for event in AuditEvent.objects.all():self.assertNotIn(self.key,json.dumps(event.details))
        self.assertEqual(self.client.get('/api/bootstrap/').json()['subscription']['activated'],True)

    def test_invalid_malformed_foreign_server_and_disabled_keys_are_rejected(self):
        for key in ['bad',None,[],{},'SB1.!!!!','SB1.'+base64.urlsafe_b64encode(b'{"origin":null,"token":"bad"}').decode().rstrip('=')]:
            response=self.activation(key);self.assertEqual(response.status_code,400,response.content)
        with override_settings(APP_PUBLIC_URL='https://different.example.com'):
            self.assertEqual(self.activation().status_code,400)
        self.sub.key_enabled=False;self.sub.save()
        self.assertEqual(self.activation().status_code,400)
        self.assertNotIn('_auth_user_id',self.client.session)

    def test_expiry_renewal_future_dates_and_suspension_enforced_server_side(self):
        self.assertEqual(self.activation().status_code,200)
        today=timezone.localdate();self.sub.starts_on=today-timedelta(days=2);self.sub.expires_on=today-timedelta(days=1);self.sub.save()
        with self.assertRaises(PostingError):self.post(self.payload())
        self.assertEqual(self.client.get('/api/dashboard/').status_code,200)
        fresh=Client();self.assertEqual(self.activation(client=fresh).status_code,400)
        self.sub.status='active';self.sub.expires_on=today+timedelta(days=30);self.sub.save()
        self.assertEqual(self.activation(client=fresh).status_code,200)
        self.post(self.payload())
        self.sub.status='suspended';self.sub.save()
        self.assertEqual(self.activation(client=Client()).status_code,400)
        with self.assertRaises(PostingError):self.post(self.payload())
        self.sub.status='active';self.sub.starts_on=today+timedelta(days=1);self.sub.save()
        self.assertEqual(self.activation(client=Client()).status_code,400)

    def test_rotation_revokes_old_key_and_all_old_activated_sessions(self):
        other=Client();self.activation();self.activation(client=other)
        new_key=issue_key(self.sub,self.operator)
        self.assertNotEqual(new_key,self.key)
        self.assertEqual(self.client.get('/api/bootstrap/').status_code,401)
        self.assertEqual(other.get('/api/bootstrap/').status_code,401)
        self.assertEqual(self.activation().status_code,400)
        self.assertEqual(self.activation(new_key).status_code,200)
        self.assertEqual(self.client.session['subscription_key_version'],2)

    def test_inactive_owner_and_revoked_key_block_existing_sessions(self):
        self.activation();self.sub.key_enabled=False;self.sub.save()
        self.assertEqual(self.client.get('/api/bootstrap/').status_code,401)
        self.sub.key_enabled=True;self.sub.save();self.owner.is_active=False;self.owner.save()
        self.assertEqual(self.activation().status_code,400)

    def test_key_issuance_is_provider_only_and_expired_subscriptions_cannot_issue(self):
        with self.assertRaises(PermissionError):issue_key(self.sub,self.owner)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(f'/admin/books/subscription/{self.sub.pk}/issue-key/').status_code,302)
        self.client.force_login(self.operator)
        response=self.client.get(f'/admin/books/subscription/{self.sub.pk}/issue-key/')
        self.assertContains(response,'Generate subscription key');self.assertNotContains(response,self.key)
        response=self.client.post(f'/admin/books/subscription/{self.sub.pk}/issue-key/')
        self.assertContains(response,'Copy this key now')
        self.assertIn('no-store',response['Cache-Control'])
        self.sub.refresh_from_db();self.sub.status='suspended';self.sub.save()
        self.assertContains(self.client.post(f'/admin/books/subscription/{self.sub.pk}/issue-key/'),'Set an active subscription')

    def test_activation_requires_csrf_and_rotates_authenticated_session(self):
        client=Client(enforce_csrf_checks=True)
        self.assertEqual(self.activation(client=client).status_code,403)
        self.assertEqual(client.get('/activate/').status_code,200)
        csrf=client.cookies['csrftoken'].value
        response=client.post('/api/activation/',json.dumps({'key':self.key}),content_type='application/json',HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(response.status_code,200,response.content)
        self.assertNotEqual(csrf,client.cookies['csrftoken'].value)
        self.assertEqual(client.get('/api/bootstrap/').status_code,200)

    def test_activation_throttles_valid_looking_unknown_keys(self):
        value='SB1.'+base64.urlsafe_b64encode(json.dumps({'origin':'http://127.0.0.1:8017','token':'z'*43}).encode()).decode().rstrip('=')
        for i in range(30):self.assertEqual(self.activation(value).status_code,400)
        self.assertContains(self.activation(value),'Too many activation attempts',status_code=400)

    def test_client_ui_has_no_demo_badges_or_self_signup(self):
        response=self.client.get('/login/')
        self.assertNotContains(response,'DEMO');self.assertNotContains(response,'LOCAL DEVELOPMENT');self.assertNotContains(response,'Create a workspace')
        self.activation()
        self.assertNotContains(self.client.get('/'),'DEMO BUILD')

    def test_subscription_admin_save_does_not_replace_a_newly_issued_key(self):
        from types import SimpleNamespace
        from .admin import provider_site
        stale=Subscription.objects.get(pk=self.sub.pk)
        new_key=issue_key(self.sub,self.operator)
        request=RequestFactory().post('/admin/');request.user=self.operator
        provider_site._registry[Subscription].save_model(request,stale,SimpleNamespace(),True)
        current=Subscription.objects.get(pk=self.sub.pk)
        self.assertEqual(current.key_version,2)
        self.assertEqual(current.key_digest,decode_key(new_key)[1])
        self.assertTrue(current.requires_activation)
        self.assertEqual(self.activation(new_key).status_code,200)

    def test_customer_key_never_grants_provider_administration(self):
        self.activation();self.owner.is_superuser=True;self.owner.save()
        self.assertEqual(self.client.get('/api/bootstrap/').status_code,401)
        self.assertEqual(self.activation().status_code,400)
        with self.assertRaises(ValueError):issue_key(self.sub,self.operator)
