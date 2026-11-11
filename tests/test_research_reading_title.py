import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from research_reading import extract_arxiv_html


class ArxivTitleReading(unittest.TestCase):
    def test_exact_version_title_allows_one_adjacent_transposition(self):
        html = ('<article class="ltx_document">'
                '<h1 class="ltx_title_document">TorchCruves: Differentiable Parametric Curves</h1>'
                '<section><div class="ltx_abstract">Abstract. ' + 'The paper describes learnable curves. ' * 40 + '</div></section>'
                '<section><h2>Methods</h2><p>' + 'The experiment measures curve evaluation and training time. ' * 45 + '</p></section>'
                '</article>').encode()
        reading = extract_arxiv_html(html, 'TorchCurves: Differentiable Parametric Curves')
        self.assertEqual(reading['sections'], 2)
        self.assertIn('The experiment measures', reading['text'])
        with self.assertRaisesRegex(ValueError, 'paper_identity_mismatch'):
            extract_arxiv_html(html, 'OtherCurves: Differentiable Parametric Curves')


if __name__ == '__main__':
    unittest.main()
