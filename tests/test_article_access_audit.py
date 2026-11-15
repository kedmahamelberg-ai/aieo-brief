import copy,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from article_access_audit import audit
from editorial_corrections import apply_corrections,is_locked

class ArticleAccessAudit(unittest.TestCase):
 def test_recovered_infographic_renders_a_complete_summary_and_no_failure_notice(self):
  rows=json.loads((ROOT/'data/archive/stories.json').read_text())['stories']
  apply_corrections(rows)
  row=next(x for x in rows if 'f8af0f48' in x['key'])
  self.assertTrue(row['has_editorial']);self.assertTrue(row['evidence_complete'])
  self.assertEqual(len(row['body_paragraphs']),4)
  self.assertEqual(audit(rows)['access_error_notices'],[])
 def test_new_validated_article_supersedes_temporary_access_correction(self):
  key='event:fb5546e6-dab5-417f-a0aa-e0b6ede17dbc'
  self.assertFalse(is_locked(key))
  row={'key':key,'has_editorial':True,'access_recovery_validated':True,'deck':'A later full-source summary.'}
  self.assertEqual(apply_corrections([copy.deepcopy(row)])[0],row)
 def test_contradictory_complete_reading_fails_build(self):
  with self.assertRaisesRegex(ValueError,'unavailable-source notice'):
   audit([{'kind':'news','key':'test','path':'story/test/','deck':'The full article could not be reviewed.','has_editorial':True,'evidence_complete':True}])

 def test_old_editorial_does_not_override_a_current_publisher_access_restriction(self):
  row={'key':'event:fb5546e6-dab5-417f-a0aa-e0b6ede17dbc','has_editorial':True,
       'deck':'An older draft written before the source-quality audit.','body_paragraphs':['An unsafe stale summary.']}
  apply_corrections([row])
  self.assertFalse(row['has_editorial'])
  self.assertEqual(row['body_paragraphs'],[])
  self.assertIn('requires publisher access',row['deck'])
