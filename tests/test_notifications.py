import base64
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from pywebpush import webpush, WebPushException
import requests
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from news_notifications import public_settings, notification_payload, deliver, PushSession

class Notifications(unittest.TestCase):
    def test_public_config_never_contains_private_delivery_keys(self):
        with patch('news_notifications.client'), patch('news_notifications.ensure_keys',return_value={'public_key':'public','private_key':'PRIVATE'}):
            self.assertEqual(public_settings({'supabase_publishable_key':'public-api-key'}),{'enabled':True,'public_key':'public'})
        with patch('news_notifications.client') as db:
            self.assertEqual(public_settings({}),{'enabled':False});db.assert_not_called()

    def test_alert_is_bound_to_a_week_and_the_project_url(self):
        p=notification_payload({'release_id':'2026-W36','period_start':'2026-08-31','period_end':'2026-09-06','story_count':120},'https://example.test/aieo-brief')
        self.assertEqual(p['url'],'https://example.test/aieo-brief/')
        self.assertEqual(p['tag'],'brief-edition-2026-W36')
        self.assertIn('120 developments',p['body'])

    def test_unclaimed_delivery_does_not_send(self):
        db=MagicMock();db.rpc.return_value.execute.return_value.data=False
        sender=MagicMock()
        row={'subscription_id':'id','endpoint':'https://fcm.googleapis.com/fcm/send/test'}
        self.assertEqual(deliver(db,row,'2026-W36',{}, {},'https://example.test',sender),'skipped')
        sender.assert_not_called()

    def test_vendor_redirects_are_not_followed(self):
        with patch('requests.Session.post') as post:
            PushSession().post('https://fcm.googleapis.com/fcm/send/test',data=b'data')
            self.assertFalse(post.call_args.kwargs['allow_redirects'])
        with self.assertRaises(ValueError): PushSession().post('https://127.0.0.1/private')

    def test_actual_webpush_library_accepts_generated_key_and_encrypts_locally(self):
        private=ec.generate_private_key(ec.SECP256R1())
        der=private.private_bytes(serialization.Encoding.DER,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
        subscriber=ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)
        encode=lambda raw:base64.urlsafe_b64encode(raw).decode().rstrip('=')
        session=MagicMock(spec=requests.Session)
        response=requests.Response();response.status_code=201;session.post.return_value=response
        webpush({'endpoint':'https://fcm.googleapis.com/fcm/send/test','keys':{'p256dh':encode(subscriber),'auth':encode(b'0123456789abcdef')}},
            data=json.dumps({'title':'Local test'}),vapid_private_key=encode(der),vapid_claims={'sub':'https://example.test'},requests_session=session)
        self.assertEqual(session.post.call_count,1)
        self.assertNotIn(b'Local test',session.post.call_args.kwargs['data'])
        self.assertIn('authorization',{k.lower() for k in session.post.call_args.kwargs['headers']})
