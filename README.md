# NMKHDL_Project_09 — Group 9

Combined Jupyter Book for the HCMUS Introduction to Data Science arXiv project.
The two original reports are kept in separate chapters, with their report
content and supporting aggregate data preserved.

**Published Jupyter Book:** [ndkhoi2407.github.io/NMKHDL_Project_09](https://ndkhoi2407.github.io/NMKHDL_Project_09/)

**Group repository:** [github.com/ndkhoi2407/NMKHDL_Project_09](https://github.com/ndkhoi2407/NMKHDL_Project_09)

## Group members

| Student ID | Name |
|---|---|
| 24127061 | Ngô Trần Anh Khoa |
| 24127065 | Nguyễn Đăng Khôi |
| 24127114 | Thiếu Quang |
| 24127121 | Nguyễn Tiến Thành |

## Build locally

Use Node.js 22 or newer and Python 3.11, then install MyST and the report
dependencies:

```powershell
npm install --global mystmd@1.12.0
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
myst build --html --execute --execute-parallel 1 --strict
```

The generated site is in `_build/html/`. The build executes the included
notebooks and report code cells using only the committed report data; it does
not run the crawler or download the full arXiv corpus.

## GitHub Pages

The `pages.yml` workflow builds and deploys the book when `main` is updated.
Set GitHub Pages to use **GitHub Actions** in the repository settings.
