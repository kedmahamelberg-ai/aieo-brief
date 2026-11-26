import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import government_briefs as gov


def source(**changes):
    row = {'id': 'ai-item', 'country': 'Andorra', 'country_code': 'AD',
           'url': 'https://www.govern.ad/ca/w/ai', 'published_at': '2026-11-13T23:00:00Z',
           'published_date': '2026-11-14', 'classification_status': 'provisional',
           'translation_complete': True, 'relevance': 'not_related',
           'topics': ['artificial_intelligence', 'information_influence'],
           'ticker_message': 'Andorra seeks cooperation on AI influence',
           'english_summary': 'Andorra called for international cooperation on AI-driven influence content.'}
    row.update(changes)
    return row


def snapshot(*items):
    return {'as_of': '2026-11-14T14:00:00Z', 'items': list(items)}


class GovernmentBriefsTests(unittest.TestCase):
    def test_only_monitor_ai_topic_decides_inclusion(self):
        self.assertTrue(gov.candidate(source(english_summary='The government met with regional leaders.')))
        self.assertFalse(gov.candidate(source(topics=['diplomacy_alliances'],
                                              english_summary='The government discussed AI.')))
        self.assertFalse(gov.candidate(source(topics=[])))

    def test_incomplete_or_unsafe_records_are_not_published(self):
        for changes in ({'translation_complete': False}, {'classification_status': 'needs_review'},
                        {'url': 'javascript:alert(1)'}, {'published_date': 'unknown'},
                        {'country_code': ''}, {'english_summary': ''}):
            with self.subTest(changes=changes):
                self.assertFalse(gov.candidate(source(**changes)))

    def test_monitor_date_and_text_are_reused_without_editorial_review(self):
        item = source()
        state = gov.refresh(snapshot(item), {})
        row = state['records']['ai-item']
        self.assertEqual(row['date'], '2026-11-14')
        self.assertEqual(row['headline'], item['ticker_message'])
        self.assertEqual(row['summary'], item['english_summary'])
        self.assertEqual(row['url'], item['url'])
        self.assertEqual(state['pending'], 0)
        self.assertEqual(state['failures'], [])

    def test_duplicate_ids_are_merged_and_unchanged_copy_is_preserved(self):
        state = gov.refresh(snapshot(source(), source()), {})
        self.assertEqual(len(state['records']), 1)
        state['records']['ai-item']['headline'] = 'Researcher correction'
        next_state = gov.refresh(snapshot(source()), state)
        self.assertEqual(next_state['records']['ai-item']['headline'], 'Researcher correction')

    def test_existing_checked_copy_migrates_without_overwriting(self):
        item = source()
        legacy_sha = gov.fingerprint(item, gov.PREVIOUS_POLICY)
        prior = {'policy': gov.PREVIOUS_POLICY,
                 'records': {'ai-item': {**gov.monitor_record(item, legacy_sha),
                                         'headline': 'Previously checked headline'}},
                 'checked': {'ai-item': legacy_sha}}
        state = gov.refresh(snapshot(item), prior)
        self.assertEqual(state['records']['ai-item']['headline'], 'Previously checked headline')
        self.assertEqual(state['checked']['ai-item'], gov.fingerprint(item))
        self.assertEqual(state['records']['ai-item']['input_fingerprint'], gov.fingerprint(item))

    def test_old_rejection_is_now_imported_by_monitor_label(self):
        item = source()
        prior = {'policy': gov.PREVIOUS_POLICY, 'records': {},
                 'checked': {'ai-item': gov.fingerprint(item, gov.PREVIOUS_POLICY)},
                 'retry': {'ai-item': {'attempts': 1}}}
        state = gov.refresh(snapshot(item), prior)
        self.assertIn('ai-item', state['records'])
        self.assertEqual(state['retry'], {})

    def test_long_monitor_text_is_shortened_without_excluding_item(self):
        item = source(ticker_message='AI ' * 18, english_summary='AI ' * 50)
        row = gov.monitor_record(item, gov.fingerprint(item))
        self.assertLessEqual(len(row['headline'].split()), 16)
        self.assertEqual(row['page_headline'], gov.clean(item['ticker_message']))
        self.assertLessEqual(len(row['summary'].split()), 45)
        self.assertEqual(row['body_paragraphs'], [gov.clean(item['english_summary'])])

    def test_v3_valid_copy_is_preserved_and_long_copy_reformatted(self):
        item = source()
        old_sha = gov.fingerprint(item, gov.INTERMEDIATE_POLICY)
        good = gov.monitor_record(item, old_sha)
        good['headline'] = 'Researcher correction'
        state = gov.refresh(snapshot(item), {'records': {'ai-item': good},
                                                'checked': {'ai-item': old_sha}})
        self.assertEqual(state['records']['ai-item']['headline'], 'Researcher correction')
        long_item = source(id='long', ticker_message='AI ' * 18,
                           english_summary='AI ' * 50)
        old_long_sha = gov.fingerprint(long_item, gov.INTERMEDIATE_POLICY)
        old_long = {'id': 'long', 'headline': 'AI ' * 18,
                    'summary': 'AI ' * 50}
        repaired = gov.refresh(snapshot(long_item),
                               {'records': {'long': old_long},
                                'checked': {'long': old_long_sha}})
        self.assertTrue(gov.within_brief_limits(repaired['records']['long']))

    def test_changed_evidence_replaces_old_copy(self):
        state = gov.refresh(snapshot(source()), {})
        state['records']['ai-item']['headline'] = 'Old headline'
        changed = source(ticker_message='Andorra announces new AI cooperation')
        result = gov.refresh(snapshot(changed), state)
        self.assertEqual(result['records']['ai-item']['headline'], changed['ticker_message'])

    def test_removed_ai_topic_withdraws_previous_copy(self):
        state = gov.refresh(snapshot(source()), {})
        result = gov.refresh(snapshot(source(topics=['diplomacy_alliances'])), state)
        self.assertNotIn('ai-item', result['records'])
        self.assertNotIn('ai-item', result['checked'])

    def test_missing_saved_record_is_reimported_and_absent_source_is_withdrawn(self):
        state = gov.refresh(snapshot(source()), {})
        state['records'].pop('ai-item')
        repaired = gov.refresh(snapshot(source()), state)
        self.assertIn('ai-item', repaired['records'])
        withdrawn = gov.refresh(snapshot(source(id='replacement')), repaired)
        self.assertNotIn('ai-item', withdrawn['records'])
        self.assertNotIn('ai-item', withdrawn['checked'])

    def test_invalid_snapshot_preserves_checkpoint(self):
        with self.assertRaises(ValueError):
            gov.refresh({'items': []}, {})

    def test_engagement_identity_stays_stable(self):
        state = gov.refresh(snapshot(source()), {})
        import unittest.mock
        with unittest.mock.patch.object(gov, 'load', return_value=state):
            a = gov.cards()[0]
            b = gov.cards()[0]
        self.assertEqual(a['key'], b['key'])
        self.assertEqual(a['section'], 'governments')
        self.assertEqual(a['summary_basis'], 'Monitor government narrative · AI topic label')

    def test_photo_selection_and_unique_listing(self):
        from unittest.mock import patch
        stories = [
            source(id='a', country='China', country_code='CN', ticker_message='Xi and Trump discuss AI',
                   english_summary='China and the United States discussed AI.'),
            source(id='b', country='China', country_code='CN', ticker_message='Xi Jinping discusses AI'),
            source(id='c', country='China', country_code='CN', ticker_message='Xi Jinping visits a port'),
            source(id='d', country='China', country_code='CN', ticker_message='China opens a summit'),
            source(id='e', country='China', country_code='CN', ticker_message='China sets a date'),
            source(id='f', country='Andorra', country_code='AD')]
        with patch.object(gov, 'load', return_value=gov.refresh(snapshot(*stories), {})):
            cards = {card['id']:card for card in gov.cards()}
        shown = [card['government_photo'] for card in cards.values() if card.get('show_feed_photo')]
        self.assertEqual(len(shown), 3)
        self.assertEqual(len({p['sha256'] for p in shown}), len(shown))
        self.assertEqual(cards['a']['government_photo']['subjects'], ['Xi Jinping', 'Donald Trump'])
        self.assertEqual(cards['b']['government_photo']['subjects'], ['Xi Jinping'])
        self.assertEqual(next(p for p in shown if not p.get('subjects'))['caption'],
                         'China · Archive image for country context.')
        self.assertIsNone(cards['f']['government_photo'])


if __name__ == '__main__':
    unittest.main()
