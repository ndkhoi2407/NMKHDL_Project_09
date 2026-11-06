
"""Create the SMALL files used by the Jupyter Book report from project data.

The book repository does not contain the full corpus.
This script copies benchmark results and computes extra statistics
from parsed.json files.

Run from the report repository root:
    python src/make_report_data.py --m1-out ./m1_data --m2-out ./m2_data
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from collections import Counter
from pathlib import Path

DATA_DIR = Path("data")

BENCH_FILES = ("summary.json", "papers.csv", "samples.csv")
TABLE_FILES = ("elements", "hierarchy", "bibtex")


def copy_benchmark(src: Path, out: Path):
    """Copy benchmark files if they exist."""
    out.mkdir(parents=True, exist_ok=True)

    for name in BENCH_FILES:
        f = src / name

        if f.exists():
            shutil.copy2(f, out / name)
            print(f"  Copied: {f} -> {out / name}")
        else:
            print(f"  MISSING: {f}")


def find_parsed_files():
    """Find parsed.json files at any depth inside data/."""
    if not DATA_DIR.exists():
        return []

    return sorted(DATA_DIR.rglob("parsed.json"))


def find_table_file(table_name: str):
    """Find a JSONL table file anywhere inside data/."""
    filename = f"{table_name}.jsonl"

    if not DATA_DIR.exists():
        return None

    matches = sorted(DATA_DIR.rglob(filename))

    return matches[0] if matches else None


def m2_extras(out: Path):
    """Calculate additional Milestone 2 statistics."""

    rows = Counter()
    kinds = Counter()
    reasons = Counter()
    failed = []

    best = None
    n_files = 0
    skipped = 0

    parsed_files = find_parsed_files()

    if not parsed_files:
        print("WARNING: No parsed.json files found inside data/.")
        print("Please check the Milestone 2 output directory.")
        return

    print(f"Found {len(parsed_files)} parsed.json file(s).")

    for f in parsed_files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))

            elements = d.get("elements", [])
            hierarchy = d.get("hierarchy", [])
            bibtex = d.get("bibtex", [])
            versions = d.get("versions", {})

            if not isinstance(elements, list):
                elements = []

            if not isinstance(hierarchy, list):
                hierarchy = []

            if not isinstance(bibtex, list):
                bibtex = []

            if not isinstance(versions, dict):
                versions = {}

            n_files += 1

            # Count parsed table rows.
            rows["elements"] += len(elements)
            rows["hierarchy"] += len(hierarchy)
            rows["bibtex"] += len(bibtex)

            # Count element kinds.
            for element in elements:
                if isinstance(element, dict):
                    kind = element.get("kind", "unknown")
                    kinds[kind] += 1

            # Collect failed and non-successful versions.
            for version, info in versions.items():
                if not isinstance(info, dict):
                    continue

                status = info.get("status", "unknown")

                if status == "ok":
                    continue

                reason = info.get("reason", "")
                reason = re.sub(r"\s*\[.*$", "", reason)

                reasons[(status, reason)] += 1

                if status == "failed":
                    try:
                        version_number = int(version)
                    except (ValueError, TypeError):
                        version_number = version

                    failed.append({
                        "arxiv_id": d.get("arxiv_id", f.parent.name),
                        "version": version_number,
                        "reason": str(info.get("reason", ""))[:200],
                    })

            # Find an example paper with shared elements across versions.
            per_version = {}

            for item in hierarchy:
                if not isinstance(item, dict):
                    continue

                version = item.get("version")
                element_id = item.get("element_id")

                if version is not None and element_id is not None:
                    per_version.setdefault(version, set()).add(element_id)

            shared = set()

            if len(per_version) >= 2:
                shared = set.intersection(*per_version.values())

            if (
                shared
                and 8 <= len(elements) <= 60
                and (
                    best is None
                    or len(elements) < len(best["elements"])
                )
            ):
                best = {
                    "arxiv_id": d.get("arxiv_id", f.parent.name),
                    "elements": elements,
                    "hierarchy": hierarchy,
                    "bibtex": bibtex,
                }

        except (json.JSONDecodeError, OSError, TypeError) as error:
            skipped += 1
            print(f"  SKIPPED: {f} ({error})")

    # Find the actual JSONL table files.
    tables = {}

    for table_name in TABLE_FILES:
        fp = find_table_file(table_name)

        tables[table_name] = {
            "rows": rows[table_name],
            "bytes": fp.stat().st_size if fp else None,
            "path": str(fp) if fp else None,
        }

    out.mkdir(parents=True, exist_ok=True)

    # Save table statistics.
    (out / "tables_stats.json").write_text(
        json.dumps(tables, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Save element kind counts.
    (out / "kind_counts.json").write_text(
        json.dumps(dict(kinds.most_common()), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Save failed version statistics.
    failure_data = {
        "reasons": [
            {
                "status": status,
                "reason": reason,
                "count": count,
            }
            for (status, reason), count in reasons.most_common()
        ],
        "failed_versions": failed,
    }

    (out / "failures.json").write_text(
        json.dumps(failure_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Save one example paper.
    if best:
        selected_elements = best["elements"][:30]

        element_ids = {
            e["element_id"]
            for e in selected_elements
            if isinstance(e, dict) and "element_id" in e
        }

        example = {
            "arxiv_id": best["arxiv_id"],
            "elements": [
                {
                    **e,
                    "content": str(e.get("content", ""))[:120],
                }
                for e in selected_elements
                if isinstance(e, dict)
            ],
            "hierarchy": [
                h
                for h in best["hierarchy"]
                if isinstance(h, dict)
                and h.get("element_id") in element_ids
            ][:40],
            "bibtex": best["bibtex"][:5],
        }
    else:
        example = None

    (out / "example.json").write_text(
        json.dumps(example, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print()
    print(f"Successfully processed: {n_files} parsed.json file(s)")
    print(f"Skipped: {skipped} file(s)")
    print(f"Report data saved to: {out.resolve()}")
    print("Generated:")
    print("  - tables_stats.json")
    print("  - kind_counts.json")
    print("  - failures.json")
    print("  - example.json")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__.split("\n")[0]
    )

    ap.add_argument(
        "--m1-out",
        type=Path,
        help="M1 report data output folder",
    )

    ap.add_argument(
        "--m2-out",
        type=Path,
        help="M2 report data output folder",
    )

    args = ap.parse_args()

    if not args.m1_out and not args.m2_out:
        ap.error("Please provide --m1-out and/or --m2-out")

    if args.m1_out:
        print("[MILESTONE 1]")
        copy_benchmark(DATA_DIR / "benchmark", args.m1_out)

    if args.m2_out:
        print("\n[MILESTONE 2]")
        copy_benchmark(DATA_DIR / "benchmark_parse", args.m2_out)
        m2_extras(args.m2_out)


if __name__ == "__main__":
    main()
