---
jupytext:
  text_representation:
    extension: .md
    format_name: myst
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

# Milestone 1 — Crawling

## 1. Objectives

Milestone 1 collects scientific papers from arXiv. Its goals are:

- Resolve the arXiv IDs of the assigned range into papers and find **every version** of each paper.
- Download the full-text **LaTeX sources** of every version (not the PDFs).
- Crawl the metadata of each paper and the **reference information** of each paper through Semantic Scholar.
- Keep the download state of every item so that the crawl can be resumed and audited.
- Prepare the working corpus that Milestone 2 (parsing) and Milestone 3 (matching) consume.

All numbers and figures on this page are generated while the book is compiled, from the small result files in `m1_data/`
(`summary.json`, `papers.csv`, `samples.csv`) produced by the benchmark script.

```{code-cell} python
:tags: [hide-input]
import pandas as pd
from IPython.display import display, Markdown
import report_utils as ru
import os
from pathlib import Path

data_dir = Path.cwd().parent / 'nguyen_tien_thanh'
os.chdir(data_dir)


S = ru.load_json("m1_data/summary.json")
papers = ru.load_csv("m1_data/papers.csv")
samples = ru.load_csv("m1_data/samples.csv")
R, T, M, K, D = (S.get(k) or {} for k in ("run", "timing", "memory", "disk", "data"))
```

```{warning}
This is a **report-only snapshot**, exported on 28 October 2026. Counts describe the saved corpus, not a new crawl performed for this book. The stored 2,445.05 seconds come from a resumed pipeline run on 27 October: discovery was skipped and the references step exited with code 1. This is **not a cold-start end-to-end benchmark**. There are no RAM samples, peak RAM or peak temporary-disk measurements. Missing measurements are shown as “Not measured”.
```

## 2. Scope

Audit baseline: [official Milestone 1 specification](https://hcmus-cs-ta.github.io/lab-book/intro-ds/statement/crawling/).

```{code-cell} python
:tags: [hide-input]
args = R.get("args") or {}
display(ru.kv_table([
    ("Prefix", args.get("prefix")),
    ("Start ID", args.get("start")),
    ("End ID", args.get("end")),
    ("IDs in the assigned range", ru.num(D.get("ids_in_range"), 0)),
    ("Papers found on arXiv", ru.num(D.get("papers_found"), 0)),
    ("IDs not found", ru.num(D.get("ids_not_found"), 0)),
    ("IDs that failed during discovery", ru.num(D.get("ids_failed_in_discovery"), 0)),
]))
```

## 3. Implementation

### 3.1 Pipeline

The crawler is a sequence of independent programs, run end to end by a driver script (`main.py`):

| Step | Program | What it does |
|---|---|---|
| `discover` | `discover.py` | Resolves the assigned IDs through the arXiv API, keeps the IDs that exist and reads the number of versions of each paper from the version suffix of the latest identifier. |
| `download` | `download_sources.py` | Downloads and extracts the source archive of **each version** individually. |
| `clean` | `process_sources.py` | Historical cleanup removed recognised binary figures while retaining other resources. Corrected tar/ZIP extraction admits only `.tex` and `.bib` before writing; original TeX bytes are preserved. LaTeX figure commands (`figure` environments, `\includegraphics`) stay untouched in the TeX files. |
| `metadata` | `metadata.py` | Writes publication-level `metadata.json`: title, authors, submission and revision dates. Corrected code preserves venue/journal references when supplied and writes actual versioned snapshots with explicit provenance; historical exports remain unchanged. |
| `references` | `references.py` | Writes `references.json` for each paper from the Semantic Scholar API. |

Every step skips the work it has already done, so an interrupted run is simply started again. The driver records
the duration of each step in `timings.json`, and a step that fails stops the run with a non-zero exit code.
The discovery step is skipped automatically when `discovery.json` is already complete for the requested range.

A version whose source is not TeX (PDF only, another format, or an archive without `.tex`) is **kept as an empty record** instead of being dropped,
so coverage statistics reflect reality. The download status of each version is stored in `download_status.json`.

### 3.2 Tools and libraries

- **arXiv API** through the `arxiv` Python client, using the modern `client.results(search)` style. The client enforces a delay of 3 seconds between calls,
  in line with the API etiquette, and requests go through one connection at a time with a descriptive `User-Agent`.
- **Semantic Scholar Graph API** through `requests`, with a free API key (read from the `S2_API_KEY` environment variable).
- **psutil** for the performance measurements (RAM sampling of the whole process tree).

### 3.3 Reference crawling

For every paper, the Semantic Scholar record is requested with the fields `paperId`, `title`, `authors`, `year`, `externalIds`, `publicationDate` and `venue` of each reference.

- Papers are queried in **batches** (the batch endpoint, 50 papers per request), which keeps the number of requests low and avoids rate limiting.
- A reference becomes a *row of the references table* only if `externalIds` contains an `ArXiv` key. Its identifier is normalised to the `yymm-id` form;
  old-style identifiers published before 2007 (for example `hep-th/9901001`) are kept as they are.
- The current code supports non-arXiv references by default, but this does not establish preservation in the existing corpus. Its resume logic skips completed reference files; see the read-only corpus audit below for actual retained rows.
- The **submission date** of a reference with an arXiv ID is read from the arXiv API (the date of version 1), in batches of 100 IDs with a persistent cache.
  If arXiv does not return the paper, the `publicationDate` of Semantic Scholar is used instead.
- HTTP 429 and server errors are retried with exponential backoff that honours the `Retry-After` header. An invalid API key (HTTP 401/403) stops the program with a clear message
  instead of marking every paper as failed.

### 3.4 Data organisation

One working folder per paper is created under `data/`:

```text
data/
|-- discovery.json            # resolved IDs and version lists
|-- download_status.json      # status of every version
|-- metadata_status.json
|-- references_status.json
|-- timings.json
`-- 2607-03694/               # one folder per publication
    |-- v1/, v2/, ...         # .tex and .bib files of each version
    |-- metadata.json
    `-- references.json
```

The folder layout above is supported by `download_sources.py` and the version-directory resolver in `parse.py`.

## 4. Results

The [official-requirements audit](crawling_stats.md) records unmet source-only extraction, venue and per-version provenance requirements. A single publication-level metadata/reference file is not evidence of a separate snapshot for every version. Non-arXiv reference preservation must be assessed from the retained data, not from the current crawler's defaults.

### 4.1 Overview

```{code-cell} python
:tags: [hide-input]
status_counts = D.get("versions_by_status") or {}
rows = [("Papers discovered", ru.num(D.get("papers_found"), 0)),
        ("Versions in total", ru.num(D.get("versions_total"), 0))]
rows += [(f"Versions with status `{k}`", ru.num(v, 0)) for k, v in status_counts.items()]
display(ru.kv_table(rows))
ru.bar(list(status_counts), {"Versions": list(status_counts.values())},
       "Versions by download status", "Number of versions", log_y=True)
```

Status meaning: `ok` – TeX sources were downloaded and kept; `pdf_only`, `other_format` and `no_tex` – the version has no TeX source and is stored as an empty record;
`error` – the download failed and will be retried by the next run.

```{code-cell} python
:tags: [hide-input]
vc = papers["versions"].value_counts().sort_index()
ru.bar(vc.index.tolist(), {"Papers": vc.values.tolist()}, "Number of versions per paper", "Number of papers", log_y=True)
```

### 4.2 Success rates

A paper counts as *scraped successfully* when no version failed to download, its metadata was written, and its references were crawled
(or Semantic Scholar has no record of it).

```{code-cell} python
:tags: [hide-input]
n = D.get("papers_found")
ok = D.get("papers_scraped_successfully")
display(ru.kv_table([
    ("Papers scraped successfully", f"{ru.num(ok, 0)} / {ru.num(n, 0)}"),
    ("Overall success rate", ru.pct(D.get("overall_success_rate"))),
    ("Download success rate (no failed version)", ru.pct(D.get("download_success_rate"))),
    ("Papers whose every version has TeX sources", ru.pct(D.get("tex_coverage_rate"))),
    ("Metadata success rate", ru.pct(D.get("metadata_success_rate"))),
    ("References success rate", ru.pct(D.get("references_success_rate"))),
    ("Papers without a Semantic Scholar record", ru.num(D.get("papers_without_s2_record"), 0)),
]))
```

### 4.3 Paper size before and after removing figures

The size of a paper is the total size of the extracted files of all its versions.

```{code-cell} python
:tags: [hide-input]
b, a = D.get("avg_paper_bytes_before_cleanup"), D.get("avg_paper_bytes_after_cleanup")
reduction = None if not b or a is None else 1 - a / b
display(ru.kv_table([
    ("Average paper size before removing figures (bytes)", ru.num(b, 0)),
    ("Average paper size after removing figures (bytes)", ru.num(a, 0)),
    ("Average paper size before / after (MiB)", f"{ru.num(ru.mb(b))} / {ru.num(ru.mb(a))}"),
    ("Size reduction", ru.pct(reduction)),
    ("Average version size before / after (bytes)",
     f"{ru.num(D.get('avg_version_bytes_before_cleanup'), 0)} / {ru.num(D.get('avg_version_bytes_after_cleanup'), 0)}"),
    ("Average compressed archive size per paper (bytes)", ru.num(D.get("avg_archive_bytes_per_paper"), 0)),
]))
ru.box(papers, {"bytes_before": "Before removing figures", "bytes_after": "After removing figures"},
       "Distribution of paper size", "Bytes (all versions of a paper)", log_y=True)
```

### 4.4 References

A reference's metadata is *complete* when it has a title, authors, a submission date and a Semantic Scholar ID.
The success rate is computed over the references that carry an arXiv ID, since only those become rows of the references table.

```{code-cell} python
:tags: [hide-input]
ref_status = D.get("references_by_status") or {}
rows = [
    ("Average references per paper (returned by Semantic Scholar)", ru.num(D.get("avg_refs_per_paper"))),
    ("Average references saved per paper", ru.num(D.get("avg_saved_refs_per_paper"))),
    ("Average references with an arXiv ID per paper", ru.num(D.get("avg_arxiv_refs_per_paper"))),
    ("Average per-paper success rate for reference metadata", ru.pct(D.get("avg_ref_metadata_success_rate_per_paper"))),
    ("Overall success rate for reference metadata", ru.pct(D.get("ref_metadata_success_rate_overall"))),
    ("References whose date came from Semantic Scholar", ru.num(D.get("refs_date_from_s2_total"), 0)),
]
rows += [(f"Papers with references status `{k}`", ru.num(v, 0)) for k, v in ref_status.items()]
display(ru.kv_table(rows))
ru.hist(papers["total_refs"], "References per paper", "Number of references", nbins=40)
rate = papers["refs_metadata_ok"] / papers["refs_with_arxiv_id"].where(papers["refs_with_arxiv_id"] > 0)
ru.hist(rate, "Per-paper success rate of reference metadata", "Success rate", nbins=20)
```

### 4.5 Error accounting and interpretation

Download errors are version-level outcomes, whereas the overall success rate is publication-level. Several errors may belong to one publication. PDF-only and no-TeX versions count as completed download attempts but do not provide parsable TeX. A missing Semantic Scholar record is an explicit completed lookup, **not** a paper with verified reference coverage. The 100% reference-metadata score applies only to saved arXiv-linked references and does not establish completeness of all bibliographies.

The saved average number of references is larger than the saved arXiv-linked subset. The current crawler can retain non-arXiv references too; the equality of saved-reference and arXiv-reference averages in this snapshot must not be interpreted as proof that every returned reference was retained.

## 5. Performance

### 5.1 Running time

```{code-cell} python
:tags: [hide-input]
steps = {k: v for k, v in (T.get("steps_seconds") or {}).items() if k != "discover"}
per_step = T.get("avg_seconds_per_paper_by_step") or {}
trial = T.get("single_paper_trial") or {}
display(ru.kv_table([
    ("Recorded resumed-run wall time (not cold-start)", ru.duration(T.get("wall_seconds"))),
    ("Resumed-run wall time / all discovered papers (not full processing time)", ru.quantity(T.get('avg_seconds_per_paper'), 's', 3)),
    ("Total time to process one paper end to end (single-paper trial)",
     f"{ru.num(trial.get('seconds'))} s" if trial else "not measured (benchmark.py --single-trial)"),
    ("Discovery in recorded run", "Skipped; original discovery time not measured"),
]))
display(pd.DataFrame({
    "Step": list(steps),
    "Total time (s)": [round(v, 1) for v in steps.values()],
    "Average per paper (s)": [ru.num(per_step.get(k), 4) for k in steps],
}))
ru.bar(list(steps), {"Total time (s)": list(steps.values())}, "Time spent in each step", "Seconds", log_y=True)
```

### 5.2 Memory and disk

The benchmark's `final_corpus_bytes` sums all files under discovered publication folders, including metadata, references and any other outputs present at export time; it is not a measurement restricted to `.tex` and `.bib`. Filesystem-wide peak extra usage, if sampled, would also differ from an absolute corpus peak. Here that peak was not measured.

RAM is the total memory of the whole process tree (the driver and every program it starts), sampled periodically.

```{code-cell} python
:tags: [hide-input]
display(ru.kv_table([
    (f"Peak RAM ({str(M.get('metric', '')).upper()}, MiB)", ru.num(ru.mb(M.get("peak_bytes")))),
    ("Average RAM (MiB)", ru.num(ru.mb(M.get("avg_bytes")))),
    ("Number of RAM samples", ru.num(M.get("samples"), 0)),
    ("Maximum extra disk usage during the run (MiB)", ru.num(ru.mb(K.get("peak_extra_bytes_during_run")))),
    ("Final corpus size (MiB)", ru.num(ru.mb(K.get("final_corpus_bytes")))),
    ("Size of the whole data/ folder (MiB)", ru.num(ru.mb(K.get("data_dir_bytes")))),
]))
ru.line(samples["seconds"], samples["ram_mb"], "RAM usage over time", "Elapsed time (s)", "RAM (MiB)")
if "disk_extra_mb" in samples:
    ru.line(samples["seconds"], samples["disk_extra_mb"], "Extra disk usage over time", "Elapsed time (s)", "Disk (MiB)")
```

### 5.3 Windows environment — not the required Colab testbed

The recorded Windows results do not satisfy the required final Google Colab CPU-only benchmark. Cold-start wall time, complete discovery time, peak/average RAM, a separately measured single-paper trial and peak required disk remain unavailable. [Colab benchmark protocol](colab_benchmarks.md) describes how to obtain new evidence without overwriting these exports.

```{code-cell} python
:tags: [hide-input]
display(ru.kv_table([
    ("Platform", R.get("platform")),
    ("Python", R.get("python")),
    ("CPU cores", R.get("cpu_count")),
    ("Total RAM (GiB)", ru.num(ru.scale(R.get("total_ram_bytes"), 1024 ** 3))),
    ("Measured at", R.get("created_at")),
    ("Pipeline finished successfully", R.get("pipeline_success")),
    ("Remaining errors", R.get("remaining_errors")),
]))
```

## 6. Summary

```{code-cell} python
:tags: [hide-input]
display(Markdown(f"""
- **{ru.num(D.get('papers_found'), 0)}** papers with **{ru.num(D.get('versions_total'), 0)}** versions were discovered in the assigned range;
  **{ru.num(D.get('papers_scraped_successfully'), 0)}** of them were scraped successfully (**{ru.pct(D.get('overall_success_rate'))}**).
- Removing figure binaries reduced the average paper size from **{ru.num(ru.mb(D.get('avg_paper_bytes_before_cleanup')))} MiB**
  to **{ru.num(ru.mb(D.get('avg_paper_bytes_after_cleanup')))} MiB**.
- A paper has on average **{ru.num(D.get('avg_refs_per_paper'))}** references, **{ru.num(D.get('avg_arxiv_refs_per_paper'))}** of which carry an arXiv ID;
  the metadata of **{ru.pct(D.get('ref_metadata_success_rate_overall'))}** of those references is complete.
- The recorded resumed run took **{ru.duration(T.get('wall_seconds'))}**; peak RAM: **{ru.quantity(ru.mb(M.get('peak_bytes')), 'MiB')}**,
  and the final corpus takes **{ru.num(ru.mb(K.get('final_corpus_bytes')))} MiB** on disk.
"""))
```
