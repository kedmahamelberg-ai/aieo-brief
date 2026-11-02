import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import editorial_corrections as corrections
import prepare_social_review as social


class SourceAuditCorrections(unittest.TestCase):
    def test_registered_audit_repairs_content_without_changing_other_articles(self):
        audit = json.loads((ROOT/corrections.SOURCE_AUDITS[0]).read_text())
        rows = [{'key': row['key'], **copy.deepcopy(row['before'])} for row in audit['news']+audit['research']]
        unrelated = {'key': 'unrelated', 'headline': 'Keep original'}
        rows.append(unrelated)
        corrections.apply_corrections(rows)
        for actual, expected in zip(rows, audit['news']+audit['research']):
            for field, value in expected['after'].items():
                self.assertEqual(actual[field], value)
        self.assertEqual(rows[-1], unrelated)

    def test_country_proof_becomes_invalid_when_article_changes(self):
        row = dict(key='tested', headline='NHS Highland', sources=[{'url':'https://source.example'}])
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root/'config').mkdir()
            (root/'config/social-geography.json').write_text(json.dumps({'articles': {'tested': {'markets':['GB'], 'content_sha256':social.geography_fingerprint(row)}}}))
            with patch.object(social, 'ROOT', root):
                self.assertEqual(social.verified_markets(row), ['GB'])
                row['headline'] = 'A changed story'
                with self.assertRaisesRegex(ValueError, 'stale'):
                    social.verified_markets(row)
