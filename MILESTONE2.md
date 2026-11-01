# Milestone 2 Extension 

Official specifications:

- Milestone 1: https://hcmus-cs-ta.github.io/lab-book/intro-ds/statement/crawling/
- Milestone 2: https://hcmus-cs-ta.github.io/lab-book/intro-ds/statement/parsing/

This module is **additive**. The existing `src/crawler.py`, `src/audit.py`, `src/status.py`, `src/sync_report.py`, all original tests, original README and the collected `data/records/**` contents are **not edited**. `src.milestone2.pipeline.Milestone2Parser` subclasses `Milestone1CorpusReader`, a read-only adapter that delegates to Milestone 1 `src.crawler.paper_dir()` and `src.crawler.read_json()`. `Milestone2MemorySampler` subclasses the **original** `src.crawler.MemorySampler` with `super().finish()`.

## Setup and run (from `source_repo/`)

Python 3.11+ and the **unchanged** Mile 1 dependency file are sufficient for the offline parser:

```sh
python -m pip install -r src/requirements.txt
python -m src.milestone2.cli --output data --max-papers 20 --report ../report_repo
```

Inspect `data/milestone2/summary.json`, `data/milestone2/status.csv`, and `data/milestone2/tables/*.jsonl` (20-paper **sample only**). The `--output` directory **is the original Milestone 1 data root**, not the parsed output. The original corpus is only read. Run the entire 5,000-publication assignment by **omitting** `--max-papers`:

```sh
python -m src.milestone2.cli --output data --report ../report_repo
```

Parser is offline: no arXiv or Semantic Scholar HTTP calls. Interrupt/resume is supported with one `checkpoint.json` per parsed publication. Use `--force` to replace **only the parsed outputs** (not the crawler data). Use `--parsed-output ./another_output` to store parsed output elsewhere. `--no-tables` suppresses combined tables while retaining per-paper JSONL.

**Windows PowerShell** uses the same module commands, for example:

```powershell
py -m pip install -r .\src\requirements.txt
py -m unittest discover -s tests -v
py -m src.milestone2.cli --output .\data --max-papers 20 --report ..\report_repo
```

The tests add the required `source_repo` and `source_repo/src` paths during discovery, so run the full suite directly from `source_repo` without setting `PYTHONPATH`:

```powershell
py -m unittest discover -s tests -v
```

## Added source and class design

```text
source_repo/
├── src/                      [all original files remain unchanged]
│   └── milestone2/           [NEW]
│       ├── __init__.py
│       ├── latex.py           compilation-path expansion, hierarchy, math/figure/sentences
│       ├── bibliography.py    .bib / \bibitem parsing, cross-version field union, cite aliases
│       ├── pipeline.py        Milestone1CorpusReader → Milestone2Parser; metrics inheritance
│       └── cli.py             offline runner
├── tests/
│   ├── test_crawler.py        [unchanged]
│   ├── test_pro.py            [unchanged]
│   └── test_milestone2.py     [NEW]
└── MILESTONE2.md             [NEW]
```

Inheritance and data flow:

```text
Milestone 1's existing src.crawler.{paper_dir,read_json}
                      │
                      ▼ (delegated, read-only)
              Milestone1CorpusReader
                      │ (subclass)
                      ▼
                Milestone2Parser ─→ gather → parse_hierarchy → dedup → JSONL

Milestone 1's existing src.crawler.MemorySampler
                      │ (subclass)
                      ▼
              Milestone2MemorySampler
```

For each source-verified `vN`:

1. Identify the main TeX root with an uncommented `\documentclass` and prefer a document with `\begin{document}`. Expand active `\input`/`\include` recursively; stop at `\end{document}`. Ignore unreferenced TeX. Path traversal and inclusion cycles are guarded.
2. Create nested section/paragraph headings, `list`/`item` branches, and `sentence`/`formula`/`figure` leaves (tables are figures). Exclude bibliography sections and preserve unnumbered acknowledgements and appendices.
3. Normalize inline and displayed math, remove nonsemantic formatting, and split sentences conservatively so inline math, decimals, URLs and common abbreviations are not cut at periods.
4. Gather inline `\bibitem` and active `.bib` references; match reference entries by DOI or normalized title, merge nonempty fields across versions, choose a canonical key and rewrite `\cite` **in parsed text, never raw TeX**.
5. Share element IDs for equal cleaned content and type across versions **of the same publication**. Emit per-version parent-child edges, stable version-root IDs, and explicit empty/no-root outcomes.

## Output format (only additions under `data/milestone2/`)

```text
data/milestone2/
├── records_data/<arxiv-id-with-dash>/
│   ├── elements.jsonl
│   ├── hierarchy.jsonl
│   ├── bibtex.jsonl
│   ├── versions.jsonl         # root_id, used TeX, warnings, status, cite alias map
│   ├── metrics.json
│   └── checkpoint.json
├── tables/
│   ├── elements.jsonl        # element_id, arxiv_id, kind, content
│   ├── hierarchy.jsonl       # arxiv_id, version, element_id, parent_id
│   ├── bibtex.jsonl          # arxiv_id, citation_key, entry_type, title, authors, year, doi, journal, url
│   └── versions.jsonl        # additional coverage/root ID table
├── status.csv
└── summary.json
```

These JSONL schemas follow the table columns described in the assignment, and the extra `versions` table records real no-source cases without inventing elements. A document-root row exists in `elements`; roots have no parent edge and are linked by `versions.root_id`.

## Report and tests

The `--report` option creates only the Milestone 2 aggregate summary and
status files in the selected report repository's `report_data/` directory.
The report repository is separate from the source-code repository and contains
the cumulative Milestone 1 and 2 notebooks. Its `_toc.yml` lists both chapters;
build the book from the report repository root with `jupyter-book build .`.
The report's GitHub Actions workflow deploys the built book to GitHub Pages.

## Limitations (do not overclaim accuracy)

- LaTeX preprocessing without TeX execution cannot always resolve custom macros, `\IfFileExists`, conditional compilation, nonstandard include systems or nested math environments. `no_root` and missing-include warnings should be audited against the rendered paper.
- Pure-regex BibTeX and `\bibitem` conversion is approximate for unstructured bibliographies; inferred titles require human inspection. References without a known title/DOI may not deduplicate, while different works with the same title may merge incorrectly.
- The hierarchy is modeled as distinct cleaned elements + per-version edges. Identical repeated text within one version can share an element, making it a content-addressed graph rather than a strictly occurrence-unique tree. This matches the distinct-elements table schema but may require occurrence-level metadata for further tasks.
- The downloaded corpus intentionally has no figure binaries; figure elements can retain caption/LaTeX references but cannot recover image pixels. Some source archives have no `.tex` or only missing `\documentclass` files.
- Performance is environment-specific. The course requires final benchmark on **Google Colab CPU-only**; local measurements are not that benchmark. A resumed run's invocation wall time does not include prior interrupted runs.
- Milestone 2 is a foundation for Milestone 3. This code does **not** implement Milestone 3 matching or publish the dataset.
