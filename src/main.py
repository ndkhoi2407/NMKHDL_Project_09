"""Chay toan bo pipeline Milestone 1 tu dau den cuoi (end-to-end).

Cac buoc, moi buoc la mot chuong trinh rieng, chay lan luot:
    discover    discover.py          tim ID ton tai, so phien ban moi bai
    download    download_sources.py  tai va giai nen source tung phien ban
    clean       process_sources.py   xoa file anh nhi phan (don lai ban cu)
    metadata    metadata.py          tao metadata.json
    references  references.py        tao references.json (Semantic Scholar)

Chay tiep duoc: moi buoc deu bo qua phan da xong. Rieng buoc discover se
tu dong bo qua neu data/discovery.json da day du cho khoang ID yeu cau
(khong con loi). Dung --fresh-discover de tim lai tu dau.

Thoi gian tung buoc duoc ghi vao <workdir>/data/timings.json de benchmark.py
va bao cao su dung. Mot buoc loi (ma thoat khac 0) thi dung ngay; chay lai
se tiep tuc tu cho cu.

Vi du:
    python src/main.py --prefix 2607 --start 3694 --end 8693
    python src/main.py --prefix 2607 --start 3694 --end 3713 --limit 20
    python src/main.py --skip discover,download,clean       # chi lam metadata + references
    python src/main.py --skip discover,download             # tai xong roi, lam tiep phan con lai
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
STEPS = [
    ("discover", "discover.py"),
    ("download", "download_sources.py"),
    ("clean", "process_sources.py"),
    ("metadata", "metadata.py"),
    ("references", "references.py"),
]
STATUS_FILES = {
    "download": "download_status.json",
    "metadata": "metadata_status.json",
    "references": "references_status.json",
}


def build_command(step: str, script: str, a: argparse.Namespace) -> list[str]:
    cmd = [sys.executable, str(SRC_DIR / script)]
    if step == "discover":
        cmd += ["--prefix", a.prefix, "--start", str(a.start), "--end", str(a.end)]
        if a.fresh_discover:
            cmd.append("--fresh")
    if step in ("download", "metadata", "references") and a.limit:
        cmd += ["--limit", str(a.limit)]
    return cmd


def discovery_is_complete(workdir: Path, a: argparse.Namespace) -> bool:
    """discovery.json da day du cho khoang yeu cau (hoan tat, khong con ID loi)?"""
    try:
        d = json.loads((workdir / "data" / "discovery.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    rng, stats = d.get("range", {}), d.get("stats", {})
    complete = d.get("complete", "stats" in d)   # file cu khong co co 'complete'
    return bool(complete
                and stats.get("failed_ids", 1) == 0
                and rng.get("prefix") == a.prefix
                and rng.get("start", 1 << 60) <= a.start
                and a.end <= rng.get("end", -1))


def count_errors(path: Path):
    """So muc co status 'error' trong file status (None neu chua co file)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return sum(1 for v in data.values() if v.get("status") == "error")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--prefix", help="yymm cua khoang ID duoc giao, vd 2607")
    ap.add_argument("--start", type=int, help="so thu tu ID dau, vd 3694")
    ap.add_argument("--end", type=int, help="so thu tu ID cuoi, vd 8693")
    ap.add_argument("--limit", type=int, default=None,
                    help="chi xu ly N bai dau (de chay thu)")
    ap.add_argument("--fresh-discover", action="store_true",
                    help="bo ket qua discovery cu va tim lai tu dau")
    ap.add_argument("--skip", default="",
                    help="cac buoc bo qua, cach nhau dau phay: "
                         + ",".join(n for n, _ in STEPS))
    ap.add_argument("--workdir", default=".",
                    help="thu muc chay (du lieu ghi vao <workdir>/data); mac dinh la thu muc hien tai")
    ap.add_argument("--timings", default=None,
                    help="file ghi thoi gian (mac dinh <workdir>/data/timings.json)")
    a = ap.parse_args()

    skip = {s.strip() for s in a.skip.split(",") if s.strip()}
    unknown = skip - {n for n, _ in STEPS}
    if unknown:
        ap.error(f"buoc khong ton tai: {sorted(unknown)}")
    if "discover" not in skip and None in (a.prefix, a.start, a.end):
        ap.error("can --prefix, --start, --end (hoac --skip discover neu da co discovery.json)")

    workdir = Path(a.workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    timings_path = Path(a.timings) if a.timings else workdir / "data" / "timings.json"

    records, ok, remaining = [], True, {}
    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    t_all = time.perf_counter()
    try:
        for name, script in STEPS:
            if name in skip:
                print(f"\n===== [{name}] bo qua", flush=True)
                continue
            if (name == "discover" and not a.fresh_discover
                    and discovery_is_complete(workdir, a)):
                print(f"\n===== [discover] bo qua: data/discovery.json da day du cho "
                      f"khoang nay (them --fresh-discover de tim lai tu dau)", flush=True)
                records.append({"name": name, "seconds": 0.0, "returncode": 0,
                                "skipped": True})
                continue
            cmd = build_command(name, script, a)
            print(f"\n===== [{name}] {' '.join(cmd[1:])}", flush=True)
            t0 = time.perf_counter()
            rc = subprocess.call(cmd, cwd=workdir)
            seconds = time.perf_counter() - t0
            records.append({"name": name, "seconds": round(seconds, 2),
                            "returncode": rc})
            print(f"===== [{name}] xong sau {seconds:.1f}s (ma thoat {rc})", flush=True)
            if rc != 0:
                ok = False
                break
    except KeyboardInterrupt:
        ok = False
        print("\n[MAIN] Bi ngat boi nguoi dung. Chay lai de tiep tuc.")
    finally:
        total = time.perf_counter() - t_all
        remaining = {step: count_errors(workdir / "data" / fname)
                     for step, fname in STATUS_FILES.items()}
        timings_path.parent.mkdir(parents=True, exist_ok=True)
        timings_path.write_text(json.dumps({
            "args": {k: v for k, v in vars(a).items()},
            "started_at": started_at,
            "total_seconds": round(total, 2),
            "success": ok,
            "remaining_errors": remaining,
            "steps": records,
        }, indent=2), encoding="utf-8")

    print(f"\n[MAIN] {'HOAN TAT' if ok else 'DUNG VI LOI'} sau {total:.1f}s "
          f"-> {timings_path}")
    pending_errors = {k: v for k, v in remaining.items() if v}
    if pending_errors:
        print(f"[MAIN] CON MUC LOI CAN THU LAI: {pending_errors}. "
              "Chay lai lenh nay de thu lai cac muc do.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
