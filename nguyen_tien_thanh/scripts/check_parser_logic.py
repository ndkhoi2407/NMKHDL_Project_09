"""Small in-memory checks of existing parser functions. Never processes the corpus."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('arxiv_parser', ROOT / 'src/parse.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

def entry(key, **fields):
    return dict(citation_key=key, entry_type='misc', **fields)

class ParserLogic(unittest.TestCase):
    def test_doi_union_and_newest_nonempty_field(self):
        rows, maps = p.dedup_bib({1: {'old': entry('old', doi='10/x', title='Original', authors=['A'], year='2020')},
                                2: {'new': entry('new', doi='10/x', title='Revised', authors=[], url='https://example.org')}})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['citation_key'], 'new')
        self.assertEqual(rows[0]['title'], 'Revised')
        self.assertEqual(rows[0]['authors'], ['A'])
        self.assertEqual(rows[0]['year'], '2020')
        self.assertEqual(maps[1]['old'], 'new')

    def test_cite_options_and_multikey_remapping(self):
        self.assertEqual(p.rename_cites(r'\citep[see][p.2]{old,other}', {'old': 'new'}),
                         r'\citep[see][p.2]{new,other}')

    def test_frequency_over_newest_key(self):
        rows, maps = p.dedup_bib({v: {key: entry(key, doi='10/x')} for v, key in [(1, 'a'), (2, 'a'), (3, 'b')]})
        self.assertEqual(rows[0]['citation_key'], 'a')
        self.assertEqual(maps[3]['b'], 'a')

    def test_normalized_title_and_key_collision(self):
        rows, maps = p.dedup_bib({1: {'same': entry('same', title='A long original title')},
                                2: {'same': entry('same', title='A different long title')},
                                3: {'other': entry('other', title='A LONG ORIGINAL TITLE!')}})
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(maps[1]['same'], maps[2]['same'])
        self.assertEqual(maps[1]['same'], maps[3]['other'])

    def test_non_misc_type_survives_newer_misc(self):
        old = entry('a', doi='10/x')
        old['entry_type'] = 'article'
        rows, _ = p.dedup_bib({1: {'a': old}, 2: {'b': entry('b', doi='10/x')}})
        self.assertEqual(rows[0]['entry_type'], 'article')

    def test_exact_text_occurrence_and_kind_identity(self):
        trees = {}
        for version in [1, 2]:
            root = p.Node('document')
            root.children = [p.Node('sentence', 'Same.'), p.Node('sentence', 'Same.'),
                             p.Node('heading', 'Same.'), p.Node('sentence', 'Different.' if version == 1 else 'Different!')]
            trees[version] = root
        elements, edges, before = p.assign_ids('test', 'test', trees)
        self.assertEqual(before, 10)
        self.assertEqual(len(elements), 7)  # two roots, two repeated sentences, heading, two distinct texts
        ids = {v: [e['element_id'] for e in edges if e['version'] == v] for v in trees}
        self.assertEqual(ids[1][:3], ids[2][:3])
        self.assertEqual(len(set(ids[1])), 4)
        self.assertNotEqual(ids[1][3], ids[2][3])

    def test_remap_precedes_content_identity(self):
        roots = {v: p.Node('document') for v in [1, 2]}
        for v, key in [(1, 'old'), (2, 'new')]:
            roots[v].children = [p.Node('sentence', p.rename_cites(r'Text \cite{' + key + '}.', {'old': 'new'}))]
        elements, edges, _ = p.assign_ids('test', 'test', roots)
        self.assertEqual(edges[0]['element_id'], edges[1]['element_id'])

    def test_cr_only_comments_keep_document_root(self):
        raw = '% comment\r' + r'\documentclass{article}' + '\r' + r'\begin{document}Text.\end{document}'
        self.assertIn(r'\documentclass', p.strip_comments(raw))
        clean = p.strip_comments(raw.replace('\r', '\n'))
        self.assertEqual(p.pick_root({'main.tex': clean}, {'main.tex': Path('main.tex')}), 'main.tex')

if __name__ == '__main__':
    unittest.main(verbosity=2)
