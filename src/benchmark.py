"""Do hieu nang cua scraper va tinh thong ke du lieu cho bao cao Milestone 1.

Chay main.py (ca he thong, end-to-end) nhu mot hop den va do:
  - Thoi gian: wall time end-to-end, thoi gian tung buoc (ke ca discovery),
    thoi gian trung binh moi bai, va (tuy chon) thoi gian xu ly MOT bai.
  - RAM: tong bo nho cua CA CAY tien trinh (main.py + cac chuong trinh con),
    lay mau dinh ky -> RAM toi da va RAM trung binh.
  - O dia: muc dia tang them toi da trong luc chay, dung luong corpus cuoi.
Sau do tinh thong ke du lieu tu cac file status: so bai crawl thanh cong, ty le
thanh cong, kich thuoc trung binh moi bai truoc/sau khi xoa anh (byte), so
reference trung binh moi bai, ty le lay duoc metadata cua reference.

Ket qua ghi vao data/benchmark/ (cac file nho, Jupyter Book doc de ve bieu do
luc compile):
    summary.json   cac con so tong hop
    samples.csv    chuoi thoi gian RAM / o dia
    papers.csv     thong ke tung bai

Vi du (nen xoa thu muc data/ truoc de do mot lan chay day du, tren Colab CPU):
    python src/benchmark.py --prefix 2310 --start 1 --end 5000 --single-trial
    python src/benchmark.py --report-only      # chi tinh thong ke tu du lieu co san

Can: pip install psutil
"""
from __future__ import annotations

import argparse
import csv
import json
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

try:
    import psutil
except ImportError:  # pragma: no cover
    raise SystemExit("Thieu thu vien psutil. Cai bang: pip install psutil")

SRC_DIR = Path(__file__).resolve().parent
MAIN = SRC_DIR / "main.py"
DATA_DIR = Path("data")
DEFAULT_OUT = DATA_DIR / "benchmark"
MB = 1024 * 1024


def _detect_memory_metric() -> str:
    """PSS (Linux) chia deu bo nho dung chung giua cac tien trinh nen tong khong
    bi tinh trung; cac he khac dung RSS."""
    try:
        return "pss" if hasattr(psutil.Process().memory_full_info(), "pss") else "rss"
    except Exception:
        return "rss"


MEMORY_METRIC = _detect_memory_metric()


def load_json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def ratio(a: int, b: int):
    return a / b if b else None


def dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


# ---------------------------------------------------------------- do luong

def process_tree_bytes(root: psutil.Process) -> int:
    """Tong bo nho cua tien trinh goc va moi tien trinh con."""
    try:
        procs = [root] + root.children(recursive=True)
    except psutil.NoSuchProcess:
        return 0
    total = 0
    for p in procs:
        try:
            total += (p.memory_full_info().pss if MEMORY_METRIC == "pss"
                      else p.memory_info().rss)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return total


def run_monitored(cmd: list[str], interval: float):
    """Chay cmd, lay mau RAM va o dia moi `interval` giay.

    Tra ve (ma_thoat, wall_seconds, samples[(giay, ram_byte, dia_tang_byte)]).
    O dia tinh bang muc dung cua ca phan vung tru muc luc bat dau (nhanh hon
    nhieu so voi duyet tung file).
    """
    base_used = shutil.disk_usage(".").used
    samples = []
    t0 = time.perf_counter()
    proc = subprocess.Popen(cmd)
    root = psutil.Process(proc.pid)
    try:
        while True:
            samples.append((time.perf_counter() - t0,
                            process_tree_bytes(root),
                            max(0, shutil.disk_usage(".").used - base_used)))
            try:
                rc = proc.wait(timeout=interval)
                wall = time.perf_counter() - t0
                break
            except subprocess.TimeoutExpired:
                continue
    except BaseException:
        proc.terminate()
        raise
    return rc, wall, samples


def single_trial(args) -> dict:
    """Chay ca pipeline cho DUNG MOT bai (ID dau tien) trong thu muc tam,
    de do thoi gian xu ly mot bai tu dau den cuoi."""
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [sys.executable, str(MAIN), "--workdir", tmp, "--prefix", args.prefix,
               "--start", str(args.start), "--end", str(args.start)]
        if args.skip:
            cmd += ["--skip", args.skip]
        t0 = time.perf_counter()
        rc = subprocess.call(cmd)
        seconds = time.perf_counter() - t0
        found = load_json(Path(tmp) / "data" / "discovery.json", {}).get("papers", [])
    return {"returncode": rc, "seconds": round(seconds, 2),
            "papers_found": len(found),
            "versions": found[0]["latest_version"] if found else None}


# ---------------------------------------------------------------- thong ke

def compute_stats():
    """Thong ke du lieu tu discovery.json va cac file *_status.json."""
    disc = load_json(DATA_DIR / "discovery.json", {})
    papers = disc.get("papers", [])
    dl = load_json(DATA_DIR / "download_status.json", {})
    md = load_json(DATA_DIR / "metadata_status.json", {})
    rf = load_json(DATA_DIR / "references_status.json", {})

    rows, version_status = [], Counter()
    sized_versions = ver_before = ver_after = 0
    for p in papers:
        pid, versions = p["id"], p["versions"]
        c = Counter()
        arch = before = after = sized = 0
        for v in versions:
            info = dl.get(f"{pid}{v}")
            st = info["status"] if info else "missing"
            c[st] += 1
            version_status[st] += 1
            if not info:
                continue
            arch += info.get("archive_bytes", 0)
            if ("extracted_bytes_before_cleanup" in info
                    and "extracted_bytes_after_cleanup" in info):
                before += info["extracted_bytes_before_cleanup"]
                after += info["extracted_bytes_after_cleanup"]
                sized += 1
        sized_versions += sized
        ver_before += before
        ver_after += after

        r = rf.get(pid, {})
        refs_saved = r.get("refs_saved", r.get("refs_with_arxiv_id"))
        download_ok = c["error"] == 0 and c["missing"] == 0   # khong version nao loi
        metadata_ok = md.get(pid, {}).get("status") == "ok"
        refs_status = r.get("status", "missing")
        rows.append({
            "id": pid,
            "versions": len(versions),
            "versions_ok": c["ok"],
            "versions_no_tex": c["no_tex"],
            "versions_pdf_only": c["pdf_only"],
            "versions_other_format": c["other_format"],
            "versions_error": c["error"],
            "versions_missing": c["missing"],
            "download_ok": download_ok,
            "tex_ok": c["ok"] == len(versions),
            "metadata_ok": metadata_ok,
            "references_status": refs_status,
            "total_refs": r.get("total_refs"),
            "refs_with_arxiv_id": r.get("refs_with_arxiv_id"),
            "refs_saved": refs_saved,
            "refs_metadata_ok": r.get("refs_metadata_ok"),
            "bytes_archive": arch,
            "bytes_before": before if sized else None,
            "bytes_after": after if sized else None,
            "scraped_ok": (download_ok and metadata_ok
                           and refs_status in ("ok", "no_s2_record")),
        })

    n = len(papers)
    count = lambda key: sum(1 for r in rows if r[key])
    sized_rows = [r for r in rows if r["bytes_before"] is not None]
    ref_rows = [r for r in rows if r["references_status"] == "ok"]
    saved_total = sum(r["refs_saved"] or 0 for r in ref_rows)
    meta_ok_total = sum(r["refs_metadata_ok"] or 0 for r in ref_rows)
    ids_stats = disc.get("stats", {})

    data = {
        "ids_in_range": ids_stats.get("ids_in_range"),
        "papers_found": n,
        "ids_not_found": ids_stats.get("not_found"),
        "ids_failed_in_discovery": ids_stats.get("failed_ids"),
        "versions_total": sum(len(p["versions"]) for p in papers),
        "versions_by_status": dict(version_status),
        # Bai "thanh cong" = moi version tai khong loi + metadata ok + references ok
        "papers_scraped_successfully": count("scraped_ok"),
        "overall_success_rate": ratio(count("scraped_ok"), n),
        "download_success_rate": ratio(count("download_ok"), n),
        "tex_coverage_rate": ratio(count("tex_ok"), n),   # moi version deu co .tex
        "metadata_success_rate": ratio(count("metadata_ok"), n),
        "references_success_rate": ratio(
            sum(1 for r in rows if r["references_status"] in ("ok", "no_s2_record")), n),
        "papers_without_s2_record": sum(
            1 for r in rows if r["references_status"] == "no_s2_record"),
        # Kich thuoc (byte), tong cac version cua moi bai
        "avg_paper_bytes_before_cleanup": mean([r["bytes_before"] for r in sized_rows]),
        "avg_paper_bytes_after_cleanup": mean([r["bytes_after"] for r in sized_rows]),
        "avg_version_bytes_before_cleanup": ratio(ver_before, sized_versions),
        "avg_version_bytes_after_cleanup": ratio(ver_after, sized_versions),
        "avg_archive_bytes_per_paper": mean([r["bytes_archive"] for r in rows]),
        # References
        "avg_refs_per_paper": mean([r["total_refs"] for r in ref_rows]),
        "avg_arxiv_refs_per_paper": mean([r["refs_with_arxiv_id"] for r in ref_rows]),
        "avg_ref_metadata_success_rate_per_paper": mean(
            [ratio(r["refs_metadata_ok"] or 0, r["refs_saved"])
             for r in ref_rows if r["refs_saved"]]),
        "ref_metadata_success_rate_overall": ratio(meta_ok_total, saved_total),
    }
    return data, rows, papers


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--prefix")
    ap.add_argument("--start", type=int)
    ap.add_argument("--end", type=int)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--skip", default="", help="chuyen tiep cho main.py")
    ap.add_argument("--interval", type=float, default=1.0,
                    help="chu ky lay mau RAM/o dia (giay)")
    ap.add_argument("--single-trial", action="store_true",
                    help="do them thoi gian xu ly mot bai (chay rieng, khong tinh vao lan do chinh)")
    ap.add_argument("--report-only", action="store_true",
                    help="khong chay gi, chi tinh thong ke tu du lieu co san")
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    trial = None
    rc, wall, samples = None, None, []
    if not args.report_only:
        if "discover" not in args.skip and None in (args.prefix, args.start, args.end):
            ap.error("can --prefix, --start, --end (hoac --report-only)")
        if any(DATA_DIR.glob("*")) and DATA_DIR.exists():
            print("[BENCH] CANH BAO: data/ khong rong. Cac buoc se bo qua phan da xong nen "
                  "thoi gian KHONG phan anh mot lan chay day du. Xoa data/ truoc khi do chinh thuc.")
        if args.single_trial:
            print("[BENCH] Do thu mot bai (thu muc tam)...")
            trial = single_trial(args)
        cmd = [sys.executable, str(MAIN)]
        for flag, val in (("--prefix", args.prefix), ("--start", args.start),
                          ("--end", args.end), ("--limit", args.limit),
                          ("--skip", args.skip)):
            if val not in (None, ""):
                cmd += [flag, str(val)]
        print(f"[BENCH] Bat dau do: {' '.join(cmd)}")
        rc, wall, samples = run_monitored(cmd, args.interval)

    timings = load_json(DATA_DIR / "timings.json", {})
    steps = {s["name"]: s["seconds"] for s in timings.get("steps", [])}
    if wall is None:
        wall = timings.get("total_seconds")

    data, rows, papers = compute_stats()
    n = data["papers_found"]

    corpus_bytes = sum(dir_size(DATA_DIR / p["folder"])
                       for p in papers if (DATA_DIR / p["folder"]).exists())
    data_dir_bytes = dir_size(DATA_DIR) if DATA_DIR.exists() else 0

    ram = [s[1] for s in samples]
    disk = [s[2] for s in samples]
    summary = {
        "run": {
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "args": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()},
            "python": platform.python_version(),
            "platform": platform.platform(),
            "cpu_count": psutil.cpu_count(),
            "total_ram_bytes": psutil.virtual_memory().total,
            "returncode": rc,
            "measured": not args.report_only,
        },
        "timing": {
            "wall_seconds": wall,
            "steps_seconds": steps,
            "avg_seconds_per_paper": ratio(wall, n) if wall else None,
            "avg_seconds_per_paper_by_step": {k: ratio(v, n) for k, v in steps.items()},
            "single_paper_trial": trial,
        },
        "memory": {
            "metric": MEMORY_METRIC,
            "peak_bytes": max(ram) if ram else None,
            "avg_bytes": mean(ram),
            "samples": len(ram),
            "interval_seconds": args.interval,
        },
        "disk": {
            "peak_extra_bytes_during_run": max(disk) if disk else None,
            "final_corpus_bytes": corpus_bytes,
            "data_dir_bytes": data_dir_bytes,
        },
        "data": data,
    }

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with open(out / "samples.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["seconds", "ram_mb", "disk_extra_mb"])
        for t, r, d in samples:
            w.writerow([round(t, 2), round(r / MB, 2), round(d / MB, 2)])
    with open(out / "papers.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["id"])
        w.writeheader()
        w.writerows(rows)

    fmt = lambda v, f="{:.1f}": "n/a" if v is None else f.format(v)
    print("\n================ TOM TAT ================")
    print(f"Bai tim thay: {n} ({data['versions_total']} phien ban); "
          f"thanh cong: {data['papers_scraped_successfully']} "
          f"({fmt(None if data['overall_success_rate'] is None else data['overall_success_rate'] * 100)}%)")
    print(f"Wall time: {fmt(wall)}s; trung binh/bai: {fmt(summary['timing']['avg_seconds_per_paper'], '{:.2f}')}s; "
          f"tung buoc: {steps}")
    if trial:
        print(f"Mot bai (end-to-end): {trial['seconds']}s")
    print(f"RAM toi da/trung binh: {fmt(None if not ram else max(ram) / MB)} / "
          f"{fmt(None if not ram else mean(ram) / MB)} MB ({MEMORY_METRIC})")
    print(f"O dia tang toi da: {fmt(None if not disk else max(disk) / MB)} MB; "
          f"corpus cuoi: {corpus_bytes / MB:.2f} MB")
    print(f"Kich thuoc TB/bai truoc -> sau xoa anh: "
          f"{fmt(data['avg_paper_bytes_before_cleanup'], '{:,.0f}')} -> "
          f"{fmt(data['avg_paper_bytes_after_cleanup'], '{:,.0f}')} byte")
    print(f"Reference TB/bai: {fmt(data['avg_refs_per_paper'], '{:.2f}')}; "
          f"ty le metadata reference: "
          f"{fmt(None if data['ref_metadata_success_rate_overall'] is None else data['ref_metadata_success_rate_overall'] * 100)}%")
    print(f"Da ghi: {out}/summary.json, samples.csv, papers.csv")
    return 0 if rc in (None, 0) else 1


if __name__ == "__main__":
    sys.exit(main())
