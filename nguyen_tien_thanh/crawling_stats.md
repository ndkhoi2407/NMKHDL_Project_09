---
kernelspec:
  display_name: Python 3
  language: python
  name: python3
---

**Full Name:** Nguyen Tien Thanh  
**Student ID:** 24127121  
**Class:** 24KHDL1  
**Group:** 09  

---

# Evidence audit and reproducibility

This page reads only the small `m1_data/` and `m2_data/` exports. The original `data/` corpus is neither required nor published. Checks compare independent exported representations; they establish internal consistency, not a new crawl or a manual validation of every parsed sentence.

(colab-summary)=
## Google Colab CPU Benchmark – 5,000 Papers

| Metric | Milestone 1 | Milestone 2 |
|---|---:|---:|
| Publications | 5,000 | 5,000 |
| Discovered versions | 6,348 | 6,348 |
| Processing time | 88,793.10 s | 561.64 s |
| Processing duration | 24 h 39 min 53 s | 9 min 21.64 s |
| Average time per paper | 17.76 s | 0.1123 s |
| Table export time | N/A | 50.80 s |
| Parsing + export | N/A | 612.44 s |

The following memory figures come from the **previously measured Colab sample**, not the new full-corpus run:

| Sample memory (PSS) | M1 | M2 |
|---|---:|---:|
| Peak | 55.60 MiB | 41.42 MiB |
| Average | 37.79 MiB | 31.02 MiB |

*Provenance: full-corpus timings are student-reported results of the new Colab run; raw logs and summaries are unavailable for independent verification. Per-paper averages divide the supplied duration by 5,000. Storage estimates retain their calculated status. Historical Windows statistics and the 17 download errors are unchanged. See the [Colab benchmark](colab_benchmarks.md) for all four sections and the environment.*

## Official requirements audit

Baseline: [M1 specification](https://hcmus-cs-ta.github.io/lab-book/intro-ds/statement/crawling/), [M2 specification](https://hcmus-cs-ta.github.io/lab-book/intro-ds/statement/parsing/) and [project logistics](https://hcmus-cs-ta.github.io/lab-book/intro-ds/statement/). PASS means the stated check is supported; PARTIAL means a limitation remains; FAIL means a requirement is currently unmet. This is an implementation audit, not an instructor-assigned grade.

```{code-cell} python
:tags: [hide-input]
import pandas as pd
from IPython.display import display
import report_utils as ru
display(pd.DataFrame(ru.load_json('audit_data/compliance_checklist.json')))
```

## Current implementation verification

Historical corpus and benchmark exports remain unchanged. `audit_data/implementation_checks.json` records tests of the corrected code separately from the earlier corpus audit, including the two targeted probes. A PASS for a code regression check does not mean historical outputs were regenerated.

```{code-cell} python
:tags: [hide-input]
implementation = ru.load_json('audit_data/implementation_checks.json')
display(pd.DataFrame(implementation['suites']))
display(pd.DataFrame(implementation['targeted_probes']))
probe = ru.load_json('audit_data/download_probe.json')
display(pd.DataFrame(probe['observations']))
```

## Read-only local corpus audit

`scripts/audit_corpus.py` inspects existing source files, metadata and references without network access or parsing publications. The retained `corpus_audit.json` snapshot predates the code corrections; its `current_root_probe` column describes the code at that earlier audit, not the corrected implementation. Its small export is committed separately from the immutable measured exports. Rebuilding this book reads the audit export; it never scans the raw corpus.

```{code-cell} python
:tags: [hide-input]
import json
from pathlib import Path
import pandas as pd
from IPython.display import display
import report_utils as ru
corpus = ru.load_json('audit_data/corpus_audit.json')
display(pd.DataFrame(list(corpus['source_extensions'].items()), columns=['Extension', 'Files']))
display(ru.kv_table(corpus['metadata'].items()))
display(pd.DataFrame(corpus['metadata_version_discrepancies']))
display(ru.kv_table(corpus['references'].items()))
display(ru.kv_table(corpus['figure_command_sample'].items()))
display(pd.DataFrame(list(corpus['files_containing_figure_commands'].items()), columns=['Retained command', 'Files containing command']))
```

Date-list length agreement checks only that `revised_dates` has one date per discovered version; it does not validate historical per-version titles or authors. Fourteen publications have more revision dates than discovered versions. This is a snapshot inconsistency requiring reconciliation, not evidence that the stored discovery list includes every current revision; this audit does not invent additional version records or alter the benchmark denominator.

The historical metadata stores a single title/authors snapshot, includes v1 in `revised_dates`, and omits venue. Corrected code now preserves journal-reference/venue fields where available, maps dates to version labels, and can obtain actual versioned API snapshots with verified returned identifiers. The main pipeline enables that option; old records are not retroactively filled. `references.py` queries the publication identifier rather than each version, and completed files are skipped on resume. The retained references use a legacy schema: the dictionary key stores the arXiv identifier, while the row itself has no `arxiv_id` field. The audit therefore checks both explicit fields and identifier-shaped keys; it must not misclassify legacy rows as non-arXiv solely because that field is absent. No non-arXiv rows were found. Therefore the current code's default non-arXiv support cannot restore references omitted by an earlier crawl, and locally preserving all crawled references remains unmet.

## Failure investigation

```{code-cell} python
:tags: [hide-input]
display(pd.DataFrame(corpus['download_errors']))
display(pd.DataFrame(corpus['root_probes']))
```

All 17 stored download failures report HTTP 404, across 16 publications (one has two failed versions); corresponding source directories are absent. The downloader treats 404 as non-retryable within one invocation and removes its empty destination. This explains the downstream `no_source_dir` outcomes. These are historical responses, not proof of permanent unavailability; no endpoints were retried during this audit.

`2607.05431v1` is Plain TeX (`dd321.tex`, compiler `pdftex`, ending in `\end`) and has no LaTeX `\documentclass` or document environment. The current root heuristic still does not support this format. `2607.07654v1` is different: `adiabatic3.tex` has 402 CR characters and no LF characters. In the historical parser, the `%[^\n]*` comment expression removed the entire CR-only file after its opening comment. A root-only probe finds `adiabatic3.tex` after newline normalization. This identifies a reproducible cause without parsing or rewriting either paper. The current `strip_comments` normalizes CR-only/CRLF line endings before removing comments. A targeted parse on a temporary copy now succeeds for this version; the measured outputs still contain both historical failures.

## Parser logic verification

Run `python scripts/check_parser_logic.py` for in-memory cases covering DOI/title merging, frequency and newest-key selection, key collisions, citation options, fallback of missing fields, the non-`misc` type preference, repeated-text occurrence IDs, and remapping before content identity. A regression check now verifies that CR-only comments preserve the document root. The separate pipeline suite tests source-only extraction and same-key field merging through actual `.bib` and `\bibitem` ingestion.

Field unionization preserves available fields rather than concatenating conflicting values. Content identity is `(kind, cleaned content)`; document roots remain version-specific, and repeated identical nodes within a version have distinct IDs. Same-key field loss is corrected: later non-empty fields merge into the entry, while conflicting earlier/later values are retained in per-version diagnostics. Author macros, nonstandard citation commands and heuristic extraction still prevent a claim of universal correctness.

## Provenance and measurement boundaries

| Stage | Evidence | Interpretation |
| --- | --- | --- |
| Crawling | `m1_data/summary.json`, `papers.csv`, empty `samples.csv` | Report-only snapshot, exported 28 October 2026. Counts come from existing status files. Recorded time belongs to a resumed run; discovery was skipped. RAM and temporary disk peaks were not measured. |
| Parsing | `m2_data/summary.json`, `papers.csv`, `samples.csv` | Instrumented run dated 2 November 2026, 398 RSS samples. Publication job completion does not imply all versions parsed. |
| Parser structure | `tables_stats.json`, `kind_counts.json`, `failures.json`, `example.json` | Aggregates and a truncated real example exported by `src/make_report_data.py`. |

The two snapshots were collected on different dates. Their counts should be compared with that limitation in mind. No benchmark from the reference website is used.

## Consistency checks

```{code-cell} python
:tags: [hide-input]
import pandas as pd
from IPython.display import display
import report_utils as ru
from scripts.validate_report import audit, inventory
checks = audit()
display(checks)
assert (checks.Result == 'PASS').all(), 'Inconsistent report evidence'
```

## Download outcomes

Percentages below use all discovered versions as the denominator. Error versions are retained, rather than silently removed from coverage calculations.

```{code-cell} python
:tags: [hide-input]
summary = ru.load_json('m1_data/summary.json')
counts = summary['data']['versions_by_status']
statuses = pd.DataFrame(list(counts.items()), columns=['Status', 'Versions'])
statuses['Share (%)'] = 100 * statuses.Versions / summary['data']['versions_total']
display(statuses)
ru.bar(statuses.Status, {'Versions': statuses.Versions}, 'Download outcomes across all versions', 'Versions')
```

## Input fingerprints

These hashes identify the exact files used for this build. Missing values remain missing; a recorded zero is shown only when it is present in the evidence.

```{code-cell} python
:tags: [hide-input]
display(inventory())
```

## Rebuild without the corpus

From PowerShell, activate the virtual environment and run `npm run build`. This invokes `myst build --html --execute --strict`; the execution flag is necessary for Markdown code cells. A bare `myst build --html` does not execute new cells. MyST caches outputs; after changing only a data file or `report_utils.py`, use `myst clean --execute` before rebuilding.

For setup, deployment and preview commands, see the repository README. The build needs network access to obtain the MyST book theme on its first run, but never calls arXiv or Semantic Scholar.
