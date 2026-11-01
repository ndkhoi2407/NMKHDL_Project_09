# arXiv Milestone 1 — Data Crawling

**Course:** HCMUS Introduction to Data Science  
**Assigned IDs:** `2607.13694` through `2607.18693` (5,000 base IDs, inclusive).  
**Specification:** [Milestone 1 — Data Crawling](https://hcmus-cs-ta.github.io/lab-book/intro-ds/statement/crawling/)

A single-process, conservative arXiv + Semantic Scholar data collector with per-paper checkpoints, safety-limited extraction, resume, CSV/JSONL exports, RAM and disk statistics, an offline status view, and an offline audit.

## Project structure

```text
source_repo/
  src/
    crawler.py          # all-stage crawler; resumable and rate-limited
    status.py           # inspect the live records without making network requests
    audit.py            # offline integrity audit
    sync_report.py      # send only aggregate statistics to the report repository
    requirements.txt
    __init__.py
  tests/
    test_crawler.py
    test_pro.py
  .vscode/settings.json  # Pylance import paths + unittest discovery
  .gitignore            # never publish collected data
  README.md
  data/                 # created at runtime; DO NOT commit
```

## Environment

Python **3.11 or later**; commands below should be run from `source_repo`.

**Windows PowerShell**:

```powershell
python -m pip install -r .\src\requirements.txt
python -m unittest discover -s tests -v
python .\src\crawler.py --max-papers 3 --phase discover --discovery-backend oai --output data
python .\src\crawler.py --max-papers 3 --phase sources --output data
python .\src\crawler.py --max-papers 3 --phase references --output data
python .\src\status.py --max-papers 3 --output data
python .\src\audit.py --max-papers 3 --output data
```

**macOS / Linux**: replace backslashes with `/`; use `python3` if `python` is not available.

## Run in stages, increasing scope

The prefix range is always deterministic; increasing `--max-papers` reuses prior checkpoints.

```powershell
# 100 base IDs — start with discovery, then versions, then references
python .\src\crawler.py --max-papers 100 --phase discover --discovery-backend oai --arxiv-delay 4 --output data
python .\src\crawler.py --max-papers 100 --phase sources --arxiv-delay 4 --output data
python .\src\crawler.py --max-papers 100 --phase references --s2-delay 5 --output data

# Enrich first-submission dates of referenced arXiv papers (optional at first; required for coverage)
python .\src\crawler.py --max-papers 100 --phase enrich-refs --enrich-backend oai --arxiv-delay 4 --output data

# Exact historical version metadata through Atom API (may hit HTTP 429)
python .\src\crawler.py --max-papers 100 --phase metadata --arxiv-delay 4 --output data

# After checking the 100, extend incrementally (500 then 5,000)
python .\src\crawler.py --max-papers 500 --phase discover --discovery-backend oai --output data
python .\src\crawler.py --max-papers 500 --phase sources --output data
python .\src\crawler.py --max-papers 500 --phase references --output data
```

For the full range, **remove `--max-papers`** from the same three phase commands, or run:

```powershell
python .\src\crawler.py --phase all --discovery-backend oai --enrich-backend oai --output data
```

The `all` mode with OAI deliberately **does not assert exact historical metadata**. Use `--phase metadata` separately when the arXiv Atom API can serve versioned requests. `--phase all` may take hours/days for 5,000 IDs and citations; keep a reliable connection, disk capacity, and an appropriate runtime (Google Colab CPU-only for final benchmark). Run just one crawler process at a time.

For the final end-to-end CPU benchmark, upload `run_colab_full_benchmark.py` alongside the crawler and run it inside a Colab CPU-only runtime:

```python
!python /content/run_colab_full_benchmark.py \
    --crawler /content/milestone1/src/crawler.py \
    --output /content/milestone1/full_cpu_benchmark \
    --report /content/drive/MyDrive/Milestone1_Backup/benchmark_source_full_colab.json
```

The benchmark runs discovery, exact version metadata, source downloads, Semantic Scholar references, and reference-date enrichment in sequence. It rejects a nonempty output folder and reports full coverage only when all five phases finish and the 5,000-ID summary has no pending work and complete reference-date enrichment. It can take many hours and make external API requests.

## Live progress, without disrupting a running crawl

In a **second terminal** pointed at `source_repo`, type:

```powershell
python .\src\status.py --max-papers 100 --watch 15 --output data
```

Stop *only this monitor* with Ctrl+C; the crawler in the first terminal keeps running. To inspect once, omit `--watch 15`. All phases also log progress after every 3 IDs by default (`--progress-every N`).

Inspect uncompleted entries and source-file consistency:

```powershell
python .\src\audit.py --max-papers 100 --output data
Get-Content .\data\summary.json
```

Audit reports specific IDs; it distinguishes legitimate PDF-only/no-source from unverified downloads and notes metadata fidelity separately.

## HTTP 429 etiquette

- arXiv APIs require **at least 3 s** between requests; this crawler uses one connection at a time. Defaults: `--arxiv-delay 3.2`, `--s2-delay 3.2`. On unauthenticated Semantic Scholar, a delay around 5s is safer; accounts may share throttling.
- Responses with `Retry-After` are honored with bounded exponential backoff. After retries are exhausted on 429, the phase **stops and leaves saved checkpoints intact** rather than hammering hundreds more IDs.
- If the Atom API consistently rejects metadata requests, use `--discovery-backend oai` and `--enrich-backend oai`. OAI-PMH `arXivRaw` provides **accurate revision dates but not the original title/abstract/authors of every revision**. The report flags this limitation instead of fabricating historical fields.
- When receiving repeated 429s, pause and resume later. No method guarantees external APIs will be available.
- Optional environment variables: `S2_API_KEY` for a Semantic Scholar API key; `CRAWLER_CONTACT` for a contact email in User-Agent. Never commit keys.

## Source extraction and safety

Every version (`v1…vN`) is downloaded from `https://export.arxiv.org/src/<id>vN`. Source archives may be tar, zip, compressed single-file TeX, plain TeX, or PDF-only. The crawler extracts **only `.tex` and `.bib`** using capped extraction sizes; archive paths cannot escape the destination directory, and ZIP symlinks are ignored. LaTeX commands (including `figure` environments and `\includegraphics`) are **preserved byte-for-byte**. PDF-only/no-TeX is recorded explicitly.

Artifacts:

```text
data/
  records/2607-13694/
    paper.json
    versions_oai.json
    references_all.json           # all references, including without an arXiv ID
    v1/metadata.json               # if available: metadata_fidelity field
    v1/source_status.json
    v1/source/**/*.tex|*.bib
  tables/papers.jsonl              # exact required columns
  tables/references.jsonl          # only references with arXiv ID
  tables/status.csv                # per-ID completion
  ref_submission_dates.sqlite     # de-duplicated arXiv first dates
  summary.json
  runs.jsonl                       # measurement per invocation
  audit.json                       # optional offline audit
```

`references_all.json` is publication-level Semantic Scholar data, **not per-version cited bibliography**: the API does not reliably distinguish references by revision. This limitation is declared in the report. Missing arXiv first-submission dates remain empty rather than being substituted with journal publication dates.

## Reporting, repository hygiene and submission

The official assignment requests **two separate public repositories**:

1. **Shared source-code repository** (`source_repo`): `.py`, requirements, README, tests; no corpus files, cache, archives, keys, or downloaded data.
2. **Report repository** (`report_repo`): Jupyter Book and GitHub Pages; plots and tables are generated at build time from *actual* logged statistics.

After collecting data:

```powershell
python .\src\crawler.py --max-papers 100 --phase export --output data
python .\src\sync_report.py --data data --report ..\report_repo
```

Then build the separate `report_repo`, verify its numerical results and source coverage, and publish GitHub Pages. The final group Moodle submission is **the public code repo URL plus public report URL**, not a ZIP of the working data. Benchmark using a Colab CPU-only environment as specified by the instructor; local Windows timings are preliminary.

## Data quality and limitations

- `total_versions_source_checked` includes successful `.tex/.bib`, explicit no-TeX and no-source cases. Do not conflate with `versions_with_tex_bib`.
- `pending_exact_version_metadata` tracks any version lacking a successful Atom version-specific lookup. OAI only provides current paper fields plus revision dates.
- Errors and pending checkpoints remain retryable. `not_found` is a genuine OAI/Atom absence, whereas network errors are *pending*, never silently counted as unavailable publications.
- Memory `peak_ram_bytes`/`average_ram_bytes` are sampled RSS of **this crawler process**, not entire host memory. `approx_peak_disk_upper_bound_bytes` is an estimate (final dataset size + maximum temporary downloaded archive) rather than observed disk peak. End-to-end wall time must include all invocations and delays.
