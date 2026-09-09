import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlsplit
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from brief_digest_notifications import due_slot,selection,notification_payload,deliver

class DailyNotifications(unittest.TestCase):
    def test_amsterdam_dst_and_two_windows(self):
        for dt, expected in [('2026-09-09T06:37:00+00:00','2026-09-09-am'),('2026-09-09T05:37:00+00:00',None),('2026-09-09T16:37:00+00:00','2026-09-09-pm'),('2026-12-09T06:37:00+00:00',None),('2026-12-09T07:37:00+00:00','2026-12-09-am'),('2026-12-09T17:37:00+00:00','2026-12-09-pm'),('2026-09-09T23:00:00+00:00',None)]:
            self.assertEqual(due_slot(datetime.fromisoformat(dt)),expected)
    def fixture(self):
        return {'stories':[{'kind':'news','key':'event:aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','date':'2026-09-05','has_editorial':True,'headline':'A news story'}],
                'culture':[{'kind':'culture','key':'culture:'+'a'*24,'date':'2026-09-09','headline':'A poem'}],
                'research':[{'kind':'research','key':'paper:'+'b'*24,'date':'2026-09-07','has_editorial':True,'headline':'A paper'}]}
    def test_every_checkbox_combination_is_independent(self):
        for topics in [[],['news'],['culture'],['research'],['news','culture'],['culture','research'],['news','research'],['news','culture','research']]:
            self.assertEqual({x['kind'] for x in selection(self.fixture(),topics,'2026-09-09-am')},set(topics))
    def test_no_empty_summary_or_future_article(self):
        data=self.fixture();data['stories'][0]['has_editorial']=False;data['research'][0]['date']='2026-10-01'
        self.assertEqual([x['kind'] for x in selection(data,['news','research','culture'],'2026-09-09-am')],['culture'])
    def test_push_links_only_requested_items_and_no_private_values(self):
        p=notification_payload(self.fixture(),['culture'],'2026-09-09-am','https://brief.example.test')
        self.assertEqual(urlsplit(p['url']).netloc,'brief.example.test')
        self.assertEqual(parse_qs(urlsplit(p['url']).query)['items'],['culture:'+'a'*24])
        self.assertEqual(p['tag'],'brief-2026-09-09-am')
        self.assertIsNone(notification_payload(self.fixture(),[],'2026-09-09-am','https://brief.example.test'))
    def test_atomic_claim_required_before_any_send(self):
        db=MagicMock();db.rpc.return_value.execute.return_value.data=False;sender=MagicMock()
        self.assertEqual(deliver(db,{'subscription_id':'id','endpoint':'https://fcm.googleapis.com/fcm/send/test'},'2026-09-09-am',{}, {},'https://brief.example.test',sender),'skipped')
        sender.assert_not_called()
