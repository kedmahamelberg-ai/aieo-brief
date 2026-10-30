"""The live grounding smoke test must tolerate one false rejection, not false acceptance."""
import sys
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import evaluate_grounding
from editorial_engine import EditorialError


class LiveEvaluationControlTests(unittest.TestCase):
    def test_one_false_rejection_of_supported_fixture_is_rechecked(self):
        correct = {row[3] for row in evaluate_grounding.CASES}
        attempts = Counter()

        def review(draft, sources, deadline):
            name = draft['editorial_headline']
            full_draft = bool(draft['body_paragraphs'])
            positive = name in correct or (full_draft and 'caused job losses' not in draft['body_paragraphs'][1])
            attempts[name] += 1
            if not positive or attempts[name] == 1:
                raise EditorialError('claim_grounding_failed', 'Synthetic rejection')

        evaluate_grounding.evaluate(review)
        for _, _, wrong, right in evaluate_grounding.CASES:
            self.assertEqual(attempts[wrong], 1)
            self.assertEqual(attempts[right], 2)
        self.assertEqual(attempts['Company trial finds workers finish support tickets faster with AI'], 3)

    def test_false_acceptance_of_wrong_fixture_still_fails(self):
        with self.assertRaisesRegex(RuntimeError, 'provenance:wrong'):
            evaluate_grounding.evaluate(lambda draft, sources, deadline: None)

    def test_persistent_false_rejection_still_fails(self):
        def review(draft, sources, deadline):
            raise EditorialError('claim_grounding_failed', 'Synthetic rejection')

        with self.assertRaisesRegex(RuntimeError, 'provenance:correct'):
            evaluate_grounding.evaluate(review)


if __name__ == '__main__':
    unittest.main()
