import copy
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import social_review_delivery as delivery


class SocialReviewDelivery(unittest.TestCase):
    def setUp(self):
        self.entry = dict(publication_week='2026-W45', status=delivery.STATUS,
                          artifact_url='https://github.com/' + delivery.REPO + '/actions/runs/123/artifacts/456',
                          run_id='123')
        self.state = {'editions': {'2026-W44': self.entry}}
        self.plan = delivery.delivery_plan(self.state, {}, date(2026, 11, 2))

    def test_current_completed_batch_is_found_after_production_was_already_recorded(self):
        self.assertEqual(self.plan['source_edition'], '2026-W44')
        self.assertEqual(self.plan['artifact_id'], '456')
        self.assertEqual(self.plan['publication_week'], '2026-W45')

    def test_old_or_previously_emailed_batch_does_not_send_again(self):
        self.assertIsNone(delivery.delivery_plan(self.state, {}, date(2026, 11, 9)))
        self.assertIsNone(delivery.delivery_plan(self.state, {'weeks': {'2026-W45': {}}}, date(2026, 11, 2)))
        self.entry['status'] = 'partial'
        self.assertIsNone(delivery.delivery_plan(self.state, {}, date(2026, 11, 2)))

    def test_wrong_repository_or_mismatched_run_is_rejected(self):
        self.entry['run_id'] = '999'
        with self.assertRaises(ValueError):
            delivery.delivery_plan(self.state, {}, date(2026, 11, 2))
        self.entry['run_id'] = '123'
        self.entry['artifact_url'] = 'https://github.com/other/repo/actions/runs/123/artifacts/456'
        with self.assertRaises(ValueError):
            delivery.delivery_plan(self.state, {}, date(2026, 11, 2))

    def test_partial_changed_or_approved_batch_cannot_be_delivered(self):
        batch = dict(status=delivery.STATUS, source_edition='2026-W44', publishing_week='2026-W45',
                     editorial_review_required=True, approval_phrase='APPROVE SOCIAL WEEK 2026-W45',
                     topics=[{}] * 15, items=[{'status': delivery.STATUS}] * 60)
        ready = dict(status=delivery.STATUS, publication_week='2026-W45', editorial_review_required=True)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / 'READY_FOR_REVIEW.json').write_text(json.dumps(ready))
            (folder / 'batch.json').write_text(json.dumps(batch))
            self.assertEqual(delivery.load_batch(folder, self.plan)[0], batch)
            for key, value in [('status', 'APPROVED'), ('source_edition', '2026-W43'), ('items', [])]:
                bad = {**batch, key: value}
                (folder / 'batch.json').write_text(json.dumps(bad))
                with self.assertRaises(ValueError):
                    delivery.load_batch(folder, self.plan)

    def test_success_records_provider_receipt_and_retry_uses_same_idempotency_key(self):
        env = dict(WEEKLY_REVIEW_TO_EMAIL=delivery.OWNER_EMAIL, RESEND_API_KEY='test-key', RESEND_FROM_EMAIL='test@example.org')
        response = Mock()
        response.json.return_value = {'id': 'email-123'}
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, env), \
                patch.object(delivery, 'RECEIPTS', Path(directory) / 'receipt.json'), \
                patch.object(delivery, 'email_content', return_value={'subject': 'draft'}), \
                patch.object(delivery.requests, 'post', return_value=response) as post:
            for _ in range(2):
                receipts = {}
                delivery.send({}, Path(directory), self.plan, 'abc', receipts)
                self.assertEqual(receipts['weeks']['2026-W45']['provider_message_id'], 'email-123')
            self.assertEqual(post.call_args_list[0].kwargs['headers']['Idempotency-Key'],
                             post.call_args_list[1].kwargs['headers']['Idempotency-Key'])
            self.assertEqual(post.call_args.kwargs['json']['to'], [delivery.OWNER_EMAIL])

    def test_failed_email_does_not_record_success(self):
        env = dict(WEEKLY_REVIEW_TO_EMAIL=delivery.OWNER_EMAIL, RESEND_API_KEY='test-key', RESEND_FROM_EMAIL='test@example.org')
        response = Mock()
        response.raise_for_status.side_effect = RuntimeError('provider failure')
        receipts = {}
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, env), \
                patch.object(delivery, 'RECEIPTS', Path(directory) / 'receipt.json'), \
                patch.object(delivery, 'email_content', return_value={}), \
                patch.object(delivery.requests, 'post', return_value=response):
            with self.assertRaises(RuntimeError):
                delivery.send({}, Path(directory), self.plan, 'abc', receipts)
            self.assertEqual(receipts, {})
            self.assertFalse(delivery.RECEIPTS.exists())

    def test_path_escape_and_changed_recipient_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                delivery.image_data(Path(directory), '../outside.jpg')
        with patch.dict(os.environ, {'WEEKLY_REVIEW_TO_EMAIL': 'other@example.org'}), \
                patch.object(delivery.requests, 'post') as post:
            with self.assertRaises(ValueError):
                delivery.send({}, Path('.'), self.plan, 'abc', {})
            post.assert_not_called()


if __name__ == '__main__':
    unittest.main()
