"""Offline command-line entry point for Milestone 2 parsing."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from src.crawler import parse_range
from .pipeline import run


def main() -> None:
    p = argparse.ArgumentParser(description='Milestone 2: parse local Milestone 1 TeX sources offline')
    p.add_argument('--output', default='data', help='Existing Milestone 1 data/ directory')
    p.add_argument('--parsed-output', default=None, help='New Milestone 2 directory; default data/milestone2')
    p.add_argument('--start', default='2607.13694')
    p.add_argument('--end', default='2607.18693')
    p.add_argument('--max-papers', type=int, default=None)
    p.add_argument('--force', action='store_true', help='Re-parse previously completed papers')
    p.add_argument('--no-tables', action='store_true', help='Skip combined JSONL table export')
    p.add_argument('--report', default=None, help='Existing report_repo directory to sync new Mile 2 statistics')
    args = p.parse_args()
    if args.max_papers is not None and args.max_papers < 1:
        p.error('--max-papers must be positive')
    ids = parse_range(args.start, args.end, args.max_papers)
    result = run(Path(args.output), ids, parsed_root=Path(args.parsed_output) if args.parsed_output else None,
                 force=args.force, make_tables=not args.no_tables,
                 report_root=Path(args.report) if args.report else None)
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
