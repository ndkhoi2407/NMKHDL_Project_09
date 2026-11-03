"""Giai doan 1 - Entry Discovery.

Tao danh sach ID trong khoang duoc giao, hoi arXiv API xem ID nao ton tai,
xac dinh so phien ban moi bai va ghi ket qua ra data/discovery.json.

Vi du chay thu 10 bai:
    python src/discover.py --prefix 2310 --start 1 --end 10

Chay tiep duoc (resume):
- Tien do duoc luu vao file dau ra sau moi CHECKPOINT_EVERY batch va khi bi
  ngat (Ctrl+C), nen chay lai se KHONG hoi lai nhung ID da tim thay.
- ID da duoc xac nhan "khong ton tai" o lan chay truoc cung duoc bo qua.
  Dung --recheck-missing de hoi lai chung, --fresh de bo het ket qua cu.
- Bai da tim thay khong bao gio bi mat khi chay lai (ket qua duoc gop).

Luu y:
- Chi dung API cua arXiv (id_list), tuan tu 1 ket noi, nghi >= 3 giay/request.
- "published" la ngay nop v1; "updated" CHI la ngay cua phien ban moi nhat.
  Lich su ngay cua tung phien ban (revised_dates) khong co trong ket qua
  nay, phai lay o buoc metadata.
- Can Python >= 3.9.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path

import arxiv

BATCH_SIZE = 50          # so ID moi lan goi API
DELAY_SECONDS = 3        # arXiv yeu cau nghi >= 3 giay giua cac request
MAX_ROUNDS = 3           # so lan hoi lai cac ID chua thay / bi loi
CHECKPOINT_EVERY = 10    # ghi tien do sau moi N batch (10 batch ~ 500 ID)
DEFAULT_OUTPUT = Path("data/discovery.json")

VERSION_RE = re.compile(r"^(?P<base>.+)v(?P<ver>\d+)$")


def build_id_list(prefix: str, start: int, end: int) -> list[str]:
    """Sinh ID theo dinh dang moi (tu 1501 tro di: 5 chu so, vd 2310.00001).

    Giai doan 0704-1412 dung 4 chu so (vd 1203.0001). Doi width neu can.
    """
    width = 5 if int(prefix) >= 1501 else 4
    return [f"{prefix}.{n:0{width}d}" for n in range(start, end + 1)]


def chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def write_json_atomic(path: Path, obj: dict):
    """Ghi qua file tam roi thay the, de crash giua chung khong lam hong file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def load_previous(path: Path, prefix: str) -> dict | None:
    """Doc ket qua lan truoc (neu co va cung thang) de chay tiep."""
    if not path.exists():
        return None
    try:
        prev = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print("[DISCOVERY] CANH BAO: khong doc duoc file cu, tim lai tu dau.")
        return None
    if prev.get("range", {}).get("prefix") != prefix:
        print("[DISCOVERY] File cu thuoc thang khac, bo qua.")
        return None
    return prev


def query_batch(client: arxiv.Client, ids: list[str]) -> dict:
    """Tra ve {base_id: thong tin bai} cho cac ID tim thay trong batch."""
    search = arxiv.Search(id_list=ids, max_results=len(ids))
    found = {}
    try:
        for r in client.results(search):
            m = VERSION_RE.match(r.get_short_id())
            if not m:
                continue
            base, latest = m.group("base"), int(m.group("ver"))
            found[base] = {
                "id": base,
                "folder": base.replace(".", "-"),
                "latest_version": latest,
                # arXiv danh so lien tuc v1..vN nen co N phien ban
                "versions": [f"v{i}" for i in range(1, latest + 1)],
                "title": " ".join(r.title.split()),
                "authors": [a.name for a in r.authors],
                "venue": getattr(r, "journal_ref", None),
                "metadata_identifier": r.get_short_id(),
                "published": r.published.date().isoformat(),
                "updated": r.updated.date().isoformat(),
            }
    except arxiv.UnexpectedEmptyPageError:
        # Batch rong. Co the do ID khong ton tai, nhung cung co the do API
        # tra trang rong tam thoi -> de vong hoi lai (MAX_ROUNDS) xac nhan.
        pass
    return found


def discover(prefix: str, start: int, end: int, previous: dict | None = None,
             recheck_missing: bool = False, on_checkpoint=None) -> dict:
    ids = build_id_list(prefix, start, end)
    id_set = set(ids)
    # Client tu thuc thi delay giua cac request nen khong can time.sleep them.
    client = arxiv.Client(page_size=BATCH_SIZE, delay_seconds=DELAY_SECONDS,
                          num_retries=3)

    # --- Nap ket qua cu: bai da tim thay + ID da xac nhan khong ton tai
    papers: dict = {}
    confirmed_missing: set = set()
    if previous:
        papers = {p["id"]: p for p in previous.get("papers", [])
                  if p["id"] in id_set}
        if not recheck_missing:
            confirmed_missing = {i for i in previous.get("not_found", [])
                                 if i in id_set and i not in papers}
    reused_found, reused_missing = len(papers), len(confirmed_missing)

    errors: dict = {}      # id -> loi cua lan hoi gan nhat (neu request loi)
    pending = [i for i in ids if i not in papers and i not in confirmed_missing]
    found_round1 = None
    rounds_used = batches_done = 0
    t0 = time.perf_counter()

    if previous:
        print(f"[DISCOVERY] Chay tiep: giu {reused_found} bai da tim thay, "
              f"{reused_missing} ID da xac nhan khong ton tai, "
              f"con {len(pending)}/{len(ids)} ID can hoi.")

    def build_result(complete: bool, not_found: list, failed_ids: list) -> dict:
        recovered = (len(papers) - found_round1) if found_round1 is not None else 0
        return {
            "complete": complete,
            "range": {"prefix": prefix, "start": start, "end": end},
            "stats": {
                "ids_in_range": len(ids),
                "found": len(papers),
                "not_found": len(not_found),
                "failed_ids": len(failed_ids),
                "recovered_on_retry": recovered,
                "rounds_used": rounds_used,
                "total_versions": sum(p["latest_version"] for p in papers.values()),
                "reused_found": reused_found,
                "reused_not_found": reused_missing,
                "seconds": round(time.perf_counter() - t0, 2),  # chi lan chay nay
            },
            "papers": [papers[i] for i in ids if i in papers],
            "not_found": not_found,
            "failed": [{"id": i, "error": errors[i]} for i in failed_ids],
        }

    try:
        for round_no in range(1, MAX_ROUNDS + 1):
            if not pending:
                break
            rounds_used = round_no
            for batch in chunks(pending, BATCH_SIZE):
                try:
                    papers.update(query_batch(client, batch))
                    for i in batch:
                        errors.pop(i, None)
                    print(f"[DISCOVERY] vong {round_no} {batch[0]}..{batch[-1]}: "
                          f"tong da tim thay {len(papers)}")
                except Exception as exc:  # loi mang, HTTP 5xx...
                    for i in batch:
                        errors[i] = str(exc)
                    print(f"[DISCOVERY] LOI vong {round_no} "
                          f"{batch[0]}..{batch[-1]}: {exc}")
                batches_done += 1
                if on_checkpoint and batches_done % CHECKPOINT_EVERY == 0:
                    on_checkpoint(build_result(
                        False, [i for i in ids if i in confirmed_missing], []))
            if round_no == 1:
                found_round1 = len(papers)
            pending = [i for i in pending if i not in papers]
    except KeyboardInterrupt:
        if on_checkpoint:
            on_checkpoint(build_result(
                False, [i for i in ids if i in confirmed_missing], []))
        print("[DISCOVERY] Bi ngat. Da luu tien do, chay lai de tiep tuc.")
        raise SystemExit(130)

    # Con lai sau MAX_ROUNDS lan hoi:
    #  - lan hoi cuoi bi loi          => failed (chua biet ton tai hay khong)
    #  - lan hoi cuoi OK nhung rong   => khong ton tai (xac nhan)
    failed_ids = [i for i in pending if i in errors]
    confirmed_missing.update(i for i in pending if i not in errors)
    not_found = [i for i in ids if i in confirmed_missing]
    return build_result(True, not_found, failed_ids)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", required=True, help="yymm, vd 2310")
    ap.add_argument("--start", type=int, required=True)
    ap.add_argument("--end", type=int, required=True)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--fresh", action="store_true",
                    help="bo ket qua cu, tim lai tu dau")
    ap.add_argument("--recheck-missing", action="store_true",
                    help="hoi lai cac ID truoc do duoc xac nhan khong ton tai")
    args = ap.parse_args()

    previous = None if args.fresh else load_previous(args.output, args.prefix)
    result = discover(args.prefix, args.start, args.end, previous,
                      args.recheck_missing,
                      on_checkpoint=lambda r: write_json_atomic(args.output, r))
    write_json_atomic(args.output, result)
    print("[DISCOVERY] Thong ke:", result["stats"])
    print(f"[DISCOVERY] Da luu {args.output}")


if __name__ == "__main__":
    main()
