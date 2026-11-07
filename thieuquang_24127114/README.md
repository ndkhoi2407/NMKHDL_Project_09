# NMKHDL GROUP 09 — End-to-End Pipeline & Source Code (Milestones 1, 2 & 3)

**HCMUS — Introduction to Data Science | Group 09**  
**Contributor:** Thiều Quang (`24127114`)  
**Assigned corpus range:** `2607.13694` through `2607.18693` (5,000 publications).  
**Group repository:** [ndkhoi2407/NMKHDL_Project_09](https://github.com/ndkhoi2407/NMKHDL_Project_09)  
**Published Jupyter Book:** [ndkhoi2407.github.io/NMKHDL_Project_09](https://ndkhoi2407.github.io/NMKHDL_Project_09/)  
**Individual report:** [thieuquang18.github.io/NMKHDL_report](https://thieuquang18.github.io/NMKHDL_report/)

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

### Overall Pipeline Results

| Component | Scope / Assigned Metric | Recorded Result |
|---|---|---|
| **Milestone 1 — Crawling** | Assigned publications | **5,000** |
| | Total publication versions | **6,417** |
| | Crawled references (S2) | **80,752** |
| **Milestone 2 — Parsing** | Parsed versions | **6,105** (312 empty-source accounted for) |
| | Standardized & deduplicated BibTeX | **383,892** |
| **Milestone 3 — Matching** | Human-reviewed manual labels | **100/100** (41 `matched`, 59 `none`) |
| | Weak automatic pseudo-labels | **23,958** across 500 publications |
| | Evaluation metric (MRR@5) | **Manual Test = 0.4500** (9/20 ranked #1, 11 `none`) |
| | Top-5 predictions generated | **24,058 rows** (for 505 sampled papers) |
| | Six-table Parquet bundle | Generated for `papers`, `references`, `elements`, `hierarchy`, `bibtex`, `predictions` |

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

### Milestone 3 — Reference Matching & Evaluation

Milestone 3 matches standardized BibTeX entries to arXiv references from the *same publication*.

```powershell
# 1. Prepare candidates and unreviewed CSV (5 papers per member * K members)
py -3.11 -m src.milestone3.cli prepare --root . --output .\data\milestone3 --members 1

# 2. Train supervised ranker (StandardScaler + LogisticRegression) using reviewed manual labels
py -3.11 -m src.milestone3.cli train --root . --output .\data\milestone3 --members 1

# 3. Export 6-table Parquet bundle (requires pyarrow)
py -3.11 -m src.milestone3.export --root . `
    --output .\data\milestone3\huggingface_dataset `
    --predictions .\data\milestone3\predictions.jsonl `
    --min-id 2607.13694 --max-id 2607.18693
```

#### Evaluation Metric (MRR@5)

$$
\operatorname{MRR@5}=\frac{1}{|Q|}\sum_{i=1}^{|Q|}\mathrm{RR@5}_i,
\qquad
\mathrm{RR@5}_i=\begin{cases}
1/r_i,&1\leq r_i\leq5,\\
0,&\text{otherwise.}
\end{cases}
$$

| Split | Label source | Publications | Entries | MRR@5 |
|---|---|---|---|---|
| Train | Manual | 3 | 60 | **0.5333** |
| Train | Automatic (weak) | 498 | 23,862 | **0.2973** |
| Validation | Manual (`2607.14503`) | 1 | 20 | **0.0000** (all 20 citations were `none`) |
| Validation | Automatic (weak) | 1 | 13 | **0.3846** |
| Test | Manual (`2607.17851`) | 1 | 20 | **0.4500** (9/9 matched ranked #1; 11 `none`) |
| Test | Automatic (weak) | 1 | 83 | **0.0843** (7/7 matched ranked #1) |

See [MILESTONE3.md](./MILESTONE3.md) for 10-feature definitions and training details.

---

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
