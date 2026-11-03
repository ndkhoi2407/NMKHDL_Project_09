# HCMUS arXiv Project — Group 09

Milestones 1 and 2 of **Introduction to Data Science**, University of Science, VNU-HCM. The assigned range is **2607.03694–2607.08693**, comprising 5,000 base IDs. This is the cumulative source-code repository; the Jupyter Book is maintained separately.

- Source branch: [`24127121`](https://github.com/ndkhoi2407/NMKHDL_Project_09/tree/24127121)
- Report repository: [TienThanh1234/arXiV-project](https://github.com/TienThanh1234/arXiV-project)
- Verified public report: [Group 09 Jupyter Book](https://tienthanh1234.github.io/arXiV-project/). The homepage, both milestone chapters and evidence pages were verified after successful GitHub Pages deployment.
- Official specifications: [Milestone 1](https://hcmus-cs-ta.github.io/lab-book/intro-ds/statement/crawling/), [Milestone 2](https://hcmus-cs-ta.github.io/lab-book/intro-ds/statement/parsing/).

## Environment setup

The implementation and offline tests have been validated with **Python 3.14** on Windows. Use pip and a virtual environment; conda is not required. Colab uses its supplied Python interpreter and must be benchmarked separately.

```powershell
git clone --branch 24127121 --single-branch https://github.com/ndkhoi2407/NMKHDL_Project_09.git
cd NMKHDL_Project_09
python -m venv .venv
$env:PATH = "$PWD\.venv\Scripts;$env:PATH"
python -m pip install -r src/requirements.txt
python -m pip check
```

Dependencies are `arxiv`, `requests` and `psutil`, pinned in `src/requirements.txt`. Parsing and report-data export otherwise use the Python standard library. If `ensurepip` fails while creating the environment, the system pip can populate it with `python -m pip --python .venv/Scripts/python.exe install -r src/requirements.txt` before setting PATH.

Reference crawling can use a real Semantic Scholar key, supplied privately through the environment. Do not paste credentials into code or commit them:

```powershell
$secureKey = Read-Host "Semantic Scholar API key" -AsSecureString
$env:S2_API_KEY = [System.Net.NetworkCredential]::new('', $secureKey).Password
```

Optionally set `ARXIV_CRAWLER_CONTACT` to an ASCII contact address for the User-Agent. No API key or network is needed for the offline tests.

## Project structure

```text
src/
  discover.py             # assigned IDs and version lists
  download_sources.py     # versioned /src/ downloads, .tex/.bib-only extraction
  process_sources.py      # legacy image cleanup; not a corpus migration tool
  metadata.py             # publication and identifier-verified version metadata
  references.py           # Semantic Scholar responses, projections and provenance
  main.py                 # resumable M1 driver with per-step timings
  parse.py                # hierarchy, normalization, bibliography and deduplication
  benchmark.py            # M1 process-tree monitoring and corpus statistics
  benchmark_parse.py      # M2 monitoring and statistics
  make_report_data.py     # small report exports from existing results
  requirements.txt
scripts/
  check_parser_logic.py
  check_pipeline.py
  check_colab_workflow.py
  colab_benchmark.py
notebooks/colab_cpu_benchmarks.ipynb
BENCHMARKS.md
data/                     # generated locally; excluded from Git
```

## Safe offline validation

These commands exercise small fixtures, mocked APIs and benchmark orchestration. They do not crawl or parse the 5,000-publication corpus:

```powershell
python scripts/check_parser_logic.py
python scripts/check_pipeline.py
python scripts/check_colab_workflow.py
```

The checks cover source-only tar/ZIP extraction and unchanged TeX bytes, path filtering, CR-only line endings, duplicate-key field unionization, citation remapping, exact-text reuse, metadata provenance and complete reference-response retention. Passing fixtures does not establish universal corpus accuracy.

## Milestone 1 — crawling

The driver resolves the assigned IDs through the arXiv API, downloads each version from the versioned source endpoint, processes sources, writes metadata and fetches references. It records `data/timings.json` and resumes completed work. The metadata step enables `--versioned` so historical titles/authors are fetched through actual versioned API identifiers rather than copied from the latest snapshot.

New tar/ZIP extraction writes only `.tex` and `.bib`, preserving their bytes and LaTeX figure commands. This correction does not migrate any old corpus. Source member payload sizes are logical uncompressed bytes, distinct from measured temporary disk consumption. PDF-only/unconvertible versions remain explicit empty records.

### Small trial

Use a separate work directory and a genuinely small discovery range. `--limit` alone does not reduce the discovery range:

```powershell
python src/main.py --prefix 2607 --start 3694 --end 3696 --limit 3 --workdir .cache/trial-m1
```

This is a networked three-ID trial. Only run it when ready to make requests. To parse that trial input, keep its data directory as the working directory:

```powershell
$projectRoot = (Get-Location).Path
Push-Location .cache/trial-m1
python "$projectRoot/src/parse.py" --limit 3 --workers 1 --export
Pop-Location
```

### Full execution — explicit opt-in

The following commands start a complete run; they are documented for reproducibility and were not run while preparing this submission. Use a new working directory to keep historical data intact:

```powershell
python src/main.py --prefix 2607 --start 3694 --end 8693 --workdir .cache/full-m1
```

Individual stages can be run from a working directory containing `data/discovery.json`. Supported targeted selectors include:

```powershell
# Set $projectRoot to the cloned repository before entering an isolated working copy containing data/.
# $projectRoot = (Get-Location).Path
python "$projectRoot/src/download_sources.py" --versions 2607.04159v2
python "$projectRoot/src/metadata.py" --ids 2607.03694 --versioned --refresh
python "$projectRoot/src/references.py" --ids 2607.03694 --refresh
```

`--refresh` replaces selected generated records in that working copy. Completed legacy reference files are otherwise skipped; current defaults cannot recover references absent from an older run. Raw Semantic Scholar responses preserve even unidentifiable references. The reference provenance explicitly describes a shared publication-level response, not an independently measured bibliography for every version.

## Milestone 2 — hierarchical parsing and standardization

Run the parser from the directory containing the intended `data/` input:

```powershell
$projectRoot = (Get-Location).Path
Push-Location .cache/full-m1
python "$projectRoot/src/parse.py" --workers 2 --export
Pop-Location
```

The parser follows the selected compilation root and transitive includes, ignores commented includes, constructs headings, sentence/formula/figure leaves and nested lists, excludes references from the hierarchy, cleans formatting and normalizes math. Bibliographies are extracted from included `.bib` files and `\bibitem` definitions. Duplicate identical keys merge non-empty fields; conflicts remain in version diagnostics. Cross-version unionization remaps citation keys before exact `(kind, cleaned content)` deduplication. Repeated occurrences within one version retain distinct IDs.

For selected publications use `--ids 2607.03694,2607.03695`; `--limit 3` limits the first three discovered publications. `--force` explicitly replaces selected existing parse outputs. `--export-only` merges existing results without reparsing. The per-publication timeout uses `SIGALRM` and is not enforced by that mechanism on Windows. Plain TeX without a LaTeX root remains unsupported; author macro expansion and bibliography extraction are heuristic.

## Generated outputs

```text
data/
  discovery.json, download_status.json, metadata_status.json
  references_status.json, parse_status.json, timings.json
  2607-03694/
    v1/, v2/, ...                 # .tex/.bib sources where available
    metadata.json                 # publication snapshot and dated version map
    metadata_versions.json        # actual versioned API snapshots with provenance
    references.json               # identifiable-reference projection
    references_raw.json           # complete fetched response
    references_provenance.json     # explicit publication scope and version pointers
    parsed.json                   # all versions, elements, hierarchy and bibliography
  tables/{elements,hierarchy,bibtex}.jsonl
  benchmark/{summary.json,papers.csv,samples.csv}
  benchmark_parse/{summary.json,papers.csv,samples.csv}
```

## Benchmarks and reproducibility

The final course testbed is **Google Colab CPU-only**. [BENCHMARKS.md](BENCHMARKS.md), the executable notebook and `scripts/colab_benchmark.py` define the workflow. The runner defaults to a plan and refuses full execution outside Colab or into an existing output directory:

```powershell
python scripts/colab_benchmark.py --stage both --workdir /content/arxiv-new-run --single-trial --workers 2
```

On Colab, explicit `--execute` starts the full run. Retain environment/source hashes, commands, logs, summaries, RAM samples, corpus-disk samples and failures. Merged-table export is timed separately. For an already prepared working directory, supported benchmark entry points are:

```powershell
python "$projectRoot/src/benchmark.py" --prefix 2607 --start 3694 --end 8693 --single-trial
python "$projectRoot/src/benchmark_parse.py" --workers 2
# Statistics from existing results only:
python "$projectRoot/src/benchmark.py" --report-only
python "$projectRoot/src/benchmark_parse.py" --report-only
```

`$projectRoot` is the repository path captured before entering the isolated working directory, as in the M2 example. Use a fresh isolated corpus/output state for valid full-run measurements. `benchmark_parse.py --fresh` deletes existing parser outputs; it is deliberately not required by the fresh-directory runner. A resumed run, a report-only summary and a fresh end-to-end measurement are different experiments.

The report's historical M1 timing is a resumed Windows run with discovery skipped; peak/average RAM, original discovery time and peak disk were not measured. Historical M2 measurements are Windows-only. No real Colab results have been collected. Source-only migration, legacy metadata/reference recovery, version/date reconciliation, residual 404 downloads and Plain TeX support remain open corpus requirements.

To export statistics from existing local results into a new report-data destination:

```powershell
python src/make_report_data.py --m1-out .cache/report-export/m1_data --m2-out .cache/report-export/m2_data
```

This scans existing results; it does not run a crawler or parser. Preserve historical exports and publish new measured runs under distinct provenance labels. The full corpus, generated tables, environments, caches, archives and credentials stay local and must not be force-added to Git.
