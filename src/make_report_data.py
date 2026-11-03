"""Create the SMALL files used by the Jupyter Book report from the project data.

The book repository does not contain the corpus (it is very large), so every number in the
report must come from small files. This script copies the benchmark results and computes extra
statistics from parsed.json (table sizes, element kinds, reasons for failed versions, an example).

Run from the project root (where data/ is):
    python src/make_report_data.py --m1-out ../arxiv-report/m1_data --m2-out ../arxiv-report/m2_data
Either option can be used alone.
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


def copy_benchmark(src: Path, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    for name in BENCH_FILES:
        f = src / name
        if f.exists():
            shutil.copy2(f, out / name)
            print(f"  copy {f} -> {out / name}")
        else:
            print(f"  MISSING {f} (run the benchmark first)")


def m2_extras(out: Path):
    rows, kinds = Counter(), Counter()
    failed, reasons = [], Counter()
    best = None                                   # example: small paper, >=2 versions, shared elements
    n_files = 0
    for f in sorted(DATA_DIR.glob("*/parsed.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        n_files += 1
        for t in ("elements", "hierarchy", "bibtex"):
            rows[t] += len(d[t])
        kinds.update(e["kind"] for e in d["elements"])
        for v, info in d["versions"].items():
            if info["status"] == "ok":
                continue
            reason = re.sub(r"\s*\[.*$", "", info.get("reason", ""))
            reasons[(info["status"], reason)] += 1
            if info["status"] == "failed":
                failed.append({"arxiv_id": d["arxiv_id"], "version": int(v),
                               "reason": info.get("reason", "")[:200]})
        per_version = {}
        for h in d["hierarchy"]:
            per_version.setdefault(h["version"], set()).add(h["element_id"])
        shared = set.intersection(*per_version.values()) if len(per_version) >= 2 else set()
        if shared and 8 <= len(d["elements"]) <= 60 and (best is None or len(d["elements"]) < len(best["elements"])):
            best = d

    tables = {}
    for t in ("elements", "hierarchy", "bibtex"):
        fp = DATA_DIR / "tables" / f"{t}.jsonl"
        tables[t] = {"rows": rows[t], "bytes": fp.stat().st_size if fp.exists() else None}
    out.mkdir(parents=True, exist_ok=True)
    (out / "tables_stats.json").write_text(json.dumps(tables, indent=2), encoding="utf-8")
    (out / "kind_counts.json").write_text(json.dumps(dict(kinds.most_common()), indent=2), encoding="utf-8")
    (out / "failures.json").write_text(json.dumps({
        "reasons": [{"status": s, "reason": r, "count": c} for (s, r), c in reasons.most_common()],
        "failed_versions": failed}, indent=2, ensure_ascii=False), encoding="utf-8")
    if best:
        ids = {e["element_id"] for e in best["elements"][:30]}
        example = {"arxiv_id": best["arxiv_id"],
                   "elements": [{**e, "content": e["content"][:120]} for e in best["elements"][:30]],
                   "hierarchy": [h for h in best["hierarchy"] if h["element_id"] in ids][:40],
                   "bibtex": best["bibtex"][:5]}
    else:
        example = None
    (out / "example.json").write_text(json.dumps(example, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  {n_files} parsed.json -> tables_stats.json, kind_counts.json, failures.json, example.json")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--m1-out", type=Path, help="m1_data folder of the book repository")
    ap.add_argument("--m2-out", type=Path, help="m2_data folder of the book repository")
    args = ap.parse_args()
    if not (args.m1_out or args.m2_out):
        ap.error("need --m1-out and/or --m2-out")
    if args.m1_out:
        print("[M1]")
        copy_benchmark(DATA_DIR / "benchmark", args.m1_out)
    if args.m2_out:
        print("[M2]")
        copy_benchmark(DATA_DIR / "benchmark_parse", args.m2_out)
        m2_extras(args.m2_out)


if __name__ == "__main__":
    main()