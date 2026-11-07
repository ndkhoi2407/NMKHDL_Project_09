# NMKHDL_Project_09 — Group 9

Combined Jupyter Book and source repository for the HCMUS Introduction to Data Science arXiv project.
All members' reports are organized in separate directories, with their report content, notebooks, supporting aggregate data, and pipeline source code preserved.

**Published Jupyter Book:** [ndkhoi2407.github.io/NMKHDL_Project_09](https://ndkhoi2407.github.io/NMKHDL_Project_09/)

**Group repository:** [github.com/ndkhoi2407/NMKHDL_Project_09](https://github.com/ndkhoi2407/NMKHDL_Project_09)

## Group members

| Student ID | Name | Role / Scope |
|---|---|---|
| 24127061 | Ngô Trần Anh Khoa | Member |
| 24127065 | Nguyễn Đăng Khôi | Representative |
| 24127114 | Thiều Quang | Member |
| 24127121 | Nguyễn Tiến Thành | Member |

## Repository Structure

- `thieuquang_24127114/`: Thiều Quang (`24127114`) — Milestones 1–3 reports (`milestone1.ipynb`, `milestone2.ipynb`, `milestone3.ipynb`), aggregated report data, offline test suite (`tests/`), and full pipeline source code (`src/`).
- `nguyen_tien_thanh/`: Nguyễn Tiến Thành (`24127121`) — arXiv Corpus reports, notebooks, scripts, and source code.
- `khoi/`: Nguyễn Đăng Khôi (`24127065`) — Milestone 1 & 2 reports and data.
- `ngo_tran_anh_khoa/`: Ngô Trần Anh Khoa (`24127061`) — Milestone 1 & 2 reports.

Individual branches:
- Branch `24127114`: Dedicated branch hosting Thiều Quang's full standalone pipeline source code (`src/` covering M1 crawling, M2 hierarchical parsing, M3 reference matching & export), 28 offline tests (`tests/`), complete Jupyter Book report repository (`report_repo/`), and comprehensive instructions in `README.md`.

## Build locally

Use Node.js 22 or newer and Python 3.11, then install MyST and the report dependencies:

```powershell
npm install --global mystmd@1.12.0
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
myst build --html --execute --execute-parallel 1 --strict
```

The generated site is in `_build/html/`. The build executes the included notebooks and report code cells using only the committed report data; it does not run the crawler or download the full arXiv corpus.

## GitHub Pages

The `pages.yml` workflow builds and deploys the book when `main` is updated.
Set GitHub Pages to use **GitHub Actions** in the repository settings.
