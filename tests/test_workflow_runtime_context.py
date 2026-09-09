"""Regression guard for the exact invalid job-level runner context failure."""
import re
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class RuntimeContext(unittest.TestCase):
 def test_no_runner_expression_in_job_level_environment(self):
  for file in (ROOT/'.github/workflows').glob('*.yml'):
   block=False
   for number,line in enumerate(file.read_text().splitlines(),1):
    if re.match(r'^    env:\s*$',line):block=True;continue
    if block and line.strip() and not line.startswith('      '):block=False
    if block:self.assertNotRegex(line,r'\$\{\{[^}]*\brunner\.',f'{file.name}:{number} uses runner before the job exists')
 def test_new_files_are_present(self):
  for path in ['assets/engagement.js','assets/digest.js','scripts/brief_digest_notifications.py','templates/digest.html','supabase/migrations/202609090004_brief_daily_preferences_and_metrics.sql']:
   self.assertTrue((ROOT/path).is_file(),path)

 def test_follow_editions_calls_the_repaired_editorial_workflow(self):
  caller=(ROOT/'.github/workflows/follow-observatory.yml').read_text()
  callee=(ROOT/'.github/workflows/generate-brief-editorial.yml').read_text()
  self.assertIn('uses: ./.github/workflows/generate-brief-editorial.yml',caller)
  self.assertIn('workflow_call:',callee)
  self.assertIn('news_only:',callee)
  self.assertIn('echo "AIEO_AI_LEDGER=$RUNNER_TEMP/ai-usage/${GITHUB_JOB}.json" >> "$GITHUB_ENV"',callee)
