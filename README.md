# NMKHDL GROUP 09 — Milestone 1: arXiv Crawling

## 1. Project Overview

This project implements Milestone 1 of the HCMUS Introduction to Data Science project.

The objective is to construct a local dataset of arXiv research papers within the assigned ID range. The pipeline discovers available papers, retrieves their metadata and source files, collects reference information, and records crawling status for subsequent analysis and processing.

The collected corpus is also used as the input dataset for Milestone 2.

## 2. Main Objectives

The Milestone 1 pipeline performs the following tasks:

- Discover arXiv papers within the assigned ID range.
- Identify available papers and their metadata.
- Retrieve source files for available papers and versions.
- Preserve downloaded LaTeX source files and their directory structure.
- Process and organize the downloaded source data.
- Retrieve reference information using Semantic Scholar where available.
- Record crawling status, errors, and checkpoints.
- Generate statistics and benchmark information for evaluating the collected dataset.

## 3. Project Structure

```text
NMKHDL_Project_09/
├── data/                       # Local working data; not committed to Git
│   ├── 2607-03694/
│   │   ├── v1/
│   │   ├── v2/
│   │   ├── ...
│   │   ├── metadata.json
│   │   ├── parsed.json
│   │   └── references.json
│   ├── discovery.json
│   ├── download_status.json
│   ├── metadata_status.json
│   ├── references_status.json
│   ├── parse_status.json
│   ├── timings.json
│   ├── benchmark/
│   ├── benchmark_parse/
│   └── milestone2/
│
├── src/                        # Source code
│   ├── crawler.py
│   ├── status.py
│   ├── audit.py
│   ├── milestone2/
│   │   └── cli.py
│   └── requirements.txt
│
├── tests/                      # Offline test suite
├── MILESTONE1.md
├── MILESTONE2.md
├── README.md
└── .gitignore
```

The exact contents of the data directory depend on the crawling and parsing stages that have been completed.

## 4. Requirements

- Python 3.11 or later
- Internet connection for crawling and metadata/reference retrieval
- Semantic Scholar API key for reference retrieval, where required

Install the required Python packages from the repository root:

```powershell
py -3.11 -m pip install -r .\src\requirements.txt
```

## 5. Configuration

The reference retrieval stage may use the Semantic Scholar API.

If an API key is required, configure it as an environment variable in PowerShell:

```powershell
$env:S2_API_KEY="YOUR_API_KEY"
```

The API key should be stored in the environment rather than committed to the repository.

Do not commit API keys, credentials, or downloaded corpus data to Git.

## 6. Running the Pipeline

The assigned arXiv ID range is:

```text
Prefix: 2607
Start:  03694
End:    08693
Total:  5,000 base IDs
```

Start with a small trial before processing the full range.

### Small Trial

Run the following commands sequentially:

```powershell
py -3.11 .\src\crawler.py --max-papers 3 --phase discover --discovery-backend oai --output .\data

py -3.11 .\src\crawler.py --max-papers 3 --phase sources --output .\data

py -3.11 .\src\crawler.py --max-papers 3 --phase references --output .\data

py -3.11 .\src\status.py --max-papers 3 --output .\data

py -3.11 .\src\audit.py --max-papers 3 --output .\data
```

### Full Crawling Pipeline

For the complete assigned range, run the following stages sequentially, omitting `--max-papers`:

```powershell
py -3.11 .\src\crawler.py --phase discover --discovery-backend oai --output .\data

py -3.11 .\src\crawler.py --phase metadata --output .\data

py -3.11 .\src\crawler.py --phase sources --output .\data

py -3.11 .\src\crawler.py --phase references --output .\data

py -3.11 .\src\crawler.py --phase enrich-refs --enrich-backend oai --output .\data
```

The crawler saves checkpoints and can resume after interruption. Crawling should respect arXiv and Semantic Scholar rate limits.

A complete run may take several hours depending on network conditions and API response times.

## 7. Output Data

The collected dataset contains the available source files and associated information for each paper.

Example:

```text
data/
└── 2607-03694/
    ├── v1/
    │   ├── main.tex
    │   ├── references.bib
    │   └── ...
    ├── metadata.json
    ├── parsed.json
    └── references.json
```

The actual number of versions and files varies between papers.

The downloaded source files are preserved for subsequent processing and parsing in Milestone 2.

## 8. Status and Log Files

The pipeline records its progress and results in JSON files:

| File | Description |
|---|---|
| `discovery.json` | Records discovered papers and discovery information. |
| `download_status.json` | Records source download status. |
| `metadata_status.json` | Records metadata retrieval status. |
| `references_status.json` | Records reference retrieval status. |
| `parse_status.json` | Records parsing status for Milestone 2. |
| `timings.json` | Stores timing information from pipeline operations. |

These files allow incomplete operations and failed records to be identified without restarting the entire crawling process.

## 9. Benchmark

The project includes benchmark outputs for evaluating crawling and parsing performance.

The benchmark information can include:

- Total execution time.
- Average processing time per paper.
- Step-by-step execution time.
- Peak and average memory usage.
- Number of papers and versions processed.
- Download and processing results.
- Output data size.

Benchmark outputs are stored in:

```text
data/
├── benchmark/
│   ├── summary.json
│   ├── papers.csv
│   └── samples.csv
│
└── benchmark_parse/
    ├── summary.json
    ├── papers.csv
    └── samples.csv
```

The benchmark results are used to evaluate the performance of the crawling and parsing stages.

## 10. Current Dataset Statistics

The assigned dataset covers the following range:

| Metric | Result |
|---|---:|
| ID prefix | `2607` |
| Starting ID | `03694` |
| Ending ID | `08693` |
| IDs in assigned range | 5,000 |
| Sample paper directory | `2607-03694` |

The actual number of discovered papers, downloaded versions, successful operations, and other performance metrics should be taken from the generated benchmark and status files.

## 11. Source Data and Storage

The downloaded source corpus is stored locally under the `data/` directory.

The corpus contains the available versions of each paper and associated metadata and reference information.

The collected source data is used as the input for Milestone 2, where the local corpus is parsed and transformed into structured outputs.

The full dataset is not committed to Git because of its large storage requirements.

## 12. Reproducibility

To reproduce Milestone 1:

1. Clone the project repository.
2. Install Python 3.11 or later.
3. Install dependencies from `src/requirements.txt`.
4. Configure the Semantic Scholar API key if required.
5. Run the discovery stage for the assigned ID range.
6. Retrieve metadata and source files.
7. Retrieve reference information.
8. Inspect crawling status and audit results.
9. Generate or inspect benchmark statistics.

The status and checkpoint files help identify successful, failed, and incomplete operations.

## 13. Notes

The assigned arXiv ID range for this project is:

```text
2607.03694 – 2607.08693
```

This range contains 5,000 base IDs.

Milestone 1 constructs the local arXiv corpus, which serves as the input dataset for Milestone 2.

Milestone 2 performs offline parsing of the collected corpus and generates structured data for further analysis.

For additional methodology, implementation details, outputs, and limitations, see:

- [MILESTONE1.md](https://github.com/ndkhoi2407/NMKHDL_Project_09/blob/24127121/MILESTONE1.md)
- [MILESTONE2.md](https://github.com/ndkhoi2407/NMKHDL_Project_09/blob/24127121/MILESTONE2.md)
