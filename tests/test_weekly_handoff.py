import copy
import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from brief_contract import validate_pair, relationship_fingerprint
from check_observatory_update import needs_update, expected_period, missing_news_summaries, needs_editorial_retry
from build_site import inputs
from source_chronology import public_directional_counts


class WeeklyHandoff(unittest.TestCase):
    def setUp(self):
        self.release = json.loads((ROOT/'data/preview/release.json').read_text())
        self.sym = json.loads((ROOT/'data/preview/symbiosis.json').read_text())
        self.published = {'release_id': self.release['release_id'],
            'source_release_sha256': self.release['content_sha256'],
            'source_relationship_sha256': relationship_fingerprint(self.sym),
            'directional_counts': validate_pair(self.release, self.sym),
            'story_count': len(self.release['evidence'])}

    def test_monday_and_sunday_bounds(self):
        zone = ZoneInfo('Europe/Amsterdam')
        self.assertEqual(expected_period(datetime(2026,9,7,2,17,tzinfo=zone)), ('2026-08-31','2026-09-06'))
        self.assertEqual(expected_period(datetime(2026,9,6,12,tzinfo=zone)), ('2026-08-24','2026-08-30'))

    def test_same_release_does_not_repeat_heavy_work(self):
        self.assertFalse(needs_update(self.release, self.sym, self.published))
        self.sym['generated_at'] = '2099-01-01T12:00:00Z'
        self.assertFalse(needs_update(self.release, self.sym, self.published))

    def test_withheld_old_source_matches_public_counts_without_retry_loop(self):
        event = self.release['evidence'][0]
        event['event_date'] = '2026-09-30'
        event['sources'] = [{'url': 'https://example.org/news/2023/old-story'}]
        self.published['story_count'] = len(self.release['evidence']) - 1
        self.published['directional_counts'] = public_directional_counts(self.release, self.sym)
        self.assertFalse(needs_update(self.release, self.sym, self.published))
        self.published['stories'] = [{'event_id': event['event_id'],
                                      'evidence_complete': True, 'has_editorial': False}]
        self.assertEqual(missing_news_summaries(self.release, self.published), 0)

    def test_deferred_editorial_resumes_after_two_hours_and_rejections_retry_daily(self):
        event = self.release['evidence'][0]
        self.published['stories'] = [{'event_id': event['event_id'],
                                      'evidence_complete': True, 'has_editorial': False}]
        now = datetime(2026, 11, 1, 12, tzinfo=ZoneInfo('Europe/Amsterdam'))
        self.assertEqual(missing_news_summaries(self.release, self.published), 1)
        self.assertTrue(needs_editorial_retry(self.release, self.published, {}, now))
        status = {'release_id': self.release['release_id'], 'updated_at': '2026-11-01T08:00:00Z'}
        self.assertFalse(needs_editorial_retry(self.release, self.published, status, now))
        status['counts']={'deferred':39}
        self.assertTrue(needs_editorial_retry(self.release, self.published, status, now))
        status['updated_at']='2026-11-01T09:30:00Z'
        self.assertFalse(needs_editorial_retry(self.release, self.published, status, now))
        status['updated_at'] = '2026-10-31T08:00:00Z'
        self.assertTrue(needs_editorial_retry(self.release, self.published, status, now))
        self.published['stories'][0]['has_editorial'] = True
        self.assertFalse(needs_editorial_retry(self.release, self.published, status, now))
        self.published['stories'][0]['has_editorial'] = False
        self.published['stories'][0]['evidence_complete'] = False
        self.assertFalse(needs_editorial_retry(self.release, self.published, status, now))
        self.published['release_id'] = '2026-W00'
        self.assertEqual(missing_news_summaries(self.release, self.published), 0)

    def test_same_week_correction_is_picked_up(self):
        self.sym['evidence'][0]['axes']['human']['direction'] = 'loss' if self.sym['evidence'][0]['axes']['human']['direction']!='loss' else 'gain'
        self.assertTrue(needs_update(self.release, self.sym, self.published))

    def test_missing_or_different_published_week_requests_update(self):
        self.assertTrue(needs_update(self.release, self.sym, {}))
        self.published['release_id'] = '2026-W34'
        self.assertTrue(needs_update(self.release, self.sym, self.published))

    def test_mixed_weeks_and_missing_rows_are_blocked(self):
        bad = copy.deepcopy(self.sym); bad['release_id']='2026-W36'
        with self.assertRaises(ValueError): needs_update(self.release, bad, self.published)
        bad = copy.deepcopy(self.sym); bad['evidence'].pop()
        with self.assertRaises(ValueError): needs_update(self.release, bad, self.published)
        self.release['counts']['ai_relevant_event_records'] += 1
        with self.assertRaises(ValueError): needs_update(self.release, self.sym, self.published)

    def test_single_sided_evidence_is_allowed(self):
        self.sym['evidence'][0]['axes']['human']['direction']='gain'
        self.sym['evidence'][0]['axes']['ai']['direction']='unresolved'
        self.assertEqual(sum(validate_pair(self.release, self.sym)['human'].values()),len(self.release['evidence']))

    def test_temporary_deployment_mismatch_is_retried(self):
        from test_complete_content_import import example_export
        good=example_export();bad=copy.deepcopy(good);bad['relationship']['release_id']='2026-W34'
        with patch('build_site.fetch',side_effect=[bad,good]) as fetch, patch('build_site.time.sleep'):
            release, sym = inputs()
        self.assertEqual(release['release_id'], sym['release_id'])
        self.assertEqual(fetch.call_count,2)
        self.assertTrue(all(call.args[0].endswith('/data/brief/current.json') for call in fetch.call_args_list))
