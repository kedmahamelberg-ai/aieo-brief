import copy
import json
import sys
import unittest
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from brief_contract import validate_pair, relationship_fingerprint
from check_observatory_update import needs_update, publication_differences, expected_period, missing_news_summaries, needs_editorial_retry
from build_site import inputs, public_evidence
from source_chronology import public_directional_counts


class WeeklyHandoff(unittest.TestCase):
    def setUp(self):
        self.release = json.loads((ROOT/'data/preview/release.json').read_text())
        self.sym = json.loads((ROOT/'data/preview/symbiosis.json').read_text())
        self.published = {'release_id': self.release['release_id'],
            'period_start': self.release['period_start'], 'period_end': self.release['period_end'],
            'source_release_sha256': self.release['content_sha256'],
            'source_relationship_sha256': relationship_fingerprint(self.sym),
            'directional_counts': validate_pair(self.release, self.sym),
            'story_count': len(self.release['evidence']),
            'stories': [{'event_id': str(row['event_id']),
                         'for_humans': public_evidence(row['axes']['human'].get('evidence')),
                         'for_ai': public_evidence(row['axes']['ai'].get('evidence')),
                         'human_direction': row['axes']['human']['direction'] if public_evidence(row['axes']['human'].get('evidence')) else 'none',
                         'ai_direction': row['axes']['ai']['direction'] if public_evidence(row['axes']['ai'].get('evidence')) else 'none'}
                        for row in self.sym['evidence']]}
        self.recount()
        self.correction_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.correction_dir.cleanup)
        self.correction_root = Path(self.correction_dir.name)

    def set_correction(self, event_id, after, recovery=False):
        if 'human_direction' in after and after['human_direction'] != 'none':
            after = {**after, 'for_humans': 'A source-supported effect on people.'}
        path = self.correction_root/'data/editorial/article-access-corrections-2026-11-15.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'schema_version': 'brief_source_audit_corrections_v1',
            'news': [{'key': 'event:' + str(event_id), 'source_urls': ['https://example.org/source'],
                      'reason': 'Source-checked correction', 'after': after,
                      'retry_when_full_source_available': recovery}]}))

    def recount(self):
        counts = self.published['directional_counts']
        for axis in counts:
            for direction in counts[axis]:
                counts[axis][direction] = sum(row[axis + '_direction'] == direction
                                               for row in self.published['stories'])


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
        self.published['stories'] = [row for row in self.published['stories'] if row['event_id'] != str(event['event_id'])]
        self.recount()
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
        status['counts']={'selected':0,'deferred':0,'blocked_rejections':1}
        self.assertFalse(needs_editorial_retry(self.release, self.published, status, now))
        status['counts']={'deferred':39}
        self.assertTrue(needs_editorial_retry(self.release, self.published, status, now))
        status['updated_at']='2026-11-01T09:30:00Z'
        self.assertFalse(needs_editorial_retry(self.release, self.published, status, now))
        status['updated_at'] = '2026-10-31T08:00:00Z'
        self.assertTrue(needs_editorial_retry(self.release, self.published, status, now))
        status['updated_at'] = '2026-11-01T08:00:00Z'
        status['counts']={'needs_model':60,'needs_rebind':0,'selected':2,'deferred':0}
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


    def test_registered_correction_matches_without_requesting_another_build(self):
        row = self.published['stories'][0]
        direction = 'loss' if row['human_direction'] != 'loss' else 'gain'
        self.set_correction(row['event_id'], {'human_direction': direction})
        row['human_direction'] = direction
        self.recount()
        self.assertFalse(needs_update(self.release, self.sym, self.published, self.correction_root))
        # The same changed article must fail without the registered correction.
        with tempfile.TemporaryDirectory() as empty:
            self.assertTrue(needs_update(self.release, self.sym, self.published, Path(empty)))

    def test_stale_article_is_not_silently_corrected_by_the_checker(self):
        row = self.published['stories'][0]
        direction = 'loss' if row['human_direction'] != 'loss' else 'gain'
        self.set_correction(row['event_id'], {'human_direction': direction})
        before = copy.deepcopy(self.published)
        reasons = publication_differences(self.release, self.sym, self.published, self.correction_root)
        self.assertTrue(any(reason.startswith('article_classifications:') for reason in reasons))
        self.assertEqual(self.published, before)

    def test_corrected_empty_box_and_reviewed_effects_follow_publication_rules(self):
        row = self.published['stories'][0]
        self.set_correction(row['event_id'], {'for_humans': '', 'for_ai': 'A supported risk.',
            'box_effects': {'human': 'none', 'ai': 'loss'}})
        row.update(human_direction='none', ai_direction='loss')
        self.recount()
        self.assertFalse(needs_update(self.release, self.sym, self.published, self.correction_root))

    def test_recovered_reading_supersedes_temporary_notice_only_with_validation(self):
        row = self.published['stories'][0]
        direction = 'loss' if row['human_direction'] != 'loss' else 'gain'
        self.set_correction(row['event_id'], {'human_direction': direction}, recovery=True)
        row.update(has_editorial=True, access_recovery_validated=True)
        self.assertFalse(needs_update(self.release, self.sym, self.published, self.correction_root))
        row['access_recovery_validated'] = False
        self.assertTrue(needs_update(self.release, self.sym, self.published, self.correction_root))

    def test_swapped_labels_fail_even_when_aggregate_counts_match(self):
        first = self.published['stories'][0]
        second = next(row for row in self.published['stories'] if row['human_direction'] != first['human_direction'])
        first['human_direction'], second['human_direction'] = second['human_direction'], first['human_direction']
        reasons = publication_differences(self.release, self.sym, self.published, self.correction_root)
        self.assertTrue(any(reason.startswith('article_classifications:') for reason in reasons))
        self.assertNotIn('directional_counts_do_not_match_articles', reasons)

    def test_published_totals_must_match_actual_articles(self):
        self.published['directional_counts']['human']['gain'] += 1
        self.assertIn('directional_counts_do_not_match_articles',
                      publication_differences(self.release, self.sym, self.published, self.correction_root))

    def test_missing_duplicate_and_unexpected_articles_are_detected(self):
        original = copy.deepcopy(self.published['stories'])
        variants = [original[:-1], original[:-1] + [original[0]],
                    original[:-1] + [{**original[-1], 'event_id': 'unexpected'}]]
        for rows in variants:
            with self.subTest(ids=[row['event_id'] for row in rows][-2:]):
                self.published['stories'] = rows
                self.assertTrue(needs_update(self.release, self.sym, self.published, self.correction_root))
        self.published['stories'] = None
        self.assertIn('stories_missing_or_invalid',
                      publication_differences(self.release, self.sym, self.published, self.correction_root))

    def test_source_bindings_and_dates_remain_required_with_corrections(self):
        for field in ('source_release_sha256', 'source_relationship_sha256', 'period_start', 'period_end', 'release_id'):
            with self.subTest(field=field):
                changed = {**self.published, field: 'stale'}
                self.assertIn(field, publication_differences(self.release, self.sym, changed, self.correction_root))


    def test_nonempty_editorial_box_uses_source_direction_even_if_upstream_prose_is_hidden(self):
        row = self.published['stories'][0]
        source = self.sym['evidence'][0]
        row['for_humans'] = 'The checked editorial explains the source-supported benefit.'
        row['human_direction'] = source['axes']['human']['direction']
        self.recount()
        self.assertFalse(needs_update(self.release, self.sym, self.published, self.correction_root))

    def test_empty_uncorrected_box_is_context_but_cannot_claim_a_benefit(self):
        row = self.published['stories'][0]
        row.update(for_humans='', human_direction='none')
        self.recount()
        self.assertFalse(needs_update(self.release, self.sym, self.published, self.correction_root))
        row['human_direction'] = 'gain'
        self.recount()
        self.assertTrue(needs_update(self.release, self.sym, self.published, self.correction_root))
