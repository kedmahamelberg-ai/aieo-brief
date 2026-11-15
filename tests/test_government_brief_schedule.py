import unittest
import sys
import json
import os
import subprocess
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from datetime import datetime
from government_brief_schedule import is_due

class GovernmentBriefScheduleTests(unittest.TestCase):
    def test_waits_until_amsterdam_publication_time(self):
        self.assertFalse(is_due({}, datetime.fromisoformat("2026-11-14T16:04:59+00:00")))

    def test_runs_after_winter_target(self):
        self.assertTrue(is_due({}, datetime.fromisoformat("2026-11-14T16:05:00+00:00")))

    def test_summer_clock_tracks_daylight_saving(self):
        self.assertFalse(is_due({}, datetime.fromisoformat("2026-07-14T15:04:59+00:00")))
        self.assertTrue(is_due({}, datetime.fromisoformat("2026-07-14T15:05:00+00:00")))

    def test_repeated_and_delayed_triggers_do_not_repeat_today(self):
        state = {"policy": "government-ai-brief-v4", "last_checked_at": "2026-11-14T16:30:00+00:00"}
        self.assertFalse(is_due(state, datetime.fromisoformat("2026-11-14T22:20:00+00:00")))

    def test_yesterday_and_checks_before_target_do_not_block_today(self):
        now = datetime.fromisoformat("2026-11-14T18:20:00+00:00")
        for checked in ("2026-11-13T19:34:14+00:00", "2026-11-14T08:00:00+00:00"):
            self.assertTrue(is_due({"policy": "government-ai-brief-v4", "last_checked_at": checked}, now))

    def test_next_day_runs_again(self):
        self.assertTrue(is_due({"policy": "government-ai-brief-v4", "last_checked_at": "2026-11-14T16:30:00Z"},
                               datetime.fromisoformat("2026-11-15T16:05:00+00:00")))

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
