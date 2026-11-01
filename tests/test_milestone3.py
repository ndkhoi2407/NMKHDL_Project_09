import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.milestone3.matching import normalize, make_features, weak_match, mrr_at_5
from src.milestone3.cli import split_groups, validate_manual
from src.milestone3.export import validate_row, TABLES, export
from src.milestone3.publish import validate_bundle


class TestMilestone3(unittest.TestCase):
    def setUp(self):
        self.e={'arxiv_id':'2607.13694','citation_key':'cite1','title':'A study of graph neural networks for chemistry 2023',
                'authors':['Jane Smith'],'year':2023,'url':''}
        self.r={'arxiv_id':'2607.13694','ref_arxiv_id':'2301.12345',
                'ref_title':'Graph neural networks for chemistry','ref_authors':['Jane Smith'],
                'ref_submission_date':'2023-01-01','ref_s2_id':'x'}

    def test_normalize_latex(self):
        self.assertEqual(normalize(r'\emph{Hello} WORLD!'), 'hello world')

    def test_features(self):
        f=make_features(self.e,self.r)
        self.assertEqual(len(f),10)
        self.assertGreater(f[1],.7)
        self.assertEqual(f[6],1.0)

    def test_weak_exact_arxiv(self):
        e=dict(self.e, title='ref: arXiv:2301.12345')
        matched, score, tops=weak_match(e,[self.r])
        self.assertEqual(matched,'2301.12345')
        self.assertEqual(tops,['2301.12345'])

    def test_same_paper_only_validation(self):
        manual=[{'arxiv_id':'2607.13694','citation_key':'cite1','label_status':'matched',
                 'groundtruth_arxiv_id':'another-paper-id'}]
        with self.assertRaises(ValueError):
            validate_manual(manual,{'2607.13694':[self.e]}, {'2607.13694':[self.r]},1)

    def test_missing_manual_cannot_pass(self):
        with self.assertRaises(ValueError):
            validate_manual([],{}, {},1)

    def test_mrr5(self):
        a={'groundtruth_arxiv_id':'a', **{f'cand_{i}':None for i in range(1,6)}}
        b={'groundtruth_arxiv_id':'b',**{f'cand_{i}':None for i in range(1,6)}}
        b['cand_2']='b'
        c={'groundtruth_arxiv_id':None,**{f'cand_{i}':None for i in range(1,6)}}
        self.assertAlmostEqual(mrr_at_5([a,b,c]), .5/3)

    def test_publication_split_no_overlap(self):
        manual=[str(i) for i in range(10)]
        auto=[f'a{i}' for i in range(10)]
        mapping=split_groups(manual,auto,2,42)
        self.assertEqual(sum(mapping[p]=='test' for p in manual),2)
        self.assertEqual(sum(mapping[p]=='valid' for p in auto),2)
        self.assertEqual(len(mapping),20)

    def test_schema(self):
        bib={k:('' if k not in ['arxiv_id','citation_key','entry_type'] else 'x') for k in TABLES['bibtex'][1]}
        bib.update({'authors':[],'year':None})
        self.assertEqual(validate_row('bibtex',bib)['authors'],[])
        bib['authors']={'bad':True}
        with self.assertRaises(ValueError):validate_row('bibtex',bib)

    def test_predictions_split(self):
        p={k:None for k in TABLES['predictions'][1]}
        p.update(arxiv_id='2607.13694', citation_key='x', partition='bad')
        with self.assertRaises(ValueError):validate_row('predictions',p)

    def test_individual_export_requires_both_range_endpoints(self):
        with TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, 'both --min-id and --max-id'):
                export(Path(temp), Path(temp) / 'dataset', minimum='2607.13694')

    def test_publication_requires_explicit_individual_range(self):
        with TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, 'Both endpoints'):
                validate_bundle(Path(temp), '', '')


if __name__ == '__main__': unittest.main()
