# Milestones 1–2 report source

This folder contains the MyST/Jupyter Book source for the cumulative
Milestone 1 and Milestone 2 report, together with the aggregated data used by
its notebooks.

## Build locally

Install Python 3.11 or later and Node.js, then run from this folder:

```powershell
python -m pip install -r requirements.txt
npm install --global mystmd@1.12.0
myst build --html --execute --execute-parallel 1
```

The generated site is written to `_build/html/`. The notebooks read the
committed aggregate files under `report_data/`; the original crawl and parsed
corpora are not included.

## Published report

The canonical report source and GitHub Pages deployment remain in
[`NMKHDL_report`](https://github.com/thieuquang18/NMKHDL_report/tree/24127114).
The live book is at <https://thieuquang18.github.io/NMKHDL_report/>.
