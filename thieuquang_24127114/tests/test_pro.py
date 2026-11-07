"""Regression tests for stronger recovery and offline verification; no network."""
from __future__ import annotations
from pathlib import Path
import sys
import tempfile
import unittest
from typing import cast

repository_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repository_root / "src"))
sys.path.insert(0, str(repository_root))

from src import audit, crawler, status

class TestPro(unittest.TestCase):
    def test_rejects_html_pdf_and_binary_as_tex(self):
        for body in [b'<!doctype html><html>429</html>', b'<html>error</html>',
                     b'%PDF-1.7\n', b'\x00garbage', b'<?xml version="1.0"?>']:
            self.assertFalse(crawler.looks_like_text(body))
        self.assertTrue(crawler.looks_like_text(b'% a comment\n\\documentclass{article}\n'))

    def test_semantic_scholar_429_stops_phase(self):
        class FakeClient:
            def get(self, *args, **kwargs):
                raise crawler.HTTPError(429, 'https://api.semanticscholar.org/graph/v1/')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(crawler.RateLimitStop):
                crawler.fetch_s2_references(
                    cast(crawler.PacedClient, FakeClient()), root, '2607.13694'
                )
            self.assertTrue((crawler.paper_dir(root, '2607.13694') / 'references_error.json').exists())

    def test_source_429_checkpoint_and_stop(self):
        class FakeClient:
            def get(self, *args, **kwargs):
                raise crawler.HTTPError(429, 'https://export.arxiv.org/src/example')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(crawler.RateLimitStop):
                crawler.download_source(
                    cast(crawler.PacedClient, FakeClient()), root,
                    '2607.13694v1', 1024
                )
            self.assertEqual(crawler.read_json(crawler.paper_dir(root, '2607.13694') /
                                              'v1' / 'source_status.json')['status'], 'error')

    def test_monitor_and_audit_dont_modify_collected_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = crawler.paper_dir(root, '2607.13694')
            crawler.write_json(folder / 'paper.json', {'status': 'found', 'latest_version': 2})
            crawler.write_json(folder / 'v1' / 'source_status.json', {
                'status': 'no_latex', 'tex_bib_files': 0})
            crawler.write_json(folder / 'v2' / 'source_status.json', {
                'status': 'ok', 'tex_bib_files': 1})
            (folder / 'v2' / 'source').mkdir(parents=True)
            (folder / 'v2' / 'source' / 'article.tex').write_text('\\documentclass{article}')
            crawler.write_json(folder / 'references_all.json', {'status': 'ok', 'references': []})
            ids = ['2607.13694', '2607.13695']
            x = status.snapshot(root, ids)
            self.assertEqual(x['discovered'], 1)
            self.assertEqual(x['pending_discovery'], 1)
            self.assertEqual(x['source_checked'], 2)
            self.assertEqual(x['source_with_latex'], 1)
            y = audit.audit(root, ids)
            self.assertEqual(y['issue_count'], 1)  # discovery pending; exact metadata is a separate coverage metric
            self.assertFalse((root / 'summary.json').exists())

    def test_oai_reference_date_is_first_revision_not_last(self):
        class FakeResponse:
            def __init__(self, data): self.content = data
            def close(self): pass
        class FakeClient:
            def get(self, domain, url, *, params=None, stream=False):
                assert domain == 'oai'
                assert params is not None
                ident = params['identifier'].rsplit(':', 1)[-1]
                return FakeResponse(('''<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
                    <GetRecord><record><metadata><arXivRaw xmlns="http://arxiv.org/OAI/arXivRaw/">
                    <id>'''+ident+'''</id><title>Test</title>
                    <version version="v1"><date>Mon, 20 Jul 2026 10:00:00 GMT</date></version>
                    <version version="v2"><date>Tue, 21 Jul 2026 10:00:00 GMT</date></version>
                    </arXivRaw></metadata></record></GetRecord></OAI-PMH>''').encode())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            crawler.write_json(crawler.paper_dir(root, '2607.13694') / 'references_all.json',
                               {'status': 'ok', 'references': [{'ref_arxiv_id': '2607.13696'}]})
            crawler.enrich_reference_dates(
                cast(crawler.PacedClient, FakeClient()), root, ['2607.13694'],
                batch_size=30, backend='oai'
            )
            conn = crawler.open_ref_cache(root)
            try:
                value = conn.execute('SELECT submission_date FROM dates WHERE arxiv_id=?',
                                     ('2607.13696',)).fetchone()[0]
                self.assertEqual(value, '2026-07-20T10:00:00+00:00')
            finally:
                conn.close()


if __name__ == '__main__':
    unittest.main()
