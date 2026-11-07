# NMKHDL GROUP 09  (Milestones 1, 2 & 3)

**HCMUS — Introduction to Data Science | Group 09**  
**Group repository:** [ndkhoi2407/NMKHDL_Project_09](https://github.com/ndkhoi2407/NMKHDL_Project_09)  
**Published Jupyter Book:** [ndkhoi2407.github.io/NMKHDL_Project_09](https://ndkhoi2407.github.io/NMKHDL_Project_09/)  

---

## 1. Pipeline Overview

```text
Assigned arXiv IDs (2607.13694 – 2607.18693)
    │
    ▼
Milestone 1: Crawl metadata, all versions, LaTeX/BibTeX source archives, S2 references
    │
    ▼
Milestone 2: Recover document hierarchy, parse compilation path, standardize & dedup BibTeX
    │
    ▼
Milestone 3: Publication-scoped candidate ranking & citation-to-reference matching
    │
    ▼
Train / Valid / Test -> Top-5 Predictions -> MRR@5 Evaluation -> Sharded Parquet Export
```


---

## 2. Environment & Installation

Python 3.11+ is recommended. Install all dependencies for the crawler, parser, matcher, and test suite:

```powershell
# Core crawler and parser dependencies
py -3.11 -m pip install -r .\src\requirements.txt

# Milestone 3 matching, ranking and export dependencies
py -3.11 -m pip install -r .\src\milestone3\requirements.txt
```

---

## 3. Running the Test Suite

Run the full offline test suite (28 integration and unit tests covering Milestones 1, 2, and 3):

```powershell
py -3.11 -m unittest discover -s .\tests -v
```

---

## 4. Pipeline Execution Guide

### Milestone 1 — Crawling Assigned arXiv Papers

The assigned range is `2607.13694` to `2607.18693`. To test with a trial run:

```powershell
py -3.11 .\src\crawler.py --max-papers 3 --phase discover --discovery-backend oai --output .\data
py -3.11 .\src\crawler.py --max-papers 3 --phase sources --output .\data
py -3.11 .\src\crawler.py --max-papers 3 --phase references --output .\data
py -3.11 .\src\status.py --max-papers 3 --output .\data
py -3.11 .\src\audit.py --max-papers 3 --output .\data
```

For the complete range, run all phases sequentially:

```powershell
py -3.11 .\src\crawler.py --phase discover --discovery-backend oai --output .\data
py -3.11 .\src\crawler.py --phase metadata --output .\data
py -3.11 .\src\crawler.py --phase sources --output .\data
py -3.11 .\src\crawler.py --phase references --output .\data
py -3.11 .\src\crawler.py --phase enrich-refs --enrich-backend oai --output .\data
```

See [MILESTONE1.md](./MILESTONE1.md) for detailed crawling methodology and rate-limiting safeguards.

### Milestone 2 — Hierarchical Parsing & Standardization

Milestone 2 operates completely offline and reads the Milestone 1 data directory without mutating raw records.

```powershell
# Small trial run (20 papers)
py -3.11 -m src.milestone2.cli --output .\data --max-papers 20

# Full assigned range
py -3.11 -m src.milestone2.cli --output .\data
```

Outputs are written to `data/milestone2/tables/` (`elements.jsonl`, `hierarchy.jsonl`, `bibtex.jsonl`). See [MILESTONE2.md](./MILESTONE2.md) for hierarchy parsing and citation normalization details.


## 5. Jupyter Book Reports

The MyST/Jupyter Book report files and aggregate logging data are included in [`report_repo/`](./report_repo/):

```powershell
cd report_repo
npm install --global mystmd@1.12.0
py -3.11 -m pip install -r requirements.txt
myst build --html --execute --execute-parallel 1
```

The compiled site renders all 3 milestones (`milestone1.ipynb`, `milestone2.ipynb`, `milestone3.ipynb`) and is deployed to GitHub Pages automatically via `.github/workflows/pages.yml`.

---

## 6. Repository Layout

```text
├── src/
│   ├── crawler.py                  # Milestone 1: crawling pipeline
│   ├── metadata.py                 # OAI/Atom metadata extraction
│   ├── download_sources.py         # Source tarball fetching & filtering
│   ├── references.py               # Semantic Scholar reference extraction
│   ├── audit.py / status.py        # Checkpointing, integrity & progress
│   ├── milestone2/                 # Milestone 2: parsing & deduplication
│   │   ├── latex.py                # TeX AST, hierarchy & sentence extraction
│   │   ├── bibliography.py         # BibTeX normalization & union
│   │   └── pipeline.py             # Pipeline runner
│   └── milestone3/                 # Milestone 3: reference matching
│       ├── matching.py             # 10 candidate features & heuristic scoring
│       ├── cli.py                  # prepare, train, evaluate (MRR@5)
│       ├── export.py               # 6-table Parquet exporter
│       └── publish.py              # HF dataset publisher
├── tests/                          # 28 offline unit & integration tests
├── report_repo/                    # Jupyter Book report source & data
│   ├── index.md                    # Landing page
│   ├── milestone1.ipynb            # Milestone 1 report
│   ├── milestone2.ipynb            # Milestone 2 report
│   ├── milestone3.ipynb            # Milestone 3 report (with MRR@5 equation)
│   ├── report_data/                # Aggregated summary & benchmark data
│   └── myst.yml                    # MyST configuration
├── MILESTONE1.md                   # Milestone 1 specification & audit notes
├── MILESTONE2.md                   # Milestone 2 specification & audit notes
├── MILESTONE3.md                   # Milestone 3 specification & audit notes
└── README.md                       # This comprehensive documentation
```

---

## 7. Official Course Specifications

- [Milestone 1 — Data Crawling](https://hcmus-cs-ta.github.io/lab-book/intro-ds/statement/crawling/)
- [Milestone 2 — Hierarchical Parsing and Standardization](https://hcmus-cs-ta.github.io/lab-book/intro-ds/statement/parsing/)
- [Milestone 3 — Reference Matching](https://hcmus-cs-ta.github.io/lab-book/intro-ds/statement/matching/)
- [Project Statement & Submission Guidelines](https://hcmus-cs-ta.github.io/lab-book/intro-ds/statement/)
