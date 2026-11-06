# NMKHDL_Project_09
Introduction to Data Science Project

## Environment

- Python 3.14
- Install the required dependencies:

```powershell
py -3.14 -m pip install -r .\src\requirements.txt
```

## Milestone 1 — Data Crawling

Collect 5,000 assigned arXiv publications, including source files, metadata, and bibliographic references.

```powershell
python .\src\main.py --prefix 2608 --start 24007 --end 29006
```

The crawler performs publication discovery, source downloading, source processing, metadata collection, and reference retrieval. Checkpoints are used to preserve progress, while exponential backoff helps handle API rate limits.

## Milestone 2 — Hierarchical Parsing and Standardization

Parse the collected LaTeX corpus, extract document elements, reconstruct document hierarchies, normalize content, deduplicate elements across versions, and standardize bibliography records.

Run the M2 benchmark:

```powershell
python .\src\m2_benchmark.py --data .\data --output .\m2_benchmark_output --discovery .\data\discovery.json
```

## Project Reports

- **GitHub Report Repository:**  
  https://github.com/khoabautroi/NMKHDL_G09_report

- **GitHub Pages — Online Reports:**  
  https://khoabautroi.github.io/NMKHDL_G09_report/
