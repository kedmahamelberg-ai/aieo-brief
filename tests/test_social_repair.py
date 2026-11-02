import copy
import hashlib
import json
import os
from datetime import date
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import prepare_social_review as social
import repair_social_review as repair


class SocialRepair(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.original = self.root / 'original'; self.output = self.root / 'repaired'
        for name in ('assets', 'sources'): (self.original / name).mkdir(parents=True)
        self.rows = []; self.topics = []; self.photos = {}
        for n in range(15):
            ident = f'TOPIC{n}'; kind = 'Research' if n == 14 else 'News'
            market = list(social.COUNTRIES)[n % 5] if kind == 'News' else ''
            row = dict(key=f'key{n}', path=f"{'story' if kind == 'News' else 'research'}/article{n}/index.html",
                       headline='A supported source-backed article', deck='A factual introduction', what_happened='A supported finding.',
                       body_paragraphs=['The source evidence.'], sources=[{'url': f'https://source.example/{n}'}],
                       has_editorial=True, edition='2026-W44', markets=[market])
            self.rows.append(row)
            topic = dict(id=ident, kind=kind, market=market, country=social.COUNTRIES.get(market, ''),
                         date='2026-11-04' if kind == 'Research' else f'2026-11-{2+n//2:02}', time='06:00' if kind == 'Research' else ('10:00' if n % 2 == 0 else '18:00'),
                         path=row['path'], headline=row['headline'], hook=row['deck'], fact=row['what_happened'],
                         evidence='Source checked', source_urls=[row['sources'][0]['url']], source_limitation='One source.',
                         tags=['#TheBrief', '#ResponsibleAI', social.GEO.get(market, '#AIResearch')],
                         second_subject_tag='#AIGovernance', substack_lead='Read the evidence.',
                         source_key=row['key'], article_content_sha256=social.geography_fingerprint(row))
            if kind == 'News':
                topic['photo'] = ident; data = f'original photo {n}'.encode()
                relative = f'sources/{ident}.jpg'; (self.original / relative).write_bytes(data)
                self.photos[ident] = dict(local_source=relative, sha256=hashlib.sha256(data).hexdigest(),
                     source_url=f'https://photos.example/{n}', title='Country landscape', creator='Creator', rights_status='Public domain')
            self.topics.append(topic)
            for medium in ('carousel', 'story'):
                for card in (1,2,3): (self.original / f'assets/{ident}_{medium}_{card}.png').write_bytes(b'original prepared media')
        batch = social.build(self.topics, self.photos, self.original, '2026-W44', date(2026,10,26), date(2026,11,1), date(2026,11,2))
        repair.save(self.original / 'batch.json', batch); repair.save(self.original / 'PHOTO_MANIFEST.json', self.photos)
        self.plan = dict(revision=2, publication_week='2026-W45', source_edition='2026-W44',
                         baseline_batch_sha256=hashlib.sha256((self.original/'batch.json').read_bytes()).hexdigest(),
                         topic_updates=[dict(previous_topic_id=t['id'], topic=t, replacement=False) for t in self.topics])
        self.receipt = dict(publication_week='2026-W45', status=social.STATUS, run_id='123',
             artifact_url='https://github.com/kedmahamelberg-ai/aieo-brief/actions/runs/123/artifacts/456')

    def test_offline_preview_preserves_unchanged_media_but_cannot_claim_live_readiness(self):
        with patch.object(social, 'verified_markets', return_value=list(social.COUNTRIES)), \
             patch.object(social, 'render') as render, patch.object(repair, 'review_html', return_value='review'):
            batch = repair.produce(self.original, self.output, self.plan, items=self.rows, verify_destinations=False)
        self.assertEqual(len(batch['items']), 60)
        self.assertEqual(render.call_args.args[0], [])
        self.assertEqual((self.output/'assets/TOPIC0_carousel_1.png').read_bytes(), b'original prepared media')
        self.assertFalse((self.output/'READY_FOR_REVIEW.json').exists())

    def test_different_input_stale_article_and_headline_only_destinations_are_rejected(self):
        bad = {**self.plan, 'baseline_batch_sha256': '0' * 64}
        with self.assertRaisesRegex(ValueError, 'exact audited'):
            repair.produce(self.original, self.output, bad, items=self.rows)
        rows = copy.deepcopy(self.rows); rows[0]['what_happened'] = 'A changed claim.'
        with self.assertRaisesRegex(ValueError, 'live article'):
            repair.produce(self.original, self.output, self.plan, items=rows)
        rows = copy.deepcopy(self.rows); rows[0]['has_editorial'] = False
        with self.assertRaisesRegex(ValueError, 'headline-only'):
            repair.produce(self.original, self.output, self.plan, items=rows)

    def test_country_check_and_photo_hash_cannot_be_bypassed(self):
        with patch.object(social, 'verified_markets', return_value=[]), self.assertRaisesRegex(ValueError, 'country'):
            repair.produce(self.original, self.output, self.plan, items=self.rows)
        (self.original/'sources/TOPIC0.jpg').write_bytes(b'different photo')
        with patch.object(social, 'verified_markets', return_value=list(social.COUNTRIES)), self.assertRaisesRegex(ValueError, 'photograph bytes changed'):
            repair.produce(self.original, self.output, self.plan, items=self.rows)

    def test_repair_receipt_preserves_original_approval_and_requires_new_review(self):
        state_path = self.root/'data/social-production/state.json'
        repair.save(state_path, {'editions': {'2026-W44': self.receipt}})
        approval_path = self.root/'data/social-production/approved/2026-W45.json'
        approval = dict(status='APPROVED', batch_sha256=self.plan['baseline_batch_sha256'])
        repair.save(approval_path, approval)
        self.output.mkdir(); (self.output/'batch.json').write_text('corrected batch')
        repair.save(self.output/'READY_FOR_REVIEW.json', dict(source_audit_complete=True, live_corrected_destinations_checked=True))
        env = dict(SOCIAL_ARTIFACT_URL='https://github.com/kedmahamelberg-ai/aieo-brief/actions/runs/789/artifacts/999', GITHUB_RUN_ID='789')
        with patch.object(repair, 'ROOT', self.root), patch.dict(os.environ, env):
            repair.record(self.output, self.plan)
        self.assertEqual(repair.read(approval_path)['status'], 'SUPERSEDED_PENDING_CORRECTED_REVIEW')
        history = self.root/'data/social-production/approval-history/2026-W45'/(approval['batch_sha256']+'.json')
        self.assertEqual(repair.read(history), approval)
        self.assertFalse(repair.needed(self.plan, repair.read(state_path))[0])
        self.assertEqual(repair.read(state_path)['review_history']['2026-W44'][0], self.receipt)

    def test_replacement_photo_requires_fresh_identity_and_exact_bytes(self):
        path = self.root/'config/social-repair-2026-W45/photos/new.jpg'
        path.parent.mkdir(parents=True); path.write_bytes(b'fresh image')
        photo = {**self.photos['TOPIC0'], 'repository_source': 'config/social-repair-2026-W45/photos/new.jpg',
                 'rights_status': 'CC0', 'sha256': hashlib.sha256(b'fresh image').hexdigest()}
        plan = {**self.plan, 'photo_replacements': {'TOPIC0': photo}}
        repair.save(self.root/'config/social-photo-history.json', {'source_urls': [photo['source_url']], 'sha256': []})
        with patch.object(repair, 'ROOT', self.root), patch.object(social, 'verified_markets', return_value=list(social.COUNTRIES)):
            with self.assertRaisesRegex(ValueError, 'already used'):
                repair.produce(self.original, self.output, plan, items=self.rows)
            photo['sha256'] = '0'*64
            with self.assertRaisesRegex(ValueError, 'Replacement photograph bytes'):
                repair.produce(self.original, self.output, plan, items=self.rows)


if __name__ == '__main__': unittest.main()
