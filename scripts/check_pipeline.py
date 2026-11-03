"""Isolated pipeline regression checks; no network or original corpus writes."""
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import download_sources as download
import metadata
with patch.dict(os.environ, {'S2_API_KEY': '', 'ARXIV_CRAWLER_CONTACT': ''}):
    import references
import importlib.util
spec = importlib.util.spec_from_file_location('arxiv_parser', ROOT/'src/parse.py')
parser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parser)

TEX = b'\\documentclass{article}\n\\begin{document}\nText.\n\\begin{figure}\\includegraphics{x}\\caption{Keep me}\\end{figure}\n\\end{document}\n'

class PipelineChecks(unittest.TestCase):
    def test_tar_source_filter_and_byte_preservation(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.cache') as temp:
            root = Path(temp)
            archive = root/'input.tar.gz'
            files = {'nested/main.tex': TEX, 'refs.bib': b'@misc{x}', 'x.png': b'png',
                     'a.sty': b'sty', '../../escape.tex': b'escape'}
            with tarfile.open(archive, 'w:gz') as tar:
                for name, content in files.items():
                    info = tarfile.TarInfo(name); info.size = len(content)
                    tar.addfile(info, io.BytesIO(content))
                link = tarfile.TarInfo('linked.tex'); link.type = tarfile.SYMTYPE; link.linkname = '../../escape'
                tar.addfile(link)
            out = root/'out'; out.mkdir()
            self.assertEqual(download.extract_archive(archive, out), 'tar')
            self.assertEqual({p.relative_to(out).as_posix() for p in out.rglob('*') if p.is_file()}, {'nested/main.tex', 'refs.bib'})
            self.assertEqual((out/'nested/main.tex').read_bytes(), TEX)

    def test_zip_source_filter_and_byte_preservation(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.cache') as temp:
            root = Path(temp); archive = root/'input.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                for name, content in {'main.tex': TEX, 'nested/refs.bib': b'bib', 'a.pdf': b'%PDF', '../escape.tex': b'bad'}.items():
                    z.writestr(name, content)
            out = root/'out'; out.mkdir()
            self.assertEqual(download.extract_archive(archive, out), 'zip')
            self.assertEqual({p.relative_to(out).as_posix() for p in out.rglob('*') if p.is_file()}, {'main.tex', 'nested/refs.bib'})
            self.assertEqual((out/'main.tex').read_bytes(), TEX)

    def test_duplicate_same_key_across_bib_files_and_bibitem(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.cache') as temp:
            root = Path(temp)
            (root/'main.tex').write_text(r'''\documentclass{article}
\begin{document}
Example text \cite{shared}.
\bibliography{first,second}
\begin{thebibliography}{1}
\bibitem{shared} A. Author. "Shared reference title". 2020. https://example.org/extra
\end{thebibliography}
\end{document}''')
            (root/'first.bib').write_text('@article{shared,\n title={Shared reference title},\n author={A Author},\n year={2020}\n}\n')
            (root/'second.bib').write_text('@article{shared,\n doi={10.1234/example},\n url={https://example.org/saved}\n}\n')
            result = parser.parse_version(root)
            self.assertEqual(result['status'], 'ok')
            entry = result['bib']['shared']
            self.assertEqual(entry['year'], 2020)
            self.assertEqual(entry['doi'], '10.1234/example')
            self.assertTrue(entry['authors'])
            self.assertTrue(entry['url'])

    def test_conflicts_and_nonempty_union(self):
        entries, conflicts = {}, []
        parser.merge_bib_entry(entries, {'citation_key':'x', 'title':'Earlier', 'year':2020, 'authors':['A'], 'entry_type':'article'}, conflicts)
        parser.merge_bib_entry(entries, {'citation_key':'x', 'title':'Later', 'year':None, 'authors':[], 'doi':'10/x', 'entry_type':'misc'}, conflicts)
        self.assertEqual(entries['x']['year'], 2020)
        self.assertEqual(entries['x']['authors'], ['A'])
        self.assertEqual(entries['x']['entry_type'], 'article')
        self.assertEqual(entries['x']['title'], 'Later')
        self.assertTrue(any(c['earlier']=='Earlier' and c['later']=='Later' for c in conflicts))

    def test_oai_venue_and_explicit_date_provenance(self):
        xml = ET.fromstring('<root xmlns:a="http://arxiv.org/OAI/arXivRaw/">'
                            '<a:version version="v1"><a:date>Wed, 01 Jul 2026 00:00:00 GMT</a:date></a:version>'
                            '<a:journal-ref>Example Journal 1 (2026)</a:journal-ref></root>')
        result, warning = metadata.build_metadata_oai({'title':'Title', 'authors':['A'], 'latest_version':1}, xml)
        self.assertEqual(result['venue'], 'Example Journal 1 (2026)')
        self.assertEqual(result['versions']['v1']['date'], '2026-07-01')
        self.assertIn('not historical', result['provenance']['title_authors_scope'])

    def test_driver_enables_versioned_metadata(self):
        import main
        from types import SimpleNamespace
        args = SimpleNamespace(limit=None)
        self.assertIn('--versioned', main.build_command('metadata', 'metadata.py', args))

    def test_actual_version_metadata_requires_matching_identifier(self):
        from types import SimpleNamespace
        from datetime import datetime, timezone
        record = SimpleNamespace(title='Earlier title', authors=[SimpleNamespace(name='A')],
                                  published=datetime(2026,7,1,tzinfo=timezone.utc), updated=datetime(2026,7,2,tzinfo=timezone.utc),
                                  journal_ref='Journal', get_short_id=lambda: '2607.00001v1')
        client = SimpleNamespace(results=lambda search: iter([record]))
        result = metadata.version_metadata(client, {'id':'2607.00001','versions':['v1']})
        self.assertEqual(result['v1']['title'], 'Earlier title')
        with self.assertRaises(ValueError):
            metadata.version_metadata(client, {'id':'2607.00002','versions':['v1']})

    def test_non_arxiv_and_unidentifiable_raw_references_preserved(self):
        paper = {'id':'2607.00001', 'folder':'2607-00001', 'versions':['v1','v2']}
        response = {'references':[{'paperId':'s2-one','title':'Non arxiv', 'externalIds':{}},
                                  None,
                                  {'paperId':None,'title':None,'externalIds':{}},
                                  {'paperId':'s2-two','title':'Arxiv', 'externalIds':{'ArXiv':'2601.00001'}}]}
        with tempfile.TemporaryDirectory(dir=ROOT/'.cache') as temp, patch.object(references,'DATA_DIR',Path(temp)), patch.object(references,'fetch_s2_many',return_value={paper['id']:(response,'')}):
            fetched, errors = references.s2_phase([paper], {}, False)
            out = Path(temp)/paper['folder']
            self.assertEqual(json.loads((out/'references_raw.json').read_text()), response)
            provenance = json.loads((out/'references_provenance.json').read_text())
            self.assertFalse(provenance['version_specific'])
            result, _, _ = references.build_references(fetched[paper['id']][2], {})
            self.assertIn('s2-s2-one', result)
            self.assertIsNone(result['s2-s2-one']['arxiv_id'])

if __name__ == '__main__':
    (ROOT/'.cache').mkdir(exist_ok=True)
    unittest.main(verbosity=2)
