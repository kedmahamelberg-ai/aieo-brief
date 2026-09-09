import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import ai_runtime as ai
import editorial_engine as engine


class OpenAIEditorial(unittest.TestCase):
    def setUp(self):
        env=patch.dict(os.environ, {'AIEO_AI_PROVIDER':'openai','AIEO_AI_MODEL':'gpt-5-nano'})
        env.start(); self.addCleanup(env.stop)
        ai.selected_policy.cache_clear(); self.addCleanup(ai.selected_policy.cache_clear)

    def test_whole_article_reaches_writer_without_lossy_intermediate_notes(self):
        body=('A full source paragraph in Chinese 中文 and French français. ' * 200)+'The concluding limitation must stay.'
        with patch.object(engine, 'call_json') as model:
            compiled, trace=engine.compile_evidence([{'source_number':1,'evidence':body}])
        model.assert_not_called()
        self.assertIn(body, str(compiled))
        self.assertFalse(trace)

    def test_api_errors_and_schema_are_not_replaced_with_local_generation(self):
        with patch.object(ai, 'completion', side_effect=ai.AIError('API unavailable')) as request:
            with self.assertRaises(ai.AIError):engine.call_json('Article to read')
        self.assertEqual(request.call_count, 1)
        self.assertEqual(request.call_args.args[1], engine.SCHEMA)
