import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/publish_generated_data.py'
spec = importlib.util.spec_from_file_location('publisher', SCRIPT)
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)


def git(cwd, *args):
    return subprocess.run(('git', *args), cwd=cwd, check=True, text=True,
                          capture_output=True).stdout.strip()


class PublishGeneratedDataTests(unittest.TestCase):
    def test_research_summary_and_concurrent_affiliation_both_survive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote = root / 'remote.git'
            git(root, 'init', '--bare', str(remote))
            seed, runner, concurrent, verify = (root / name for name in ('seed', 'runner', 'concurrent', 'verify'))
            git(root, 'clone', str(remote), str(seed))
            git(seed, 'checkout', '-b', 'main')
            git(seed, 'config', 'user.name', 'Tester')
            git(seed, 'config', 'user.email', 'tester@example.test')
            public = seed / 'data/research/public.json'
            public.parent.mkdir(parents=True)
            base = {'schema_version': 'v1', 'generated_at': 'base', 'papers': [
                {'key': 'paper:flide', 'date': '2026-10-30', 'metadata_sha256': 'same',
                 'institutions': ['Bad author block'], 'has_editorial': False}]}
            public.write_text(json.dumps(base) + '\n')
            git(seed, 'add', '.')
            git(seed, 'commit', '-m', 'Seed')
            git(seed, 'push', 'origin', 'HEAD:main')
            git(remote, 'symbolic-ref', 'HEAD', 'refs/heads/main')
            git(root, 'clone', str(remote), str(runner))
            git(root, 'clone', str(remote), str(concurrent))
            git(concurrent, 'config', 'user.name', 'Tester')
            git(concurrent, 'config', 'user.email', 'tester@example.test')
            changed = json.loads((concurrent / 'data/research/public.json').read_text())
            changed['papers'][0]['institutions'] = ['National University of Singapore', 'University of Oxford']
            changed['papers'].append({'key': 'paper:other', 'date': '2026-10-29',
                                      'metadata_sha256': 'other', 'has_editorial': True})
            (concurrent / 'data/research/public.json').write_text(json.dumps(changed) + '\n')
            git(concurrent, 'add', '.')
            git(concurrent, 'commit', '-m', 'Correct affiliations')
            git(concurrent, 'push', 'origin', 'HEAD:main')
            generated = json.loads((runner / 'data/research/public.json').read_text())
            generated['papers'][0].update(has_editorial=True, headline='Checked Flide',
                                          summary_status='ready', editorial_engine_version='runtime-v10')
            (runner / 'data/research/public.json').write_text(json.dumps(generated) + '\n')
            subprocess.run((sys.executable, str(SCRIPT)), cwd=runner, check=True,
                           text=True, capture_output=True)
            git(root, 'clone', str(remote), str(verify))
            result = json.loads((verify / 'data/research/public.json').read_text())
            flide = next(p for p in result['papers'] if p['key'] == 'paper:flide')
            self.assertEqual(flide['headline'], 'Checked Flide')
            self.assertEqual(flide['institutions'], ['National University of Singapore', 'University of Oxford'])
            self.assertEqual(len(result['papers']), 2)

    def test_superseded_source_does_not_take_stale_summary(self):
        base = {'papers': [{'key': 'paper:a', 'date': '2026-10-30',
                            'metadata_sha256': 'old', 'has_editorial': False}]}
        local = {'papers': [dict(base['papers'][0], has_editorial=True, headline='Stale')]}
        remote = {'papers': [dict(base['papers'][0], metadata_sha256='new')]}
        result = publisher.reconcile('data/research/public.json', base, local, remote)
        self.assertFalse(result['papers'][0].get('has_editorial'))
        self.assertNotIn('headline', result['papers'][0])


if __name__ == '__main__':
    unittest.main()
