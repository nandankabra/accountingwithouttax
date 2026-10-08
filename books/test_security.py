import io
import logging
import os
from pathlib import Path
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor
from django.contrib.auth.models import User
from django.core import mail
from django.db import connections
from django.test import TestCase,SimpleTestCase,TransactionTestCase,Client,override_settings
from cryptography.exceptions import InvalidTag
from ops.encrypted_backup import init_key,read_key,encrypt_stream,decrypt_file,BackupError,restore_backup
from .services import create_workspace
from .models import AuditEvent,AuthThrottle
from .security import consume_limit,RedactResetTokens


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',APP_PUBLIC_URL='http://testserver')
class AccountSecurityTests(TestCase):
    def setUp(self):
        self.password='Initial-testing-password-7123'
        self.user=User.objects.create_user('security@example.test',password=self.password)
        create_workspace(self.user,'Security test')

    def test_change_password_requires_current_password_and_invalidates_other_sessions(self):
        self.client.force_login(self.user)
        other=Client();other.force_login(self.user)
        p={'old_password':'wrong','new_password1':'Another-testing-password-987','new_password2':'Another-testing-password-987'}
        self.assertEqual(self.client.post('/security/',p).status_code,200)
        self.user.refresh_from_db();self.assertTrue(self.user.check_password(self.password))
        p['old_password']=self.password
        self.assertEqual(self.client.post('/security/',p).status_code,302)
        self.assertEqual(self.client.get('/api/bootstrap/').status_code,200)
        self.assertEqual(other.get('/api/bootstrap/').status_code,401)
        self.assertTrue(AuditEvent.objects.filter(action='auth.password_changed').exists())

    def test_password_reset_is_single_use_and_revokes_old_sessions(self):
        other=Client();other.force_login(self.user)
        response=self.client.post('/password-reset/',{'email':self.user.username})
        self.assertEqual(response.status_code,302)
        self.assertEqual(len(mail.outbox),1)
        path=re.search(r'http://testserver(/password-reset/confirm/\S+)',mail.outbox[0].body).group(1)
        form=self.client.get(path)
        self.assertEqual(form.status_code,302)
        replacement={'new_password1':'Reset-testing-password-989','new_password2':'Reset-testing-password-989'}
        self.assertEqual(self.client.post(form['Location'],replacement).status_code,302)
        self.user.refresh_from_db();self.assertTrue(self.user.check_password(replacement['new_password1']))
        self.assertEqual(other.get('/api/bootstrap/').status_code,401)
        self.assertFalse(self.client.get(path).context['validlink'])
        event=AuditEvent.objects.get(action='auth.reset_requested')
        self.assertIsNone(event.actor_id)
        self.assertTrue(AuditEvent.objects.filter(action='auth.password_reset').exists())

    def test_unknown_reset_address_has_same_response_and_sends_nothing(self):
        known=self.client.post('/password-reset/',{'email':self.user.username})
        unknown=self.client.post('/password-reset/',{'email':'missing@example.test'})
        self.assertEqual(known['Location'],unknown['Location'])
        self.assertEqual(len(mail.outbox),1)

    def test_reset_throttle_limits_emails_without_exposing_account_status(self):
        for _ in range(5):
            response=self.client.post('/password-reset/',{'email':self.user.username})
            self.assertEqual(response.status_code,302)
        self.assertEqual(len(mail.outbox),3)

    def test_shared_login_throttle_blocks_correct_password_after_limit(self):
        for _ in range(10):self.client.post('/login/',{'username':self.user.username,'password':'wrong'})
        response=self.client.post('/login/',{'username':self.user.username,'password':self.password})
        self.assertContains(response,'Too many attempts')
        self.assertEqual(self.client.get('/api/bootstrap/').status_code,401)
        self.assertTrue(AuthThrottle.objects.exists())
        self.assertIsNone(AuditEvent.objects.filter(action='auth.failed').first().actor_id)


class BackupCryptoTests(SimpleTestCase):
    def test_stream_roundtrip_and_random_nonce(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);keypath=init_key(root/'key');key=read_key(keypath)
            plaintext=b'Private financial fixture\n'*100000
            outputs=[]
            for index in range(2):
                encrypted=io.BytesIO();encrypt_stream(io.BytesIO(plaintext),encrypted,key)
                outputs.append(encrypted.getvalue())
            self.assertNotEqual(outputs[0],outputs[1])
            self.assertNotIn(b'Private financial fixture',outputs[0])
            (root/'encrypted').write_bytes(outputs[0])
            decrypt_file(root/'encrypted',root/'restored',key)
            self.assertEqual((root/'restored').read_bytes(),plaintext)
            with self.assertRaises(FileExistsError):init_key(keypath)

    def test_tampering_and_wrong_key_leave_no_plaintext_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);key=os.urandom(32)
            encrypted=io.BytesIO();encrypt_stream(io.BytesIO(b'secret fixture'),encrypted,key)
            data=bytearray(encrypted.getvalue());data[18]^=1
            (root/'tampered').write_bytes(data)
            with self.assertRaises(InvalidTag):decrypt_file(root/'tampered',root/'out',key)
            self.assertFalse((root/'out').exists())
            (root/'original').write_bytes(encrypted.getvalue())
            with self.assertRaises(InvalidTag):decrypt_file(root/'original',root/'out',os.urandom(32))
            self.assertFalse((root/'out').exists())

    def test_restore_rejects_source_and_system_database_names_before_decryption(self):
        for name in ('simplebooks','postgres','template0','template1','invalid-name'):
            with self.assertRaises(BackupError):restore_backup('unused','unused',name)

    def test_reset_tokens_are_redacted_from_access_logs(self):
        record=logging.LogRecord('django.server',logging.INFO,'test',1,'GET %s 200',('/password-reset/confirm/abc/secret-token/',),None)
        RedactResetTokens().filter(record)
        self.assertNotIn('secret-token',record.getMessage())
        self.assertIn('[redacted]',record.getMessage())


class SharedThrottleConcurrencyTests(TransactionTestCase):
    def test_concurrent_attempts_cannot_exceed_limit(self):
        def attempt(_):
            try:return consume_limit('test','same-account',1)
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(attempt,range(2)))
        self.assertEqual(results.count(True),1)
