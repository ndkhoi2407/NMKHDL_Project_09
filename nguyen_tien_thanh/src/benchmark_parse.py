"""Do hieu nang parser Milestone 2 va tinh thong ke cho bao cao.

Chay parse.py (ca cay tien trinh, ke ca cac worker) nhu hop den va do:
  - Thoi gian: wall time end-to-end, trung binh moi bai.
  - RAM: tong bo nho ca cay tien trinh, lay mau dinh ky -> toi da / trung binh.
  - Dung luong dau ra (parsed.json + data/tables neu co).
Thong ke: ty le parse thanh cong, do phu version tung bai, so element / entry
bibtex truoc va sau khu trung.

Ket qua ghi vao data/benchmark_parse/: summary.json, papers.csv, samples.csv.

Vi du (do chinh thuc, tren Colab CPU):
    python src/benchmark_parse.py --fresh --workers 2
    python src/benchmark_parse.py --report-only
"""
from __future__ import annotations

import argparse
import csv
import json
import platform
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import benchmark as B                      # dung lai ham do RAM cua Milestone 1

SRC_DIR = Path(__file__).resolve().parent
DATA_DIR = Path("data")
STATUS_FILE = DATA_DIR / "parse_status.json"
OUT = DATA_DIR / "benchmark_parse"
MB = 1024 * 1024


def compute_stats():
    disc = B.as_dict(B.load_json(DATA_DIR / "discovery.json", {}))
    papers = [p for p in disc.get("papers", []) if isinstance(p, dict) and "id" in p]
    st = B.as_dict(B.load_json(STATUS_FILE, {}))
    rows, out_bytes = [], 0
    for p in papers:
        s = B.as_dict(st.get(p["id"]))
        f = DATA_DIR / p["folder"] / "parsed.json"
        size = f.stat().st_size if f.exists() else 0
        out_bytes += size
        with_tex = (s.get("versions_ok") or 0) + (s.get("versions_failed") or 0)
        rows.append({
            "id": p["id"], "status": s.get("status", "missing"),
            "versions": s.get("versions"), "versions_ok": s.get("versions_ok"),
            "versions_empty": s.get("versions_empty"), "versions_failed": s.get("versions_failed"),
            "version_coverage": B.ratio(s.get("versions_ok") or 0, s.get("versions")) if s.get("versions") else None,
            "parse_success_rate": B.ratio(s.get("versions_ok") or 0, with_tex) if with_tex else None,
            "elements_before_dedup": s.get("elements_before_dedup"),
            "elements_after_dedup": s.get("elements_after_dedup"),
            "hierarchy_rows": s.get("hierarchy_rows"),
            "bib_before_dedup": s.get("bib_before_dedup"),
            "bib_after_dedup": s.get("bib_after_dedup"),
            "seconds": s.get("seconds"), "output_bytes": size,
        })
    done = [r for r in rows if r["status"] in ("ok", "partial")]
    tot = lambda k: sum(r[k] or 0 for r in done)
    ok_v, fail_v = tot("versions_ok"), tot("versions_failed")
    data = {
        "papers_total": len(rows), "papers_processed": len(done),
        "papers_error": sum(1 for r in rows if r["status"] == "error"),
        "papers_missing": sum(1 for r in rows if r["status"] == "missing"),
        "paper_success_rate": B.ratio(len(done), len(rows)),
        "versions_total": tot("versions"), "versions_ok": ok_v,
        "versions_empty": tot("versions_empty"), "versions_failed": fail_v,
        "version_parse_success_rate": B.ratio(ok_v, ok_v + fail_v),      # trong cac version co TeX
        "version_coverage_overall": B.ratio(ok_v, tot("versions")),
        "avg_version_coverage_per_paper": B.mean([r["version_coverage"] for r in done]),
        "elements_before_dedup": tot("elements_before_dedup"),
        "elements_after_dedup": tot("elements_after_dedup"),
        "element_reduction": 1 - B.ratio(tot("elements_after_dedup"), tot("elements_before_dedup"))
        if tot("elements_before_dedup") else None,
        "hierarchy_rows": tot("hierarchy_rows"),
        "bib_before_dedup": tot("bib_before_dedup"), "bib_after_dedup": tot("bib_after_dedup"),
        "bib_reduction": 1 - B.ratio(tot("bib_after_dedup"), tot("bib_before_dedup"))
        if tot("bib_before_dedup") else None,
        "avg_seconds_per_paper_cpu": B.mean([r["seconds"] for r in done]),
    }
    return data, rows, out_bytes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--cited-only", action="store_true")
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--fresh", action="store_true",
                    help="XOA parsed.json + parse_status.json truoc khi do (de do day du)")
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args()

    rc, wall, samples = None, None, []
    if not args.report_only:
        if args.fresh:
            n = 0
            for f in DATA_DIR.glob("*/parsed.json"):
                f.unlink()
                n += 1
            STATUS_FILE.unlink(missing_ok=True)
            print(f"[BENCH-M2] Da xoa {n} parsed.json va parse_status.json")
        elif STATUS_FILE.exists():
            print("[BENCH-M2] CANH BAO: da co ket qua cu; parse.py se bo qua bai da xong nen "
                  "thoi gian KHONG day du. Dung --fresh de do chinh thuc.")
        cmd = [sys.executable, str(SRC_DIR / "parse.py")]
        for flag, val in (("--workers", args.workers), ("--limit", args.limit)):
            if val is not None:
                cmd += [flag, str(val)]
        if args.cited_only:
            cmd.append("--cited-only")
        print("[BENCH-M2] Do:", " ".join(cmd))
        rc, wall, samples = B.run_monitored(cmd, args.interval)

    data, rows, out_bytes = compute_stats()
    tables = sum(f.stat().st_size for f in (DATA_DIR / "tables").glob("*.jsonl")) \
        if (DATA_DIR / "tables").exists() else 0
    ram, n = [s[1] for s in samples], data["papers_processed"]
    summary = {
        "run": {"created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "args": vars(args), "python": platform.python_version(),
                "platform": platform.platform(), "cpu_count": B.psutil.cpu_count(),
                "returncode": rc, "measured": not args.report_only},
        "timing": {"wall_seconds": wall,
                   "avg_seconds_per_paper": B.ratio(wall, n) if wall else None},
        "memory": {"metric": B.MEMORY_METRIC, "peak_bytes": max(ram) if ram else None,
                   "avg_bytes": B.mean(ram), "samples": len(ram)},
        "output": {"parsed_json_bytes": out_bytes, "tables_jsonl_bytes": tables,
                   "avg_bytes_per_paper": B.ratio(out_bytes, n)},
        "data": data,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    with open(OUT / "samples.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["seconds", "ram_mb"])
        w.writerows((round(t, 2), round(r / MB, 2)) for t, r, _ in samples)
    with open(OUT / "papers.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["id"])
        w.writeheader()
        w.writerows(rows)

    fmt = lambda v, f="{:.1f}": "n/a" if v is None else f.format(v)
    pct = lambda v: fmt(None if v is None else v * 100)
    print("\n================ TOM TAT M2 ================")
    print(f"Bai xu ly: {n}/{data['papers_total']} ({pct(data['paper_success_rate'])}%); "
          f"version parse ok: {data['versions_ok']}/{data['versions_total']} "
          f"(rong {data['versions_empty']}, loi {data['versions_failed']}); "
          f"ty le parse thanh cong (version co TeX): {pct(data['version_parse_success_rate'])}%")
    print(f"Element truoc -> sau khu trung: {data['elements_before_dedup']} -> {data['elements_after_dedup']} "
          f"(giam {pct(data['element_reduction'])}%); bibtex: {data['bib_before_dedup']} -> {data['bib_after_dedup']}")
    print(f"Wall: {fmt(wall)}s; TB/bai: {fmt(summary['timing']['avg_seconds_per_paper'], '{:.3f}')}s; "
          f"RAM toi da: {fmt(None if not ram else max(ram) / MB)} MB ({B.MEMORY_METRIC}); "
          f"dung luong dau ra: {out_bytes / MB:.2f} MB")
    print(f"Da ghi: {OUT}/summary.json, samples.csv, papers.csv")
    return 0 if rc in (None, 0) else 1


if __name__ == "__main__":
    sys.exit(main())
