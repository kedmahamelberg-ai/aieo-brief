import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from research_affiliations import clean_institutions


class AffiliationNotes(unittest.TestCase):
    def test_equal_contribution_is_not_an_institution(self):
        values = ['Carnegie Mellon University', '*Equal contribution', '∗Equal contribution',
                  'Carnegie Mellon University, *Equal contribution',
                  'Carnegie Mellon University ∗Equal contribution']
        self.assertEqual(clean_institutions(values), ['Carnegie Mellon University'])


if __name__ == '__main__':
    unittest.main()
