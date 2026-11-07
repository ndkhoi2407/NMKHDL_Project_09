"""Offline Milestone 3 unit tests. Tests matching features, MRR@5, and candidate scoring."""
from __future__ import annotations

import unittest
from src.milestone3.matching import (
    FEATURE_NAMES,
    candidates,
    heuristic_score,
    jaccard,
    make_features,
    mrr_at_5,
    normalize,
    tokens,
    weak_match,
)


class TestMile3(unittest.TestCase):
    def test_feature_names_length(self):
        self.assertEqual(len(FEATURE_NAMES), 10)

    def test_normalize_and_tokens(self):
        text = r"\textbf{Deep} Residual Learning \emph{for} Image Recognition"
        norm = normalize(text)
        self.assertNotIn("textbf", norm)
        toks = tokens(text)
        self.assertIn("deep", toks)
        self.assertIn("learning", toks)
        self.assertIn("recognition", toks)
        # stop words excluded
        self.assertNotIn("for", toks)

    def test_exact_arxiv_id_match(self):
        entry = {
            "title": "Deep Residual Learning for Image Recognition arXiv:1512.03385",
            "authors": ["He", "Zhang", "Ren", "Sun"],
            "year": 2015,
        }
        ref = {
            "ref_arxiv_id": "1512.03385",
            "ref_title": "Deep Residual Learning for Image Recognition",
            "ref_authors": ["Kaiming He", "Xiangyu Zhang"],
            "ref_submission_date": "2015-12-10",
        }
        feats = make_features(entry, ref)
        self.assertEqual(len(feats), 10)
        self.assertEqual(feats[8], 1.0)  # arxiv_id_exact
        self.assertEqual(heuristic_score(feats), 1.0)

    def test_mrr_at_5_computation(self):
        rows = [
            {"groundtruth_arxiv_id": "1001.0001", "cand_1": "1001.0001"},  # RR = 1.0
            {"groundtruth_arxiv_id": "1001.0002", "cand_2": "1001.0002"},  # RR = 0.5
            {"groundtruth_arxiv_id": "1001.0003", "cand_3": "1001.0003"},  # RR = 0.3333
            {"groundtruth_arxiv_id": "1001.0004", "cand_6": "1001.0004"},  # RR = 0.0 (>5)
            {"groundtruth_arxiv_id": "", "cand_1": "1001.0005"},           # none -> 0.0
        ]
        # total RR = 1.0 + 0.5 + 1/3 + 0 + 0 = 1.8333333333333333 / 5 = 0.36666666666666664
        val = mrr_at_5(rows)
        self.assertAlmostEqual(val, (1.0 + 0.5 + 1.0 / 3.0) / 5.0, places=4)


if __name__ == "__main__":
    unittest.main()
