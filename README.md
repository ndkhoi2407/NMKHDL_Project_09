# NMKHDL Project 09 — Source Code

HCMUS Introduction to Data Science project source repository.

## Environment

- Python 3.11 or later
- Install the crawler dependencies:

```powershell
py -3.11 -m pip install -r .\src\requirements.txt
```

## Tests

Run the offline test suite from the repository root:

```powershell
py -3.11 -m unittest discover -s .\tests -v
```

## Milestone 1 — Crawl assigned arXiv papers

The assigned range is `2607.13694` through `2607.18693` (5,000 base IDs).
Start with a small trial before processing the full range:

```powershell
py -3.11 .\src\crawler.py --max-papers 3 --phase discover --discovery-backend oai --output .\data
py -3.11 .\src\crawler.py --max-papers 3 --phase sources --output .\data
py -3.11 .\src\crawler.py --max-papers 3 --phase references --output .\data
py -3.11 .\src\status.py --max-papers 3 --output .\data
py -3.11 .\src\audit.py --max-papers 3 --output .\data
```

For the full range, run the phases sequentially, omitting `--max-papers`:

```powershell
py -3.11 .\src\crawler.py --phase discover --discovery-backend oai --output .\data
py -3.11 .\src\crawler.py --phase metadata --output .\data
py -3.11 .\src\crawler.py --phase sources --output .\data
py -3.11 .\src\crawler.py --phase references --output .\data
py -3.11 .\src\crawler.py --phase enrich-refs --enrich-backend oai --output .\data
```

The crawler saves checkpoints and can resume after interruption. Respect
arXiv and Semantic Scholar rate limits; a complete run can take many hours.
Do not commit downloaded data, API keys, or credentials.

## Milestone 2 — Parse the local corpus

Milestone 2 is offline and reads the Milestone 1 data directory without
rewriting it. Run a small trial first:

```powershell
py -3.11 -m src.milestone2.cli --output .\data --max-papers 20
```

To parse the full assigned range, omit `--max-papers`:

```powershell
py -3.11 -m src.milestone2.cli --output .\data
```

The parsed output is written to `data/milestone2/`. See
[MILESTONE1.md](./MILESTONE1.md) and [MILESTONE2.md](./MILESTONE2.md) for
methodology, outputs, limitations, and audit details.

## Report

The cumulative Milestone 1 and 2 report is maintained in a separate repository
and hosted on GitHub Pages:

- **Read the report:** https://thieuquang18.github.io/NMKHDL_report/
- **Report source (branch `24127114`):**
  https://github.com/thieuquang18/NMKHDL_report/tree/24127114

The report repository is separate from this shared source-code repository.
Submit both the source repository URL and the live report URL.
