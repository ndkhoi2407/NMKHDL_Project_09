# arXiv Milestone 1

## 1. Project Overview

This project implements Milestone 1 of an arXiv paper crawling and dataset construction pipeline.

The system discovers arXiv papers within a specified ID range, downloads all available versions of their source files, preserves the original LaTeX structure, removes binary image files, collects metadata, retrieves references from Semantic Scholar, and generates statistics for evaluating the resulting corpus.

## 2. Main Objectives

The pipeline performs the following tasks:

- Discover all arXiv papers in a specified ID range.
- Identify all available versions of each paper.
- Download the source files for each version.
- Preserve the original LaTeX directory and file structure.
- Remove binary image files while preserving LaTeX image references/commands.
- Collect paper metadata.
- Retrieve reference information using Semantic Scholar.
- Record crawling status and errors.
- Generate corpus statistics and benchmark information.

## 3. Project Structure

```text
arxiv-milestone1/
├── data/
│   ├── <paper-id>/
│   │   ├── v1/
│   │   ├── v2/
│   │   ├── ...
│   │   ├── metadata.json
│   │   └── references.json
│   ├── discovery.json
│   ├── download_status.json
│   ├── metadata_status.json
│   ├── references_status.json
│   ├── timings.json
│   └── benchmark/
│
├── src/
│   ├── discover.py
│   ├── download_sources.py
│   ├── process_sources.py
│   ├── metadata.py
│   ├── references.py
│   ├── benchmark.py
│   ├── main.py
│   └── requirements.txt
│
├── README.md
└── .gitignore
```

## 4. Requirements

- Python 3.14+
- Internet connection
- Semantic Scholar API key for reference retrieval

Required Python packages are listed in:

```text
src/requirements.txt
```

Install them with:

```powershell
pip install -r src/requirements.txt
```

## 5. Configuration

The reference retrieval module uses the Semantic Scholar API.

Set the API key as an environment variable before running the reference step.

### PowerShell

```powershell
$env:S2_API_KEY="YOUR_API_KEY"
```

The API key is read from the environment and is not stored in the project source code.

## 6. Running the Pipeline

The complete pipeline can be executed through `main.py`.

Example:

```powershell
python src/main.py --prefix 2608 --start 24007 --end 29006
```

The pipeline consists of the following stages:

1. Discovery
2. Source download
3. Source processing
4. Metadata collection
5. Reference retrieval

Individual stages can also be executed separately when necessary.

### Discovery

```powershell
python src/discover.py --prefix 2608 --start 24007 --end 29006 --fresh
```

### Source Download

```powershell
python src/download_sources.py
```

### Source Processing

```powershell
python src/process_sources.py
```

### Metadata

```powershell
python src/metadata.py
```

### References

```powershell
python src/references.py
```

## 7. Output Data

For each paper, the dataset contains its available versions together with metadata and references.

Example:

```text
data/
└── 2608-24007/
    ├── v1/
    │   ├── main.tex
    │   ├── *.tex
    │   ├── *.bib
    │   └── ...
    ├── v2/
    │   ├── main.tex
    │   ├── *.tex
    │   ├── *.bib
    │   └── ...
    ├── metadata.json
    └── references.json
```

The LaTeX directory structure is preserved. Binary image files are removed during source processing while LaTeX image commands are preserved.

## 8. Status and Log Files

The pipeline records its progress and results in JSON files:

- `discovery.json` — discovery results and ID-range statistics.
- `download_status.json` — source download status for each version.
- `metadata_status.json` — metadata retrieval status.
- `references_status.json` — Semantic Scholar reference retrieval status.
- `timings.json` — timing information from pipeline runs.

These files allow failed or incomplete operations to be identified without losing the entire crawl.

## 9. Benchmark

Benchmark information can be generated using:

```powershell
python src/benchmark.py --report-only
```

The report-only mode calculates statistics from the existing corpus without downloading the dataset again.

Benchmark output is stored in:

```text
data/benchmark/
├── summary.json
├── samples.csv
└── papers.csv
```

## 10. Current Dataset Statistics

The completed corpus currently contains:

| Metric | Result |
|---|---:|
| IDs in range | 5,000 |
| Papers found | 5,000 |
| Versions | 6,037 |
| Versions downloaded | 5,734 |
| PDF-only versions | 284 |
| Withdrawn/404 versions | 19 |
| Fully processed papers | 4,981 |
| Overall success rate | 99.62% |
| TeX coverage | 94.76% |
| Metadata success rate | 100% |
| Reference retrieval success rate | 100% |
| Papers without Semantic Scholar record | 8 |
| Average references per paper | 32.75 |
| Final corpus size | ~1.70 GiB |

The 19 HTTP 404 version errors correspond to withdrawn versions and are therefore treated as unavailable versions rather than crawler failures.

Eight papers do not have a corresponding Semantic Scholar record. Their `references.json` files are represented as empty JSON objects (`{}`).

## 11. Source Size Reduction

Binary image removal substantially reduces the storage size of the corpus while preserving the LaTeX source structure.

Average paper size:

```text
Before cleanup: 4,793,247 bytes
After cleanup:    376,111 bytes
```

This corresponds to a substantial reduction in average storage size while retaining the textual LaTeX source.

## 12. Reproducibility

To reproduce the experiment:

1. Create and activate a Python virtual environment.
2. Install the dependencies from `src/requirements.txt`.
3. Configure the Semantic Scholar API key.
4. Run the discovery stage for the required ID range.
5. Run the source download stage.
6. Process downloaded sources.
7. Retrieve metadata.
8. Retrieve references.
9. Generate benchmark statistics.

The generated status files can be used to inspect successful, failed, and unavailable records.

## 13. Notes

The full-scale crawl was performed on the target ID range:

```text
2608.24007 – 2608.29006
```

The final corpus contains all 5,000 IDs in the requested range.

End-to-end runtime and peak RAM for the original full-scale run were not recorded reliably and are therefore not reported as measured benchmark values.