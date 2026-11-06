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

# arXiv Corpus: Crawling and Parsing

**Introduction to Data Science · University of Science, VNU-HCM (HCMUS) · Group 09**

An auditable report on collecting versioned scientific sources and transforming LaTeX into reusable hierarchical data. The assigned range is `2608.19007–2608.24006`. Implementation descriptions are grounded in the included `src/` programs; every numerical result below comes from this project's small benchmark exports.

```{important}
Milestone 1 is a report-only corpus snapshot with timings from a resumed run; its peak RAM was not measured. Milestone 2 contains an instrumented parser run. “Not measured” is never replaced by zero. The site build reads only the small report exports and never starts a crawler or parser.
```

This book reports the work of our group on the arXiv project of the course *Introduction to Data Science*.
The project is built in stages, and each milestone has its own section:

- **[Milestone 1 — Crawling](m1_crawling.md)**: discovery of the assigned paper IDs, download of the LaTeX sources of every version,
  and crawling of the metadata and the references of each paper.
- **[Milestone 2 — Hierarchical Parsing and Standardization](m2_parsing.md)**: conversion of the LaTeX sources into a hierarchy of elements,
  cleanup and normalization, extraction of the references into BibTeX, and deduplication across versions.

All figures and tables in the book are generated while the book is compiled, from the result files in `m1_data/` and `m2_data/`.

## Headline numbers

```{code-cell} python
:tags: [hide-input]
import pandas as pd
from IPython.display import display
import report_utils as ru
import os
from pathlib import Path

data_dir = Path.cwd().parent / 'khoi'
os.chdir(data_dir)

m1 = ru.load_json("m1_data/summary.json")
m2 = ru.load_json("m2_data/summary.json")
d1, d2 = m1.get("data") or {}, m2.get("data") or {}
g = ru.get

display(pd.DataFrame([
    ("Papers", ru.num(d1.get("papers_found"), 0), ru.num(d2.get("papers_total"), 0)),
    ("Versions", ru.num(d1.get("versions_total"), 0), ru.num(d2.get("versions_total"), 0)),
    ("M1 scrape success / M2 publication job completion", ru.pct(d1.get("overall_success_rate")), ru.pct(d2.get("paper_success_rate"))),
    ("Version parsing success (parsed / parsed + failed)", "Not applicable", ru.pct(d2.get("version_parse_success_rate"))),
    ("Recorded wall time (M1 resumed; M2 measured)", ru.duration(g(m1, "timing", "wall_seconds")), ru.duration(g(m2, "timing", "wall_seconds"))),
    ("Peak RAM (MiB)", ru.num(ru.mb(g(m1, "memory", "peak_bytes"))), ru.num(ru.mb(g(m2, "memory", "peak_bytes")))),
    ("Stored corpus / parsed JSON size (MiB)", ru.num(ru.mb(g(m1, "disk", "final_corpus_bytes"))), ru.num(ru.mb(g(m2, "output", "parsed_json_bytes")))),
], columns=["", "Milestone 1 (crawling)", "Milestone 2 (parsing)"]))
```

## Reading the evidence

The milestone chapters explain methods, coverage and limitations. [Evidence audit](crawling_stats.md) reconciles aggregate statistics with per-publication records and shows the provenance of every input. Charts support hover and zoom; code can be expanded for inspection. Sizes labelled MiB use 1,048,576 bytes.

## Reproducing the results

The included `src/benchmark.py` and `src/benchmark_parse.py` define the measurements. `src/make_report_data.py` exports the small report inputs from existing local results. Those exports are retained unchanged for this report. The repository README documents a Python virtual environment, MyST execution and GitHub Pages deployment. No API keys or raw corpus are needed to rebuild the book.

The [official M1 requirements](https://hcmus-cs-ta.github.io/lab-book/intro-ds/statement/crawling/) and [official M2 requirements](https://hcmus-cs-ta.github.io/lab-book/intro-ds/statement/parsing/) are the audit baseline. [Evidence audit](crawling_stats.md) documents gaps, and the [Colab protocol](colab_benchmarks.md) separates required future CPU-only measurements from existing Windows measurements.
