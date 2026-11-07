#!/usr/bin/env python3
"""OPTIONAL preview of all 3 milestones; never modifies original Book files.

The official required report for Miles 1+2 remains build_combined.py.
Temp is created on this project's volume to avoid Windows cross-drive relpath errors.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--output',default='_build_all_three')
    args=ap.parse_args()
    base=Path(__file__).resolve().parent
    out=(base/args.output).resolve()
    if out==base or base not in out.parents:ap.error('output must be inside report_repo')
    with tempfile.TemporaryDirectory(prefix='.milestone123_',dir=str(base.parent)) as d:
        stage=Path(d)/'report'
        shutil.copytree(base,stage,ignore=shutil.ignore_patterns(
            '.git','.venv','_build','_build_combined','_build_all_three',
            '__pycache__','.ipynb_checkpoints','*.bak','*.doctree','*.pyc'))
        (stage/'_toc.yml').write_text('format: jb-book\nroot: index\nchapters:\n'
                                      '  - file: milestone1\n  - file: milestone2\n  - file: milestone3\n',encoding='utf-8')
        subprocess.run([sys.executable,'-c','from jupyter_book.cli.main import main; main()',
                        'build',str(stage)],check=True,cwd=str(base))
        html=stage/'_build'/'html'
        if not (html/'index.html').exists():raise RuntimeError('No HTML output found')
        if out.exists():shutil.rmtree(out)
        shutil.copytree(html,out)
    print('MILESTONE 1+2+3 PREVIEW:',out/'index.html')

if __name__=='__main__':main()
