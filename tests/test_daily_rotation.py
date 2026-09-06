import copy
import json
import sys
import unittest
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from daily_selection import rotation_plan, reading_day
from build_site import cards, culture_items
from culture_library import audit, select, publication, connect, KINDS


class ReadingOrder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        release = json.loads((ROOT / 'data/preview/release.json').read_text())
        relationships = json.loads((ROOT / 'data/preview/symbiosis.json').read_text())
        cls.news = cards(release, relationships, {}, {}, {})

    def test_week_exposes_every_story_without_changing_dates_or_findings(self):
        before = copy.deepcopy(self.news)
        plan = rotation_plan(self.news, '2026-W35', '2026-08-30', '2026-09-06')
        keys = {r['key'] for r in self.news}
        self.assertEqual(len(keys), 110)
        batches = []
        for n, layout in enumerate(plan['layouts']):
            self.assertEqual(set(layout['order']), keys)
            self.assertEqual(len(layout['order']), 110)
            self.assertEqual(len(set([layout['lead'], *layout['highlights']])), 3)
            count = (n + 1) * 110 // 7 - n * 110 // 7
            batches += layout['order'][:count]
        self.assertEqual(len(set(batches)), 110)
        self.assertEqual(len({r['lead'] for r in plan['layouts']}), 7)
        self.assertEqual(self.news, before)

    def test_current_calendar_handles_local_midnight_and_small_editions(self):
        self.assertEqual(reading_day(datetime(2026,9,6,22,1,tzinfo=timezone.utc)),date(2026,9,7))
        self.assertEqual(reading_day(datetime(2026,12,31,23,1,tzinfo=timezone.utc)),date(2027,1,1))
        for count in (0,1,2,5):
            items = self.news[:count]
            plan = rotation_plan(items, 'small', '2026-08-30', '2026-09-07')
            for layout in plan['layouts']:
                self.assertEqual(len(layout['order']),count)
                self.assertEqual(len(layout['highlights']),max(0,min(count-1,2)))
        self.assertEqual(plan['slot'],0)

    def test_source_order_does_not_change_the_published_calendar(self):
        a = rotation_plan(self.news, '2026-W35', '2026-08-30', '2026-09-06')
        b = rotation_plan(list(reversed(self.news)), '2026-W35', '2026-08-30', '2026-09-06')
        self.assertEqual(a,b)
        self.assertEqual(set(m for r in self.news for m in r['markets']), {'CA','CN','FR','GB','US'})


class StoredCulture(unittest.TestCase):
    def test_database_has_400_verified_records_and_images_in_each_category(self):
        result = audit(ROOT)
        self.assertEqual(result['counts'], dict.fromkeys(KINDS,400))
        self.assertEqual(result['total'],2000)
        self.assertEqual(result['cached_images'],400)

    def test_400_day_selection_is_complete_nonrepeating_and_offline(self):
        chosen = {kind:set() for kind in KINDS}
        with patch('socket.create_connection', side_effect=AssertionError('No network permitted')):
            for n in range(400):
                day = date(2026,9,6) + timedelta(days=n)
                rows = select(day, ROOT)
                self.assertEqual(Counter(r['culture_type'] for r in rows), Counter(KINDS))
                for row in rows:
                    self.assertNotIn(row['key'],chosen[row['culture_type']])
                    chosen[row['culture_type']].add(row['key'])
                    self.assertEqual(row['date'],day.isoformat())
                    self.assertEqual(row['selected_on'],day.isoformat())
            self.assertEqual([r['key'] for r in select('2026-09-06',ROOT)],
                             [r['key'] for r in select(date(2026,9,6)+timedelta(days=400),ROOT)])

    def test_build_can_use_todays_selection_without_the_collector_writing_files(self):
        path = ROOT/'data/culture/current.json'
        before = path.read_bytes()
        with patch('socket.create_connection', side_effect=AssertionError('No network permitted')):
            result = publication('2027-01-02', ROOT)
        self.assertEqual(len(result['editions']['2027-01-02']),5)
        self.assertEqual(path.read_bytes(),before)

    def test_quotes_are_contextual_and_origins_are_explicit(self):
        with connect(ROOT) as db:
            rows = [json.loads(p) for p, in db.execute('SELECT payload FROM works')]
        for row in rows:
            self.assertTrue(row['creator_origin'])
            self.assertNotIn('pg:59709:',row['provenance_id']) # Giles commentary is not Zhuangzi.
            if row['culture_type']=='quote':
                self.assertIn(row['excerpt'],row['quote_context'])
            if row.get('translator'):
                self.assertIn(row['translator'],row['rights']['basis'])
        origins=' '.join(r['creator_origin'] for r in rows)
        for place in ('Tibet','Nepal','Iran','Brazil','Japan','Chinese','Hungarian','Greek'):
            self.assertIn(place,origins)

    def test_news_and_culture_counts_are_separate(self):
        rows = culture_items()
        self.assertTrue(rows)
        self.assertTrue(all(r['kind']=='culture' for r in rows))
        self.assertTrue(all(r['creator_origin'] for r in rows))


if __name__ == '__main__':
    unittest.main()
