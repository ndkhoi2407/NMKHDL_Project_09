#!/usr/bin/env python3
"""Fast, offline progress dashboard (safe to run while the crawler is downloading)."""
from __future__ import annotations
import argparse
from collections import Counter
from pathlib import Path
import time

from crawler import paper_dir, parse_range, read_json


def snapshot(root: Path, ids: list[str]) -> dict:
    """Compute progress from per-paper checkpoints, not an out-of-date summary.json."""
    stage = Counter()
    source = Counter()
    s2 = Counter()
    versions = 0
    exact = 0
    examples: dict[str, list[str]] = {"pending_discovery": [], "pending_sources": [],
                                      "pending_references": [], "pending_exact_metadata": []}
    for ident in ids:
        folder = paper_dir(root, ident)
        paper = read_json(folder / "paper.json", {})
        state = paper.get("status", "pending")
        stage[state] += 1
        if state == "pending" and len(examples["pending_discovery"]) < 5:
            examples["pending_discovery"].append(ident)
        if state != "found":
            continue
        v_max = paper.get("latest_version", 0)
        versions += v_max
        for ver in range(1, v_max + 1):
            src_state = read_json(folder / f"v{ver}" / "source_status.json", {}).get("status", "pending")
            source[src_state] += 1
            if src_state not in ("ok", "no_latex", "no_source") and len(examples["pending_sources"]) < 5:
                examples["pending_sources"].append(f"{ident}v{ver}")
            fidelity = read_json(folder / f"v{ver}" / "metadata.json", {}).get("metadata_fidelity")
            if fidelity == "exact_version":
                exact += 1
            elif len(examples["pending_exact_metadata"]) < 5:
                examples["pending_exact_metadata"].append(f"{ident}v{ver}")
        ref_state = read_json(folder / "references_all.json", {}).get("status", "pending")
        s2[ref_state] += 1
        if ref_state not in ("ok", "not_found") and len(examples["pending_references"]) < 5:
            examples["pending_references"].append(ident)
    return {"assigned": len(ids), "discovered": stage["found"], "not_found": stage["not_found"],
            "pending_discovery": stage["pending"], "expected_versions": versions,
            "source_checked": sum(source[s] for s in ("ok", "no_latex", "no_source")),
            "source_with_latex": source["ok"], "source_error": source["error"],
            "exact_version_metadata": exact, "s2_ok": s2["ok"], "s2_not_found": s2["not_found"],
            "s2_pending": s2["pending"], "examples": examples}


def display(result: dict) -> None:
    print("\n" + "=" * 61)
    print("  MILESTONE 1  |  arXiv CRAWL STATUS  |  OFFLINE")
    print("=" * 61)
    for label, value in [
        ("Assigned base IDs", result["assigned"]),
        ("Discovered / Not found / Pending", f'{result["discovered"]} / {result["not_found"]} / {result["pending_discovery"]}'),
        ("Source versions checked / expected", f'{result["source_checked"]} / {result["expected_versions"]}'),
        ("Versions with TeX / BibTeX", result["source_with_latex"]),
        ("Source download errors", result["source_error"]),
        ("Exact-version Atom metadata", f'{result["exact_version_metadata"]} / {result["expected_versions"]}'),
        ("Semantic Scholar OK / Not indexed / Pending",
         f'{result["s2_ok"]} / {result["s2_not_found"]} / {result["s2_pending"]}'),
    ]:
        print(f"  {label:<44} {value}")
    print("-" * 61)
    for name, items in result["examples"].items():
        if items:
            print(f"  {name}: {', '.join(items)}")
    print("  Missing per-version Atom metadata is NOT equivalent to a failed source download.")
    print("=" * 61 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline progress inspection (does not call external APIs)")
    parser.add_argument("--output", default="data")
    parser.add_argument("--start", default="2607.13694")
    parser.add_argument("--end", default="2607.18693")
    parser.add_argument("--max-papers", type=int, default=None)
    parser.add_argument("--watch", type=float, default=0,
                        help="Reprint progress every N seconds, 0 for one-time output")
    args = parser.parse_args()
    if args.watch < 0 or (args.watch and args.watch < 5):
        parser.error("--watch must be 0 or >= 5 seconds")
    ids = parse_range(args.start, args.end, args.max_papers)
    try:
        while True:
            display(snapshot(Path(args.output), ids))
            if not args.watch:
                break
            time.sleep(args.watch)
    except KeyboardInterrupt:
        print("Status monitor stopped; crawler was not touched.")


if __name__ == "__main__":
    main()
