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

**Full Name:** Nguyen Dang Khoi
**Student ID:** 24127065  
**Class:** 24KHDL1  
**Group:** 09  

---
# Milestone 2 — Hierarchical Parsing and Standardization

## 1. Objectives

Milestone 2 turns the raw LaTeX sources crawled in Milestone 1 into structured data:

- Gather the files that are really part of each compilation, version by version.
- Build a **hierarchical tree** of every version (document, sections, sentences, block formulas, figures, lists).
- **Standardize** the content: LaTeX cleanup and math normalization.
- Extract the **references** into BibTeX entries.
- **Deduplicate** reference entries and full-text content across the versions of a publication.
- Measure the success rate, running time, memory footprint and output size of the parser.

All numbers and figures on this page are generated while the book is compiled, from the small result files in `m2_data/`
(`summary.json`, `papers.csv`, `samples.csv`, `tables_stats.json`, `kind_counts.json`, `failures.json`, `example.json`).

```{code-cell} python
:tags: [hide-input]
import pandas as pd
from IPython.display import display, Markdown
import report_utils as ru

S = ru.load_json("m2_data/summary.json")
papers = ru.load_csv("m2_data/papers.csv")
samples = ru.load_csv("m2_data/samples.csv")
tables = ru.load_json("m2_data/tables_stats.json")
kinds = ru.load_json("m2_data/kind_counts.json")
failures = ru.load_json("m2_data/failures.json")
example = ru.load_json("m2_data/example.json")
R, T, M, O, D = (S.get(k) or {} for k in ("run", "timing", "memory", "output", "data"))
```

```{note}
The parser benchmark was measured on 2 November 2026 (`run.measured: true`). A publication with status `ok` means its processing job completed; individual versions can still be empty or failed. Publication completion and version parsing success use different denominators.
```

## 2. Implementation

Audit baseline: [official Milestone 2 specification](https://hcmus-cs-ta.github.io/lab-book/intro-ds/statement/parsing/).

### 2.1 Hierarchical parsing

**Multi-file gathering.** For every version, all `.tex` files are read and their comments are stripped first (an unescaped `%` starts a comment),
so a commented-out `\input` is treated as plain text and never followed. The publication root is the file that contains `\documentclass`
(and `\begin{document}`) and is not included by another file. `\input`, `\include` and `\subfile` are then expanded recursively, with a cycle and depth guard.
Every file that is not reachable from the root is a redundant auxiliary file and is ignored, so the parse follows the selected compilation tree. This heuristic does not guarantee equivalence to a compiled PDF: unresolved includes are omitted and author macros are not expanded.

**Hierarchy construction.** Inside `\begin{document}...\end{document}` a block scanner finds sectioning commands, environments and display math.
The sectioning commands that actually occur in a paper are ranked (`part < chapter < section < subsection < subsubsection < paragraph < subparagraph`)
and mapped to consecutive levels, so the level of every heading is detected automatically: a paper that only uses `\section` and `\subsubsection` gets two heading levels.
The abstract becomes an `Abstract` heading; unnumbered sections such as Acknowledgements and the appendices are kept;
the References section and the `thebibliography` environment are excluded.

**Leaf elements.** The leaves of the tree are:

- **sentences** – the prose of body text;
- **block formulas** – the contents of `equation`, `align`, `gather`, `multline`, `eqnarray`, `$$...$$` and `\[...\]`;
- **figures** – `figure` and `table` environments (a table is a kind of figure here) and stand-alone `tabular`, `algorithm` and similar floats.
  The LaTeX commands that define a figure (`\includegraphics`, `\caption`) are kept in the content.

`itemize`, `enumerate` and `description` become a `list` node whose `item` children contain their own sentences, formulas and figures; lists can be nested.

**Sentence splitting.** Text is split into paragraphs on blank lines and then into sentences at `.`, `?` or `!` followed by whitespace and a capital letter, a backslash, a dollar sign or a quote.
A dot never splits a sentence inside mathematics or inside command arguments (`\cite`, `\url`, `\footnote`), after common abbreviations (`e.g.`, `i.e.`, `Fig.`, `Eq.`, `et al.`),
after single-letter initials, or inside decimal numbers.

**Versions without TeX.** A version stored as an empty record by Milestone 1 (PDF only, other formats) is recorded with the status `empty` and produces no elements,
so the coverage statistics and the tables reflect reality.

### 2.2 Standardization

**Cleanup.** Formatting commands without semantic content are removed (`\centering`, `\midrule`, `\toprule`, `\hline`, `\vspace`, `\label`, font-size and font-style switches, …),
as is the float placement option such as `[htbp]`. Style wrappers such as `\textbf{x}` and `\emph{x}` are unwrapped in prose, and whitespace is normalized, so that
formatting differences do not make identical texts look different.

**Math normalization.** All inline mathematics (`\(...\)`, `$...$`) is written as `$...$`. All block mathematics (`$$...$$`, `\[...\]`, `equation`, `align`, `gather`, `multline`, `eqnarray`)
is written as `\begin{equation}...\end{equation}`; multi-line environments are wrapped in `aligned` or `gathered` inside it, so the result stays valid LaTeX. `\label` and `\nonumber` are dropped.

**Reference extraction.** Citations defined with `\bibitem` are converted to BibTeX entries with regular expressions: `\newblock` segments, a quoted title, or sentence splitting
give the authors, title and venue, while the DOI, URL and year are matched separately; the entry type is inferred from the venue. The `.bib` files referenced by
`\bibliography` are read by a small brace-aware parser. Each entry has a citation key, entry type, title, authors, year, DOI, journal and URL.

**Reference deduplication.** The entries of all versions of a publication (and the entries inside one version) are grouped with a union-find structure:
two entries are the same reference when they share a DOI, a normalized title, or a citation key with a compatible title.
One citation key is chosen for each group (the most frequent one, the newest version on ties), the `\cite{}` commands that use the dropped keys are renamed, and the fields of
the duplicates are **unionized by field**: the newest non-empty value wins, and missing fields fall back to older entries. This does not concatenate conflicting author lists. A non-`misc` entry type takes priority over `misc`, even from an older version. Long normalized titles match without a year constraint; short non-empty titles require a year. The historical extraction used `setdefault` and could discard later fields under the same key. The corrected `merge_bib_entry` combines non-empty fields before cross-version unionization and retains conflicting values in `bib_field_conflicts`. These code fixes have not been applied to the historical corpus exports.

**Full-text deduplication.** After the `\cite` renaming, the identity of an element is its kind together with its cleaned text. Elements that match exactly across versions share one
`element_id` in the `elements` table, and the `hierarchy` table holds one node-parent edge per version. Repeated identical text inside a single version gets distinct ids,
so every version stays a tree.

**Known limitations.** Macros defined by the authors are not expanded, the `\bibitem` conversion is heuristic, and the text that follows a `\paragraph{}` heading belongs to that heading.

### 2.3 Execution

Publications are processed in parallel by a pool of worker processes, with a configurable per-publication alarm on platforms supporting `SIGALRM`. This timeout is not enforced by that mechanism on Windows, where this benchmark was measured. The status of each publication is saved periodically, so an interrupted run
resumes where it stopped.

## 3. Output tables

| Table | Columns |
|---|---|
| `elements` | `element_id`, `arxiv_id`, `kind`, `content` |
| `hierarchy` | `arxiv_id`, `version`, `element_id`, `parent_id` |
| `bibtex` | `arxiv_id`, `citation_key`, `entry_type`, `title`, `authors`, `year`, `doi`, `journal`, `url` |

Element ids start with the publication key, followed by a discriminant that is unique inside the publication (for example `2310-12345#s1`).

```{code-cell} python
:tags: [hide-input]
display(pd.DataFrame([
    {"Table": name, "Rows": f"{v['rows']:,}", "Size on disk (MiB)": ru.num(ru.mb(v.get("bytes")))}
    for name, v in tables.items()
]))
ru.bar(list(kinds), {"Elements": list(kinds.values())}, "Elements by kind", "Number of elements", log_y=True)
```

### 3.1 A worked example

The element ids that appear in several versions are the result of full-text deduplication: one element row serves every version, while the hierarchy rows attach it to a parent of each version.

```{code-cell} python
:tags: [hide-input]
if example:
    print("Publication:", example["arxiv_id"])
    display(pd.DataFrame(example["elements"]))
    display(pd.DataFrame(example["hierarchy"]))
else:
    print("No publication with elements shared across versions was found.")
```

## 4. Statistics

### 4.1 Parsing success

The version parsing success rate is computed over the versions that have TeX sources (parsed plus failed); the version coverage also counts the empty versions.

```{code-cell} python
:tags: [hide-input]
display(ru.kv_table([
    ("Publications in the corpus", ru.num(D.get("papers_total"), 0)),
    ("Publications processed", ru.num(D.get("papers_processed"), 0)),
    ("Publications with an error", ru.num(D.get("papers_error"), 0)),
    ("Publications missing from the results", ru.num(D.get("papers_missing"), 0)),
    ("Publication job completion rate (ok + partial; not version success)", ru.pct(D.get("paper_success_rate"))),
    ("Versions in total", ru.num(D.get("versions_total"), 0)),
    ("Versions parsed", ru.num(D.get("versions_ok"), 0)),
    ("Empty versions (TeX unavailable, including missing downloads)", ru.num(D.get("versions_empty"), 0)),
    ("Failed versions", ru.num(D.get("versions_failed"), 0)),
    ("Parsing success rate (versions with TeX)", ru.pct(D.get("version_parse_success_rate"))),
    ("Version coverage (parsed / all versions)", ru.pct(D.get("version_coverage_overall"))),
    ("Average version coverage per publication", ru.pct(D.get("avg_version_coverage_per_paper"))),
]))
```

### 4.2 Version coverage of every publication

The coverage of a publication is the share of its versions that were parsed. [Download all per-publication coverage records](m2_data/papers.csv); this real export includes every publication, while the chart and lowest-coverage preview below summarise it.

```{code-cell} python
:tags: [hide-input]
cov = papers["version_coverage"].dropna()
ru.hist(cov, "Version coverage per publication", "Version coverage", "Number of publications", nbins=20)
buckets = pd.cut(cov, bins=[-0.001, 0, 0.5, 0.999999, 1.0],
                 labels=["0 (nothing parsed)", "(0, 0.5]", "(0.5, 1)", "1 (all versions parsed)"])
display(buckets.value_counts().sort_index().rename_axis("Coverage").reset_index(name="Publications"))
```

The publications with the lowest coverage:

```{code-cell} python
:tags: [hide-input]
cols = ["id", "versions", "versions_ok", "versions_empty", "versions_failed", "version_coverage"]
display(papers.dropna(subset=["version_coverage"]).sort_values("version_coverage").head(15)[cols])
```

### 4.3 Why versions are empty or fail

```{code-cell} python
:tags: [hide-input]
reasons = pd.DataFrame(failures.get("reasons") or [], columns=["status", "reason", "count"])
display(reasons.rename(columns={"status": "Status", "reason": "Reason", "count": "Versions"}))
if failures.get("failed_versions"):
    display(pd.DataFrame(failures["failed_versions"]))
else:
    print("No version failed to parse.")
```

### 4.4 Deduplication

```{code-cell} python
:tags: [hide-input]
eb, ea = D.get("elements_before_dedup"), D.get("elements_after_dedup")
bb, ba = D.get("bib_before_dedup"), D.get("bib_after_dedup")
display(pd.DataFrame({
    "": ["Elements (all versions)", "BibTeX entries"],
    "Before deduplication": [ru.num(eb, 0), ru.num(bb, 0)],
    "After deduplication": [ru.num(ea, 0), ru.num(ba, 0)],
    "Removed": [ru.num(ru.difference(eb, ea), 0), ru.num(ru.difference(bb, ba), 0)],
    "Reduction": [ru.pct(D.get("element_reduction")), ru.pct(D.get("bib_reduction"))],
}))
ru.bar(["Elements", "BibTeX entries"], {"Before deduplication": [eb, bb], "After deduplication": [ea, ba]},
       "Records before and after deduplication", "Number of records", log_y=True)
nonzero = papers[papers["elements_after_dedup"] > 0]
ru.box(nonzero, {"elements_before_dedup": "Before deduplication", "elements_after_dedup": "After deduplication"},
       "Elements per publication", "Number of elements", log_y=True)
```

## 5. Performance

### 5.1 Running time and memory 

The running time is the end-to-end wall time of the parser. The memory is the total RAM of the whole process tree (the main process and all its workers), sampled periodically.

```{code-cell} python
:tags: [hide-input]
display(ru.kv_table([
    ("End-to-end wall time", ru.duration(T.get("wall_seconds"))),
    ("Average time per publication (wall time / publications)", f"{ru.num(T.get('avg_seconds_per_paper'), 4)} s"),
    ("Average processing time per publication inside a worker", f"{ru.num(D.get('avg_seconds_per_paper_cpu'), 4)} s"),
    (f"Peak RAM ({str(M.get('metric', '')).upper()}, MiB)", ru.num(ru.mb(M.get("peak_bytes")))),
    ("Average RAM (MiB)", ru.num(ru.mb(M.get("avg_bytes")))),
    ("Number of RAM samples", ru.num(M.get("samples"), 0)),
]))
ru.hist(papers["seconds"], "Processing time per publication", "Seconds", "Number of publications", nbins=40)
ru.line(samples["seconds"], samples["ram_mb"], "RAM usage over time", "Elapsed time (s)", "RAM (MiB)")
```

### 5.2 Output size

```{code-cell} python
:tags: [hide-input]
display(ru.kv_table([
    ("Size of all parsed.json files (MiB)", ru.num(ru.mb(O.get("parsed_json_bytes")))),
    ("Size of the merged tables (MiB)", ru.num(ru.mb(O.get("tables_jsonl_bytes")))),
    ("Average output per publication (KiB)", ru.num(ru.scale(O.get("avg_bytes_per_paper"), 1024))),
]))
```

### 5.3 Windows environment — not the required Colab testbed

The current measured run is Windows-only. No Google Colab CPU-only parser runtime, peak RAM or final storage measurement has been collected. [Colab benchmark protocol](colab_benchmarks.md) keeps those future runs separate.

```{code-cell} python
:tags: [hide-input]
display(ru.kv_table([
    ("Platform", R.get("platform")),
    ("Python", R.get("python")),
    ("CPU cores", R.get("cpu_count")),
    ("Measured at", R.get("created_at")),
    ("Measured run (not report-only)", R.get("measured")),
]))
```

### 5.4 Interpreting the measurements

The worker-time column is elapsed time inside a worker, despite the summary field name `avg_seconds_per_paper_cpu`; it is not an operating-system CPU-time measurement. Parallel workers make its average different from wall time divided by publication count. Summed process-tree RSS may count shared memory more than once. Samples are taken periodically, so short-lived peaks may be missed.

Per-publication `parsed.json` files and merged JSONL tables are alternative representations of the same results. Their sizes are reported separately; neither is the size of the original downloaded corpus. The 331 empty versions include 17 missing source directories, not only PDF-only papers. The two `no_root_file` failures remain visible above. Exact-text deduplication does not detect paraphrases or semantic equivalence; bibliography merging remains heuristic.

The benchmark invokes `parse.py` without `--export`, so merged-table generation is not included in its wall time. The reported merged-table sizes describe existing artifacts; the summary alone does not establish when those tables were regenerated. Root-cause inspection of the two failures and executable checks of deduplication are in the [evidence audit](crawling_stats.md). These checks do not change historical results or prove every parsed sentence correct.

## 6. Summary

```{code-cell} python
:tags: [hide-input]
display(Markdown(f"""
- **{ru.num(D.get('papers_processed'), 0)}** of **{ru.num(D.get('papers_total'), 0)}** publications were processed
  (**{ru.num(D.get('papers_error'), 0)}** errors, **{ru.num(D.get('papers_missing'), 0)}** missing).
- Of **{ru.num(D.get('versions_total'), 0)}** versions, **{ru.num(D.get('versions_ok'), 0)}** were parsed,
  **{ru.num(D.get('versions_empty'), 0)}** are empty (TeX unavailable) and **{ru.num(D.get('versions_failed'), 0)}** failed;
  the parsing success rate over versions with TeX is **{ru.pct(D.get('version_parse_success_rate'))}**.
- Deduplication reduced the elements from **{ru.num(D.get('elements_before_dedup'), 0)}** to **{ru.num(D.get('elements_after_dedup'), 0)}**
  (**{ru.pct(D.get('element_reduction'))}** fewer) and the BibTeX entries from **{ru.num(D.get('bib_before_dedup'), 0)}**
  to **{ru.num(D.get('bib_after_dedup'), 0)}** (**{ru.pct(D.get('bib_reduction'))}** fewer).
- The parser ran in **{ru.duration(T.get('wall_seconds'))}**, with a peak RAM of **{ru.num(ru.mb(M.get('peak_bytes')))} MiB**,
  and its output takes **{ru.num(ru.mb(O.get('parsed_json_bytes')))} MiB**.
"""))
```
