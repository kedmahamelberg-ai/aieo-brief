import sys
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from research_affiliations import clean_institutions, _arxiv_institutions


class AffiliationNotes(unittest.TestCase):
    def test_postal_address_is_not_an_institution(self):
        self.assertEqual(clean_institutions([
            'Learning & Generation Lab, The Hong Kong Polytechnic University',
            'Hung Hom, Kowloon, Hong Kong']),
            ['Learning & Generation Lab, The Hong Kong Polytechnic University'])

    def test_numbered_company_affiliations_are_preserved(self):
        markup = ('<div class="ltx_authors">Author Name'
                  '<span class="ltx_role_affiliation"><sup>1</sup>NAVER Cloud,'
                  '<sup>2</sup>Korea Advanced Institute of Science and Technology</span></div>')
        with patch('research_affiliations.requests.get') as get:
            get.return_value.text = markup
            names, _ = _arxiv_institutions({'arxiv_id':'2611.31237v1', 'authors':['Author Name']})
        self.assertEqual(names, ['NAVER Cloud', 'Korea Advanced Institute of Science and Technology'])

    def test_unmarked_numbered_author_block_keeps_company(self):
        markup = '<div class="ltx_authors"><span>Author Name</span><sup>1</sup><br><sup>1</sup><span>Canva</span></div>'
        with patch('research_affiliations.requests.get') as get:
            get.return_value.text = markup
            names, _ = _arxiv_institutions({'arxiv_id':'2611.33151v1', 'authors':['Author Name']})
        self.assertEqual(names, ['Canva'])
    def test_arxiv_location_and_department_cells_are_not_institutions(self):
        self.assertEqual(clean_institutions(['Department of Mathematics',
                                             'Technical University of Munich', 'Garching, Germany',
                                             'Munich Re', 'San Francisco, USA']),
                         ['Technical University of Munich', 'Munich Re'])
        self.assertEqual(clean_institutions([
            'Department of Industrial and Systems Engineering, University of Minnesota, USA (']),
            ['University of Minnesota'])
    def test_equal_contribution_is_not_an_institution(self):
        values = ['Carnegie Mellon University', '*Equal contribution', '∗Equal contribution',
                  'Carnegie Mellon University, *Equal contribution',
                  'Carnegie Mellon University ∗Equal contribution']
        self.assertEqual(clean_institutions(values), ['Carnegie Mellon University'])


if __name__ == '__main__':
    unittest.main()
