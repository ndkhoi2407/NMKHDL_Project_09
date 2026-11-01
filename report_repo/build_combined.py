#!/usr/bin/env python3
"""Build cumulative Mile 1 + Mile 2 Jupyter Book without modifying Mile 1 files.

Original index.md, milestone1.ipynb, _toc.yml, _config.yml remain byte-for-byte intact.
The expanded table of contents exists only in a disposable staging directory.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--output', default='_build_combined', help='new output folder')
    args = p.parse_args()
    base = Path(__file__).resolve().parent
    out = (base / args.output).resolve()
    if out == base or base in out.parents and out.name == '_build':
        p.error('Do not overwrite the existing Milestone 1 build directory')
    with tempfile.TemporaryDirectory(prefix='milestone1and2_') as d:
        stage = Path(d) / 'report'
        shutil.copytree(base, stage, ignore=shutil.ignore_patterns(
            '.git', '_build', '_build_combined', '__pycache__', '.ipynb_checkpoints'))
        # This is staged only; the original _toc.yml never changes.
        (stage / '_toc.yml').write_text(
            'format: jb-book\nroot: index\nchapters:\n'
            '  - file: milestone1\n  - file: milestone2\n', encoding='utf-8')
        subprocess.run([
            sys.executable,
            '-c',
            'from jupyter_book.cli.main import main; main()',
            'build',
            str(stage)
        ], check=True)
        html = stage / '_build' / 'html'
        if out.exists():
            shutil.rmtree(out)
        shutil.copytree(html, out)
    print('Combined Mile 1+2 Jupyter Book:', out / 'index.html')

if __name__ == '__main__':
    main()
