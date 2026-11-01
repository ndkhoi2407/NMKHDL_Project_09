# Milestone 1: Jupyter Book report

This report is maintained separately from the crawler source repository. The assignment asks for a public source-code repository and a Jupyter Book report hosted on GitHub Pages.

## Environment and data

Use Python 3.11 and install the report dependencies from this directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

The notebook reads `summary.json`, `status.csv`, `runs.jsonl`, and the optional `benchmark_merged_colab.json` from `report_data/`. To refresh the aggregate crawl data, run this from `source_repo`:

```powershell
python .\src\sync_report.py --data data --report ..\report_repo
```

Only aggregate JSON/CSV/JSONL files are copied. Downloaded archives, extracted TeX, and complete citation corpora remain in the source repository's local data directory.

## Build locally

From `report_repo`:

```powershell
jupyter-book build .
```

Open `_build/html/index.html` and review the rendered tables and charts. Notebook execution is enabled during the build. Update author/group details before submission.

## Current Colab CPU-only measurements

Use `report_data/benchmark_merged_colab.json` as the canonical Colab record. It declares `full_pipeline_end_to_end_colab_measurements_and_completion`, marks the session `completed` and `all_phases_completed: true`, and records **5,000/5,000 assigned arXiv IDs** with no pending IDs.

The recorded end-to-end wall time is **15,888.335 seconds (4 h 24 min 48.335 s)**, or **3.177667 seconds per assigned paper**. Its phase map sums to that runtime: `discover` **725.372 s**, `fetch_and_download` **11,200 s**, and `parse_and_extract` **3,962.963 s**. The discovery-phase mean derived from the phase map is **0.145074 s per assigned ID**. Process-tree RAM is **42,872,832 bytes peak (40.9 MiB)** and **42,598,470 bytes sample-weighted mean (40.6 MiB)** across **1,527 samples**. The output directory's largest sampled size is **10,985,472 bytes (10.5 MiB)** across **56 disk samples**; its final recorded size is also 10,985,472 bytes.

The discovery submetrics are derived from the explicit `discover` phase timing and completed-ID count; the end-to-end mean is derived from total wall time divided by 5,000. The phase timings sum to the recorded wall time. The record's start/end timestamps span **15 h 44 min 8 s**, while its `wall_seconds` field is **4 h 24 min 48.335 s**. The report presents both recorded values and uses `wall_seconds` for the end-to-end runtime metric.

The Colab record reports a final output-directory size of **10.5 MiB**. The **1.01 GiB** size in `summary.json` belongs to a separately synced local corpus snapshot generated before the Colab session; it is reported separately and is not substituted for the Colab output-directory measurement. Phase timings are shown using the grouped labels in the merged benchmark record, whose values sum to the recorded end-to-end wall time.

## Publish on GitHub Pages

1. Push this report directory to a separate public GitHub repository on branch `main`.
2. In **Settings > Pages**, select **GitHub Actions** as the build/deploy source.
3. The included `.github/workflows/pages.yml` builds the Jupyter Book and deploys `_build/html`.
4. Confirm the Pages URL is live, then submit it together with the source-code repository URL.

## Data caveats

- OAI-PMH provides current paper fields and version dates; it cannot establish every older version's historical title and abstract. Exact-version Atom coverage is reported separately.
- Semantic Scholar references are publication-level. They do not establish a different reference list for each arXiv revision; first-submission dates are enriched separately.
- The corpus tables describe the most recently synced crawl data. `assigned_ids` states the size of that dataset.
- Local `runs.jsonl` entries may combine separate or resumed invocations. They are not treated as a single Colab end-to-end measurement. Estimated disk bounds are labeled as estimates.
- Building the report reads local files and does not start the crawler or make API requests.
