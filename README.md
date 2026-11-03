# NMKHDL_Project_09
Introduction to Data Science Project 

## Environment

- Python 3.14
- Install the crawler dependencies:

```powershell
py -3.14 -m pip install -r .\src\requirements.txt
```

## Milestone 1 — Crawl assigned arXiv papers
The assigned range is `2607.19007` through `2607.24006` (5,000 base IDs).

```powershell
python .\src\main.py --prefix 2608 --start 19007 --end 24006
```
When running this command, main.py will sequentially run discovery.py, download_sources.py, process_sources.py, metadata.py, references.py.
The crawler saves checkpoint during each run so that the progress is saved after a reset.
When fetching references using Schematic Scholar API, exponential backoff is applied to respect the API's rate limit

## Milestone 2 — Parse the local corpus

