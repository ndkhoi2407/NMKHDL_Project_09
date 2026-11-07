"""Offline Milestone 2 integration tests. Does not touch or mock Milestone 1 code."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from src.milestone2.bibliography import ReferenceStore, parse_bibtex, parse_bibitems
from src.milestone2.latex import gather, parse_hierarchy, split_sentences, strip_comments, update_citations
from src.milestone2.pipeline import Milestone2Parser, Milestone2MemorySampler, run
from src.crawler import MemorySampler


class TestMile2(unittest.TestCase):
    def test_inherits_unchanged_mile1_sampler(self):
        self.assertTrue(issubclass(Milestone2MemorySampler, MemorySampler))

    def test_includes_only_compilation_path(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            (d / 'main.tex').write_text(r'''\documentclass{article}
\begin{document}
\section{Introduction}
Hello world. % \input{unused}
\input{part}
% \input{unused}
\end{document}
''')
            (d / 'part.tex').write_text(r'\subsection{Results}Two studies. \input{sub/deep}')
            (d / 'sub').mkdir()
            (d / 'sub/deep.tex').write_text('And more.')
            (d / 'unused.tex').write_text('NOT PART OF THE PUBLICATION')
            data = gather(d)
            self.assertEqual(data.root, 'main.tex')
            self.assertEqual(set(data.files), {'main.tex', 'part.tex', 'sub/deep.tex'})
            self.assertNotIn('NOT PART', data.source)
            tree = parse_hierarchy(data.source)
            self.assertEqual(tree.children[0].content, 'Introduction')
            self.assertEqual(tree.children[0].children[-1].content, 'Results')

    def test_include_cycle_cannot_escape_root(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            (d / 'main.tex').write_text(r'\documentclass{article}\begin{document}\input{again}\input{../../bad}\end{document}')
            (d / 'again.tex').write_text(r'\input{main} Valid body.')
            g = gather(d)
            self.assertTrue(any(w.startswith('include_cycle') for w in g.warnings))
            self.assertTrue(any(w.startswith('missing_include') for w in g.warnings))

    def test_comment_and_math_normalization(self):
        self.assertIn(r'\%', strip_comments(r'98\% valid % comment'))
        tree = parse_hierarchy(r'''\section{Hello}
We have \(a+b\) and \[ x=2 \].
\begin{equation}a = b\end{equation}
\begin{figure}[htpb]\centering\caption{Our result}\end{figure}''')
        leaves = tree.children[0].children
        self.assertTrue(any('$a+b$' in n.content for n in leaves))
        self.assertEqual(sum(n.kind == 'formula' for n in leaves), 2)
        self.assertEqual(sum(n.kind == 'figure' for n in leaves), 1)

    def test_empty_display_math_does_not_crash(self):
        tree = parse_hierarchy(r"\section{M} Before. \[\] After.")
        self.assertEqual(tree.children[0].children[1].kind, "formula")

    def test_sentence_rules(self):
        sentences = split_sentences(r'''The value is 3.14 and Fig. 1. is useful. A URL is \url{https://a.b/c}. Next step follows. Inline $a.b$ stays.''')
        self.assertEqual(len(sentences), 4)
        self.assertIn('3.14', sentences[0])
        self.assertIn('$a.b$', sentences[-1])

    def test_nested_list(self):
        doc = parse_hierarchy(r'\section{M}\begin{itemize}\item First. \begin{enumerate}\item Nested.\end{enumerate}\item Second.\end{itemize}')
        group = doc.children[0].children[0]
        self.assertEqual(group.kind, 'list')
        self.assertEqual(len(group.children), 2)
        self.assertEqual(group.children[0].children[1].kind, 'list')

    def test_bibtex_and_canonical_cite_rewrite(self):
        b1 = parse_bibtex('@article{alpha, title={Great Model}, author={Ann and Bob}, year={2024}}')
        b2 = parse_bibtex('@article{beta, title={Great Model}, author={Ann}, doi={10.3/zzz}}')
        store = ReferenceStore()
        store.add(1, b1)
        store.add(2, b2)
        self.assertEqual(len(store.records), 1)
        self.assertEqual(store.records[0]['doi'], '10.3/zzz')
        self.assertEqual(store.records[0]['authors'], ['Ann', 'Bob'])
        self.assertEqual(update_citations(r'\cite{beta,other}', store.aliases[2]), r'\cite{alpha,other}')

    def test_bibitem(self):
        refs = parse_bibitems(r'\begin{thebibliography}{1}\bibitem{k1} A author. \\newblock "Very Good Work". 2020.\end{thebibliography}')
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]['citation_key'], 'k1')
        self.assertEqual(refs[0]['year'], 2020)

    def test_full_pipeline_dedup_versions_empty_checkpoint(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)/'data'
            base = root/'records'/'2607-13694'
            base.mkdir(parents=True)
            (base/'paper.json').write_text(json.dumps({'status':'found', 'latest_version':3}))
            for v, content in ((1,r'\documentclass{article}\begin{document}\section{One}Shared sentence. \cite{first}.\bibliography{refs}\end{document}'),
                               (2,r'\documentclass{article}\begin{document}\section{Two}Shared sentence. \cite{second}.\bibliography{refs}\end{document}')):
                d = base/f'v{v}'
                (d/'source').mkdir(parents=True)
                (d/'source'/'main.tex').write_text(content)
                bib = '@article{first, title={Shared science title}, year={2021}}' if v == 1 else '@article{second, title={Shared science title}, doi={10.5/demo}}'
                (d/'source'/'refs.bib').write_text(bib)
                (d/'source_status.json').write_text('{"status":"ok"}')
            d = base/'v3'
            d.mkdir()
            (d/'source_status.json').write_text('{"status":"no_source"}')
            parser = Milestone2Parser(root, root/'milestone2'/'records_data')
            item = parser.parse_publication('2607.13694')
            self.assertEqual([x['parse_status'] for x in item.versions], ['ok','ok','empty'])
            self.assertEqual(len(item.bibtex), 1)
            self.assertEqual(item.bibtex[0]['doi'], '10.5/demo')
            self.assertEqual(item.versions[1]['canonical_citation_keys']['second'], 'first')
            sentences = [x for x in item.elements if x['kind'] == 'sentence']
            self.assertEqual(len([x for x in sentences if x['content'] == 'Shared sentence.']), 1)
            el = next(x['element_id'] for x in sentences if x['content'] == 'Shared sentence.')
            self.assertEqual({x['version'] for x in item.hierarchy if x['element_id'] == el}, {1,2})
            summary = run(root, ['2607.13694'])
            self.assertEqual(summary['metrics']['versions_empty'], 1)
            self.assertTrue((root/'milestone2'/'tables'/'elements.jsonl').exists())
            second = run(root, ['2607.13694'])
            self.assertEqual(second['metrics']['cached'], 1)

if __name__ == '__main__':
    unittest.main()
