import json
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import social_completion as completion
import prepare_social_review as production
import social_review_delivery as delivery
import repair_social_review as repair


class SocialCompletion(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for module in (completion, production, delivery, repair):
            handle = patch.object(module, 'ROOT', self.root)
            handle.start(); self.addCleanup(handle.stop)
        self.plan = dict(publication_week='2026-W47', source_edition='2026-W46',
                        artifact_url='https://github.com/' + delivery.REPO + '/actions/runs/999/artifacts/888', run_id='999')
        self.state = {'editions': {'2026-W46': dict(self.plan, status=delivery.STATUS)}}

    def save(self, path, value):
        target = self.root / 'data/social-production' / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value))
        return target

    def test_new_artifact_and_preview_version_cannot_reopen_approved_week(self):
        self.save('approved/2026-W47.json', dict(status='APPROVED', publication_week='2026-W47', artifact_url='previous-artifact'))
        with patch.object(delivery, 'REVIEW_VERSION', 'future-preview-version'):
            self.assertIsNone(delivery.delivery_plan(self.state, {}, date(2026, 11, 17)))
        rows = [dict(kind='news', edition='2026-W46', period_start='2026-11-09', period_end='2026-11-15')]
        self.assertFalse(production.due(rows, {}, date(2026, 11, 17))[0])
        self.assertEqual(repair.needed(dict(self.plan, revision=999), self.state), (False, None))

    def test_publication_receipt_alone_locks_week_and_next_week_remains_eligible(self):
        self.save('published/2026-W47.json', dict(publishing_status='PUBLISHED_AND_SCHEDULED'))
        self.assertTrue(completion.completed_week(self.root, '2026-W47'))
        self.assertFalse(completion.completed_week(self.root, '2026-W48'))
        next_entry = dict(self.plan, publication_week='2026-W48', status=delivery.STATUS)
        self.assertIsNotNone(delivery.delivery_plan({'editions': {'2026-W47': next_entry}}, {}, date(2026, 11, 23)))

    def test_terminal_state_alone_locks_week(self):
        self.state['editions']['2026-W46']['status'] = 'PUBLISHED_AND_SCHEDULED'
        self.assertIsNone(delivery.delivery_plan(self.state, {}, date(2026, 11, 17)))

    def test_stale_send_approval_and_repair_fail_before_network_or_overwrite(self):
        approval = self.save('approved/2026-W47.json', dict(status='APPROVED', batch_sha256='original'))
        original = approval.read_bytes()
        (self.root / 'SOCIAL_REVIEW_PLAN.json').write_text(json.dumps(self.plan))
        with patch.object(delivery.requests, 'post') as post, patch.object(delivery.requests, 'get') as get:
            operations = [lambda: delivery.send({}, self.root, self.plan, 'duplicate', {}),
                          lambda: delivery.approve(self.root, '123'),
                          lambda: repair.produce(self.root, self.root, self.plan),
                          lambda: repair.record(self.root, self.plan)]
            for operation in operations:
                with self.assertRaisesRegex(ValueError, 'already approved or published'):
                    operation()
            post.assert_not_called(); get.assert_not_called()
        self.assertEqual(approval.read_bytes(), original)

    def test_production_record_cannot_replace_completed_state(self):
        self.save('published/2026-W47.json', dict(publishing_status='PUBLISHED_AND_SCHEDULED'))
        state = self.save('state.json', self.state); original = state.read_bytes()
        (self.root / 'batch.json').write_text(json.dumps({'publishing_week': '2026-W47'}))
        (self.root / 'READY_FOR_REVIEW.json').write_text(json.dumps({'status': production.STATUS}))
        with patch.object(sys, 'argv', ['prepare_social_review.py', '--record', '--output', str(self.root)]):
            with self.assertRaisesRegex(ValueError, 'already approved or published'):
                production.main()
        self.assertEqual(state.read_bytes(), original)

    def test_check_only_stops_before_live_fetch_or_rendering(self):
        week = production.datetime.now(production.ZONE).strftime('%G-W%V')
        self.save('approved/' + week + '.json', dict(status='APPROVED'))
        output = self.root / 'github-output'
        with patch.dict(os.environ, {'GITHUB_OUTPUT': str(output)}), \
             patch.object(sys, 'argv', ['prepare_social_review.py', '--check-only']), \
             patch.object(production, 'fetch') as fetch, patch.object(production, 'render') as render:
            production.main()
        fetch.assert_not_called(); render.assert_not_called()
        self.assertEqual(output.read_text(), 'needed=false\n')

    def test_explicitly_reopened_unpublished_review_is_not_terminal(self):
        self.save('approved/2026-W47.json', dict(status='SUPERSEDED_PENDING_CORRECTED_REVIEW'))
        self.assertFalse(completion.completed_week(self.root, '2026-W47'))
        self.assertIsNotNone(delivery.delivery_plan(self.state, {}, date(2026, 11, 17)))


if __name__ == '__main__':
    unittest.main()
