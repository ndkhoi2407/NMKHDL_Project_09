#!/usr/bin/env python3
"""Offline consistency audit: inspect checkpoints and retained source files."""
from __future__ import annotations
import argparse
import json
from collections import Counter
from pathlib import Path
from crawler import parse_range, paper_dir, read_json, write_json, utc_now


def audit(root: Path, ids: list[str]) -> dict:
    issues = []
    counts = Counter()
    for ident in ids:
        folder = paper_dir(root, ident)
        entry = read_json(folder / "paper.json", {})
        state = entry.get("status", "pending")
        counts[f"discovery_{state}"] += 1
        if state not in ("found", "not_found"):
            issues.append({"paper": ident, "issue": "discovery_pending"})
            continue
        if state == "not_found":
            continue
        latest = int(entry.get("latest_version") or 0)
        if latest < 1:
            issues.append({"paper": ident, "issue": "invalid_latest_version"})
        all_dates = read_json(folder / "versions_oai.json", [])
        if all_dates and len(all_dates) != latest:
            issues.append({"paper": ident, "issue": "incomplete_oai_history"})
        for n in range(1, latest + 1):
            tag = f"{ident}v{n}"
            vdir = folder / f"v{n}"
            src_status = read_json(vdir / "source_status.json", {})
            src_state = src_status.get("status", "pending")
            counts[f"source_{src_state}"] += 1
            if src_state not in ("ok", "no_latex", "no_source"):
                issues.append({"paper": tag, "issue": "source_not_verified", "status": src_state})
            elif src_state == "ok":
                stored = sorted(p for p in (vdir / "source").rglob("*") if p.is_file()) if (vdir / "source").exists() else []
                if not stored or len(stored) != src_status.get("tex_bib_files"):
                    issues.append({"paper": tag, "issue": "source_file_count_mismatch"})
                if any(p.suffix.lower() not in (".tex", ".bib") for p in stored):
                    issues.append({"paper": tag, "issue": "unexpected_file_type"})
            meta = read_json(vdir / "metadata.json", {})
            if meta.get("metadata_fidelity") == "exact_version":
                counts["metadata_exact"] += 1
            else:
                counts["metadata_pending_exact"] += 1
        ref_state = read_json(folder / "references_all.json", {}).get("status", "pending")
        counts[f"references_{ref_state}"] += 1
        if ref_state not in ("ok", "not_found"):
            issues.append({"paper": ident, "issue": "references_not_verified"})
    return {"generated_at": utc_now(), "assigned_ids": len(ids), "counts": dict(counts),
            "issue_count": len(issues), "issues": issues,
            "note": "Unavailable papers and source-free versions are not automatically errors. "
                    "Metadata exact-version completeness is counted separately."}


def main() -> None:
    ap = argparse.ArgumentParser(description="Check data consistency without requesting the internet")
    ap.add_argument("--output", default="data")
    ap.add_argument("--start", default="2607.13694")
    ap.add_argument("--end", default="2607.18693")
    ap.add_argument("--max-papers", type=int, default=None)
    ap.add_argument("--strict", action="store_true", help="Exit code 1 if any hard issue remains")
    args = ap.parse_args()
    root = Path(args.output)
    result = audit(root, parse_range(args.start, args.end, args.max_papers))
    write_json(root / "audit.json", result)
    print(f'AUDIT | assigned={result["assigned_ids"]} | issues={result["issue_count"]}')
    print('Counts:', json.dumps(result["counts"], ensure_ascii=False, sort_keys=True))
    for item in result["issues"][:15]:
        print(' -', item)
    if len(result["issues"]) > 15:
        print(f' ... {len(result["issues"])-15} more in {root / "audit.json"}')
    print('Saved:', root / 'audit.json')
    if args.strict and result["issue_count"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
