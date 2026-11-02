import copy
import base64
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
        self.assertIsNone(delivery.delivery_plan(self.state, {'weeks': {'2026-W45': {'review_version': delivery.REVIEW_VERSION}}}, date(2026, 11, 2)))
        self.entry['status'] = 'partial'
        self.assertIsNone(delivery.delivery_plan(self.state, {}, date(2026, 11, 2)))

    def test_old_plain_review_gets_one_visual_review_upgrade(self):
        self.assertIsNotNone(delivery.delivery_plan(self.state, {'weeks': {'2026-W45': {}}}, date(2026, 11, 2)))

    def test_platform_caption_and_ordered_images_are_one_preview(self):
        item = dict(platform='instagram', account='The Brief', scheduled_at='2026-11-02T10:00:00+01:00',
                    caption='An exact caption & source', prepared_carousel_assets=['cover', 'explanation', 'cta'])
        preview = delivery.post_preview(item, dict(cover='cid:cover', explanation='cid:explanation', cta='cid:cta'))
        self.assertEqual(preview.count('<article'), 1)
        self.assertIn('An exact caption &amp; source', preview)
        self.assertLess(preview.index('cid:cover'), preview.index('cid:explanation'))
        self.assertLess(preview.index('cid:explanation'), preview.index('cid:cta'))
        self.assertLess(preview.index('<img'), preview.index('An exact caption'))
        item['platform'] = 'linkedin'
        preview = delivery.post_preview(item, dict(cover='cid:cover', explanation='cid:explanation', cta='cid:cta'))
        self.assertLess(preview.index('An exact caption'), preview.index('<img'))

    def test_repository_gate_requires_owner_exact_digest_and_original_artifact(self):
        response = Mock()
        response.json.return_value = [{'state': 'approved',
                                      'user': {'login': 'kedmahamelberg-ai', 'id': 209744145},
                                      'environments': [{'name': 'weekly-editorial'}]}]
        plan = {**self.plan, 'batch_sha256': 'abc'}
        with tempfile.TemporaryDirectory() as directory, patch.object(delivery, 'ROOT', Path(directory)), \
                patch.dict(os.environ, {'GITHUB_TOKEN': 'test'}), \
                patch.object(delivery, 'load_batch', return_value=({}, 'abc')), \
                patch.object(delivery.requests, 'get', return_value=response):
            folder = Path(directory) / 'download'; folder.mkdir()
            (folder / 'SOCIAL_REVIEW_PLAN.json').write_text(json.dumps(plan))
            state = Path(directory) / 'data/social-production/state.json'
            state.parent.mkdir(parents=True); state.write_text(json.dumps(self.state))
            delivery.approve(folder, '789')
            receipt = Path(directory) / 'data/social-production/approved/2026-W45.json'
            self.assertEqual(json.loads(receipt.read_text())['batch_sha256'], 'abc')
            receipt.unlink()
            response.json.return_value[0]['user']['id'] = 10
            with self.assertRaisesRegex(ValueError, 'owner has not approved'):
                delivery.approve(folder, '789')
            self.assertFalse(receipt.exists())
            with patch.object(delivery, 'load_batch', return_value=({}, 'different')):
                with self.assertRaisesRegex(ValueError, 'changed'):
                    delivery.approve(folder, '789')

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
                patch.object(delivery, 'email_content', return_value={'subject': 'draft', 'attachments': [{'content': base64.b64encode(b'preview').decode()}]}), \
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
                patch.object(delivery, 'email_content', return_value={'attachments': [{'content': base64.b64encode(b'preview').decode()}]}), \
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
