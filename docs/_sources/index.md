# Milestone 1 — Crawling arXiv

**HCMUS · Introduction to Data Science**  
**Assigned range:** `2607.13694` to `2607.18693` (5,000 base identifiers, inclusive).

## Project scope

1. Resolve each assigned arXiv ID and enumerate all available versions.
2. Download every version-specific original source archive from arXiv and retain only `.tex` and `.bib`. Keep LaTeX figure commands, not the figure binaries.
3. Retrieve publication-level reference metadata from Semantic Scholar, retaining all references in the working dataset and exporting the arXiv-identified subset for the two required tables.
4. Measure crawl coverage, archive bytes before vs retained LaTeX bytes, reference coverage, time, RAM, and disk use.

The *actual* statistics, figures and tables below are generated during notebook compilation from exported local crawler logs. If data has not been synced yet, charts are omitted instead of presenting fabricated metrics.
## Source and reliability policy

- Atom API `id_list` can provide exact-version metadata, but it may return HTTP 429. OAI-PMH `arXivRaw` is used for targeted discovery and version dates when appropriate; it **does not provide historical titles/authors/abstracts for every revision**.
- Source downloads are version-specific. PDF-only and source-free submissions are counted explicitly, and must not be confused with network errors.
- Semantic Scholar provides references at **publication level**, not necessarily per version. A reference publication date from Semantic Scholar is **not** substituted for its first arXiv submission date.
- Failed requests remain retryable; a partial result is not described as 100% success.

**Official specification:** <https://hcmus-cs-ta.github.io/lab-book/intro-ds/statement/crawling/>
