import unittest
import sys
import json
import os
import subprocess
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from datetime import datetime
from government_brief_schedule import is_due, import_due, feed_has_changes, verify_slot
from government_briefs import fingerprint, monitor_record

class GovernmentBriefScheduleTests(unittest.TestCase):
    def test_later_monitor_corrections_are_due_once(self):
        item = {'id': 'nl-story', 'country': 'Netherlands', 'country_code': 'NL',
                'url': 'https://example.nl/release', 'published_date': '2026-11-19',
                'translation_complete': True, 'classification_status': 'provisional',
                'topics': ['artificial_intelligence'], 'english_summary': 'A source claim about AI.',
                'ticker_message': 'AI policy'}
        state = {'records': {'nl-story': monitor_record(item, fingerprint(item))},
                 'checked': {'nl-story': fingerprint(item)}}
        self.assertFalse(feed_has_changes(state, {'as_of': '2026-11-19T15:00:00Z', 'items': [item]}))
        corrected = {**item, 'topics': ['military_defence']}
        self.assertTrue(feed_has_changes(state, {'as_of': '2026-11-19T16:00:00Z', 'items': [corrected]}))
        state['records'].clear()
        state['checked'].clear()
        self.assertFalse(feed_has_changes(state, {'as_of': '2026-11-19T16:00:00Z', 'items': [corrected]}))

    def test_unchanged_input_hash_with_old_generated_copy_is_due(self):
        item = {'id': 'legacy', 'country': 'Iceland', 'country_code': 'IS',
                'url': 'https://example.is/ai', 'published_date': '2026-11-26',
                'translation_complete': True, 'classification_status': 'provisional',
                'topics': ['artificial_intelligence'], 'english_summary': 'A reviewed AI literacy grant.',
                'ticker_message': 'Iceland supports AI literacy.'}
        sha = fingerprint(item)
        row = monitor_record(item, sha)
        row['body_paragraphs'] = ['Old generated AI claims.']
        state = {'records': {'legacy': row}, 'checked': {'legacy': sha}}
        snapshot = {'as_of': '2026-11-26T08:00:00Z', 'items': [item]}
        self.assertTrue(feed_has_changes(state, snapshot))
        state['records']['legacy'] = monitor_record(item, sha)
        self.assertFalse(feed_has_changes(state, snapshot))

    def test_changed_monitor_copy_and_new_ai_item_are_due(self):
        item = {'id': 'gr-story', 'country': 'Greece', 'country_code': 'GR',
                'url': 'https://example.gr/speech', 'published_date': '2026-11-19',
                'translation_complete': True, 'classification_status': 'provisional',
                'topics': ['artificial_intelligence'], 'english_summary': 'AI can raise productivity.',
                'ticker_message': 'Minister describes AI'}
        state = {'records': {'gr-story': {'id': 'gr-story'}},
                 'checked': {'gr-story': fingerprint(item)}}
        changed = {**item, 'ticker_message': 'Minister says AI can help small firms'}
        self.assertTrue(feed_has_changes(state, {'as_of': '2026-11-19T16:00:00Z', 'items': [changed]}))
        self.assertTrue(feed_has_changes({'records': {}, 'checked': {}},
                                         {'as_of': '2026-11-19T16:00:00Z', 'items': [item]}))

    def test_missing_saved_record_and_withdrawn_monitor_item_are_due(self):
        item = {'id': 'lu-story', 'country': 'Luxembourg', 'country_code': 'LU',
                'url': 'https://example.lu/release', 'published_date': '2026-11-22',
                'translation_complete': True, 'classification_status': 'provisional',
                'topics': ['artificial_intelligence'], 'english_summary': 'AI funding marketplace.'}
        state = {'records': {}, 'checked': {'lu-story': fingerprint(item)}}
        self.assertTrue(feed_has_changes(state, {'as_of': '2026-11-23T08:00:00Z', 'items': [item]}))
        state['records']['lu-story'] = {'id': 'lu-story'}
        unrelated = {**item, 'id': 'unrelated', 'topics': []}
        self.assertTrue(feed_has_changes(state, {'as_of': '2026-11-23T09:00:00Z', 'items': [unrelated]}))
        with self.assertRaisesRegex(ValueError, 'unexpectedly empty'):
            feed_has_changes(state, {'as_of': '2026-11-23T09:00:00Z', 'items': []})

    def test_twice_daily_parity_slots_follow_amsterdam_daylight_saving(self):
        winter = datetime.fromisoformat('2026-11-23T09:15:00+00:00')
        summer = datetime.fromisoformat('2026-07-23T08:15:00+00:00')
        self.assertTrue(verify_slot(winter, 'schedule', '15 9 * * *'))
        self.assertTrue(verify_slot(winter, 'schedule', '45 15 * * *'))
        self.assertFalse(verify_slot(winter, 'schedule', '15 8 * * *'))
        self.assertTrue(verify_slot(summer, 'schedule', '15 8 * * *'))
        self.assertTrue(verify_slot(summer, 'schedule', '45 14 * * *'))
        self.assertFalse(verify_slot(summer, 'schedule', '45 15 * * *'))
        self.assertFalse(verify_slot(winter, 'schedule', '35 * * * *'))
        self.assertTrue(verify_slot(winter, 'schedule', '35 * * * *', import_changed=True))

    def test_waits_until_amsterdam_publication_time(self):
        self.assertFalse(is_due({}, datetime.fromisoformat("2026-11-14T15:04:59+00:00")))

    def test_runs_after_winter_target(self):
        self.assertTrue(is_due({}, datetime.fromisoformat("2026-11-14T15:05:00+00:00")))

    def test_summer_clock_tracks_daylight_saving(self):
        self.assertFalse(is_due({}, datetime.fromisoformat("2026-07-14T14:04:59+00:00")))
        self.assertTrue(is_due({}, datetime.fromisoformat("2026-07-14T14:05:00+00:00")))

    def test_repeated_and_delayed_triggers_do_not_repeat_today(self):
        state = {"policy": "government-ai-brief-v4", "last_checked_at": "2026-11-14T15:30:00+00:00"}
        self.assertFalse(is_due(state, datetime.fromisoformat("2026-11-14T22:20:00+00:00")))

    def test_yesterday_and_checks_before_target_do_not_block_today(self):
        now = datetime.fromisoformat("2026-11-14T18:20:00+00:00")
        for checked in ("2026-11-13T19:34:14+00:00", "2026-11-14T08:00:00+00:00"):
            self.assertTrue(is_due({"policy": "government-ai-brief-v4", "last_checked_at": checked}, now))

    def test_next_day_runs_again(self):
        self.assertTrue(is_due({"policy": "government-ai-brief-v4", "last_checked_at": "2026-11-14T15:30:00Z"},
                               datetime.fromisoformat("2026-11-15T15:05:00+00:00")))

    def test_policy_change_gets_one_same_day_catch_up(self):
        self.assertTrue(is_due({"policy": "government-ai-brief-v2",
                                "last_checked_at": "2026-11-14T17:18:03Z"},
                               datetime.fromisoformat("2026-11-14T18:00:00+00:00")))

    def test_v3_import_gets_same_day_format_repair(self):
        self.assertTrue(is_due({"policy": "government-ai-brief-v3",
                                "last_checked_at": "2026-11-14T17:55:40Z"},
                               datetime.fromisoformat("2026-11-14T18:00:00+00:00")))

    def test_invalid_saved_time_fails_instead_of_hiding_work(self):
        with self.assertRaises(ValueError):
            is_due({"policy": "government-ai-brief-v4", "last_checked_at": "2026-11-14T17:30:00"},
                   datetime.fromisoformat("2026-11-14T18:20:00+00:00"))

    def test_manual_force_refresh_bypasses_saved_date_gate(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / 'state.json'
            output = Path(folder) / 'github-output'
            state.write_text(json.dumps({'policy': 'government-ai-brief-v4',
                                         'last_checked_at': '2099-12-31T23:59:59Z'}))
            env = {**os.environ, 'GITHUB_OUTPUT': str(output)}
            command = [sys.executable, str(Path(__file__).resolve().parents[1] / 'scripts' /
                                           'government_brief_schedule.py'), '--state', str(state)]
            self.assertEqual(subprocess.run(command, env=env, capture_output=True).returncode, 0)
            self.assertIn('due=false', output.read_text())
            output.write_text('')
            self.assertEqual(subprocess.run(command + ['--force'], env=env, capture_output=True).returncode, 0)
            self.assertIn('due=true', output.read_text())

    def test_pre_due_wakeup_imports_late_monitor_item_without_model_judgment(self):
        from unittest.mock import patch
        state = {'policy': 'government-ai-brief-v4',
                 'last_checked_at': '2026-11-21T15:20:00Z'}
        now = datetime.fromisoformat('2026-11-22T10:35:00+00:00')
        self.assertFalse(is_due(state, now))
        with patch('government_brief_schedule.changed_live_feed', return_value=True):
            self.assertTrue(import_due(state, now, check_feed=True))
        with patch('government_brief_schedule.changed_live_feed', return_value=False):
            self.assertFalse(import_due(state, now, check_feed=True))
