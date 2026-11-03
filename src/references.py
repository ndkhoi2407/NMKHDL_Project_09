"""Giai doan 3b - Tao references.json cho tung bai qua Semantic Scholar (ban nhanh, pipeline).

Dau ra: data/{yymm-id}/references.json + data/references_status.json.
Theo de bai ("keep all crawled references locally"), MAC DINH giu TAT CA reference
Semantic Scholar tra ve; moi muc co truong "arxiv_id" (null neu khong co). Chi
nhung muc co arxiv_id moi thanh hang cua bang `references` o Milestone 3 (loc
o buoc do). Dung --arxiv-only de chi giu reference co arXiv ID (hanh vi cu).
Key: yymm-id cho reference co arXiv ID (ID cu truoc 2007 giu nguyen, vd
hep-th/9901001); "s2-<paperId>" cho reference khac.
Chay lai tiep tuc duoc tu trang thai cu.

Cai tien so voi ban truoc:
  * Semantic Scholar goi theo BATCH (POST /paper/batch, S2_BATCH bai/request).
  * PIPELINE: trong khi mot luong rieng tra ngay arXiv cho cum N, luong chinh
    da goi Semantic Scholar cho cum N+1 (hai server doc lap, khong tranh gioi han).
  * Cum nho (mac dinh 50 bai) => file duoc ghi ra som va deu, khong doi 100 bai.
  * Cache ngay arXiv (data/arxiv_dates_cache.json), batch 100 ID/request.
  * 401/403 (key sai) hoac 429 lien tiep => dung ngay voi thong bao ro, KHONG
    danh dau hang loat bai la loi; cac cum da xong van duoc luu.
  * --s2-dates: bo han buoc goi arXiv (nhanh nhat, ngay co the khac ngay nop v1).

Chay tu thu muc goc project:
    python src/references.py
    python src/references.py --limit 3
    python src/references.py --retry-no-record
    python src/references.py --s2-dates
    python src/references.py --arxiv-only

Bien moi truong (chi ky tu ASCII!):
    S2_API_KEY               khoa Semantic Scholar
    ARXIV_CRAWLER_CONTACT    email dua vao User-Agent
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import arxiv
import requests

DATA_DIR = Path("data")
DISCOVERY = DATA_DIR / "discovery.json"
STATUS_FILE = DATA_DIR / "references_status.json"
ARXIV_CACHE_FILE = DATA_DIR / "arxiv_dates_cache.json"

S2_URL = "https://api.semanticscholar.org/graph/v1/paper/arXiv:{}"
S2_BATCH_URL = "https://api.semanticscholar.org/graph/v1/paper/batch"
S2_FIELDS = ["paperId", "title", "authors", "year", "externalIds",
             "publicationDate", "venue"]
S2_API_KEY = os.environ.get("S2_API_KEY")
S2_DELAY = 1.1 if S2_API_KEY else 3.1
S2_BATCH = 50            # bai / request batch (toi da 500)
CHUNK_SIZE = 50          # bai / cum; = S2_BATCH => 1 request S2 moi cum
ARXIV_DELAY = 3          # arXiv yeu cau >= 3s giua cac request
ARXIV_BATCH = 100
ARXIV_ROUNDS = 2
TIMEOUT = 60
MAX_RETRIES = 5
BATCH_RETRIES = 5
MAX_WAIT = 300
RETRY_CODES = {429, 500, 502, 503, 504}
MAX_BAD_CHUNKS = 3       # so cum lien tiep bi 429/mang truoc khi dung han

_contact = os.environ.get("ARXIV_CRAWLER_CONTACT")
HEADERS = {"User-Agent": "arxiv-milestone1-crawler/1.0 (student project"
                         + (f"; contact: {_contact}" if _contact else "") + ")"}
S2_HEADERS = dict(HEADERS, **({"x-api-key": S2_API_KEY} if S2_API_KEY else {}))
for _k, _v in S2_HEADERS.items():
    try:
        _v.encode("latin-1")
    except UnicodeEncodeError:
        raise SystemExit(f"Header '{_k}' chua ky tu khong phai ASCII: {_v!r}. "
                         "Kiem tra S2_API_KEY / ARXIV_CRAWLER_CONTACT.")

SESSION = requests.Session()
SESSION.headers.update(S2_HEADERS)
_last_s2_start = 0.0
ARXIV_MISSING: set = set()      # chi luong arXiv dung
CACHE_LOCK = threading.Lock()
VERSION_SUFFIX = re.compile(r"v\d+$")


class S2Stop(Exception):
    """Loi khong the tiep tuc (key sai, bi gioi han lien tuc)."""


def s2_wait_turn():
    global _last_s2_start
    remaining = S2_DELAY - (time.monotonic() - _last_s2_start)
    if remaining > 0:
        time.sleep(remaining)
    _last_s2_start = time.monotonic()


def save_json(path: Path, obj, indent=2):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=indent), encoding="utf-8")
    os.replace(tmp, path)


def retry_after_seconds(resp: requests.Response, default: float) -> float:
    try:
        return min(float(resp.headers["Retry-After"]), MAX_WAIT)
    except (KeyError, ValueError):
        return default


def auth_error(status_code: int) -> S2Stop:
    return S2Stop(f"HTTP {status_code} tu Semantic Scholar: "
                  + ("S2_API_KEY sai / chua kich hoat / bi tu choi."
                     if S2_API_KEY else "bi tu choi (hay dat S2_API_KEY)."))


def fetch_s2(arxiv_id: str) -> tuple[dict | None, str]:
    """1 bai (du phong khi batch loi). note='NOT_FOUND' neu S2 khong co bai."""
    params = {"fields": ",".join(f"references.{f}" for f in S2_FIELDS)}
    note = ""
    for attempt in range(1, MAX_RETRIES + 1):
        wait = 5 * 2 ** attempt
        s2_wait_turn()
        try:
            r = SESSION.get(S2_URL.format(arxiv_id), params=params,
                            timeout=TIMEOUT)
            if r.status_code == 200:
                return r.json(), ""
        except (requests.RequestException, ValueError) as exc:
            note = f"{type(exc).__name__}: {exc}"
        else:
            if r.status_code == 404:
                return None, "NOT_FOUND"
            if r.status_code in (401, 403):
                raise auth_error(r.status_code)
            if r.status_code not in RETRY_CODES:
                return None, f"HTTP {r.status_code}"
            note = f"HTTP {r.status_code}"
            wait = retry_after_seconds(r, wait)
        if attempt < MAX_RETRIES:
            time.sleep(wait)
    return None, note or "het so lan thu lai"


def post_s2_batch(ids: list[str]) -> tuple[list | None, str]:
    """Mot request batch -> (list cung thu tu, note); phan tu None = khong co bai."""
    params = {"fields": ",".join(f"references.{f}" for f in S2_FIELDS)}
    body = {"ids": [f"ARXIV:{i}" for i in ids]}
    note = ""
    for attempt in range(1, BATCH_RETRIES + 1):
        wait = min(5 * 2 ** attempt, MAX_WAIT)
        s2_wait_turn()
        try:
            r = SESSION.post(S2_BATCH_URL, params=params, json=body,
                             timeout=TIMEOUT * 2)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and len(data) == len(ids):
                    return data, ""
                return None, "HTTP 200 sai dinh dang"
        except (requests.RequestException, ValueError) as exc:
            note = f"{type(exc).__name__}: {exc}"
        else:
            if r.status_code in (401, 403):
                raise auth_error(r.status_code)
            if r.status_code not in RETRY_CODES:
                return None, f"HTTP {r.status_code}: {r.text[:200]}"
            note = f"HTTP {r.status_code}"
            wait = retry_after_seconds(r, wait)
        if attempt < BATCH_RETRIES:
            print(f"[REFERENCES] S2 batch {note}; doi {wait:.0f}s "
                  f"(lan {attempt}/{BATCH_RETRIES})")
            time.sleep(wait)
    return None, note or "het so lan thu lai"


def fetch_s2_many(ids: list[str]) -> dict:
    """{id: (json | None, note)}."""
    data, note = post_s2_batch(ids)
    if data is not None:
        return {i: ((d, "") if d else (None, "NOT_FOUND"))
                for i, d in zip(ids, data)}
    if len(ids) == 1:
        return {ids[0]: fetch_s2(ids[0])}
    if note.startswith("HTTP") and not note.startswith("HTTP 429"):
        print(f"[REFERENCES] Batch {len(ids)} bai loi ({note}); chia doi")
        mid = len(ids) // 2
        out = fetch_s2_many(ids[:mid])
        out.update(fetch_s2_many(ids[mid:]))
        return out
    return {i: (None, note) for i in ids}


def candidate_refs(refs: list | None, arxiv_only: bool = False) -> dict:
    """{key: {'raw': id arXiv goc khong version | None, 'ref': du lieu S2}}.

    Reference co arXiv ID => key yymm-id. Reference khac => key 's2-<paperId>'
    (bo qua neu --arxiv-only hoac khong co ca paperId lan title)."""
    out = {}
    for n, ref in enumerate(refs or []):
        if not isinstance(ref, dict):
            continue  # retained verbatim in references_raw.json
        raw = (ref.get("externalIds") or {}).get("ArXiv")
        if raw:
            raw_base = VERSION_SUFFIX.sub("", raw.strip())
            key = raw_base if "/" in raw_base else raw_base.replace(".", "-")
            out.setdefault(key, {"raw": raw_base, "ref": ref})
        elif not arxiv_only and (ref.get("paperId") or ref.get("title")):
            key = f"s2-{ref['paperId']}" if ref.get("paperId") else f"ref-{n}"
            out.setdefault(key, {"raw": None, "ref": ref})
    return out


def fetch_arxiv_dates(client: arxiv.Client, raw_ids: list[str], cache: dict) -> dict:
    """{id_goc: 'YYYY-MM-DD'} (ngay nop v1). Chay trong luong rieng."""
    with CACHE_LOCK:
        pending = [i for i in raw_ids if i not in cache and i not in ARXIV_MISSING]
    for _ in range(ARXIV_ROUNDS):
        if not pending:
            break
        for i in range(0, len(pending), ARXIV_BATCH):
            batch = pending[i:i + ARXIV_BATCH]
            search = arxiv.Search(id_list=batch, max_results=len(batch))
            try:
                for r in client.results(search):
                    base = VERSION_SUFFIX.sub("", r.get_short_id())
                    with CACHE_LOCK:
                        cache[base] = r.published.date().isoformat()
            except arxiv.UnexpectedEmptyPageError:
                pass
            except Exception as exc:
                print(f"[REFERENCES] CANH BAO batch arXiv loi "
                      f"({batch[0]}..): {type(exc).__name__}: {exc}")
        with CACHE_LOCK:
            pending = [i for i in pending if i not in cache]
    ARXIV_MISSING.update(pending)
    with CACHE_LOCK:
        return {i: cache[i] for i in raw_ids if i in cache}


def build_references(cands: dict, arxiv_dates: dict) -> tuple[dict, int, int]:
    """Tra ve (references.json, so_ref_arXiv_du_metadata, so_ref_arXiv_dung_ngay_S2)."""
    out, complete, from_s2 = {}, 0, 0
    for key, c in cands.items():
        ref, raw = c["ref"], c["raw"]
        date = arxiv_dates.get(raw) if raw else None
        if not date and ref.get("publicationDate"):
            date = ref["publicationDate"]
            if raw:
                from_s2 += 1
        entry = {
            "arxiv_id": raw,
            "title": ref.get("title"),
            "authors": [a["name"] for a in ref.get("authors") or []
                        if a.get("name")],
            "submission_date": date,
            "venue": ref.get("venue") or None,
            "semantic_scholar_id": ref.get("paperId"),
            "year": ref.get("year"),
        }
        out[key] = entry
        if raw and entry["title"] and entry["authors"] and entry["submission_date"] \
                and entry["semantic_scholar_id"]:
            complete += 1
    return out, complete, from_s2


def preserve_response(paper: dict, response, arxiv_only: bool, lookup_status="ok"):
    out_dir = DATA_DIR / paper["folder"]
    out_dir.mkdir(parents=True, exist_ok=True)
    save_json(out_dir / "references_raw.json", response)
    save_json(out_dir / "references_provenance.json", {
        "request_identifier": f"ARXIV:{paper['id']}", "scope": "publication-level Semantic Scholar response",
        "retrieved_at": datetime.now(timezone.utc).isoformat(), "lookup_status": lookup_status,
        "version_specific": False,
        "versions": {v: {"response": "references_raw.json", "scope": "shared publication-level lookup; not a version-specific bibliography"}
                     for v in paper.get("versions", [])},
        "projection": "arxiv-only" if arxiv_only else "all-identifiable-references"})


def s2_phase(chunk: list, status: dict, arxiv_only: bool) -> tuple[dict, int]:
    """Goi S2 cho cum; ghi ngay cac bai khong co ban ghi / loi.
    Tra ve (fetched {pid: (p, total, cands)}, so_bai_loi_tam_thoi)."""
    ids = [p["id"] for p in chunk]
    results = {}
    for i in range(0, len(ids), S2_BATCH):
        results.update(fetch_s2_many(ids[i:i + S2_BATCH]))

    fetched, transient = {}, 0
    for p in chunk:
        pid = p["id"]
        data, note = results[pid]
        if data is None and note == "NOT_FOUND":
            preserve_response(p, None, arxiv_only, "not_found")
            out_dir = DATA_DIR / p["folder"]
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "references.json").write_text("{}", encoding="utf-8")
            status[pid] = {"status": "no_s2_record", "total_refs": 0,
                           "refs_with_arxiv_id": 0, "refs_metadata_ok": 0}
            print(f"[REFERENCES] {pid}: Semantic Scholar khong co ban ghi")
        elif data is None:
            status[pid] = {"status": "error", "note": note}
            transient += 1
            print(f"[REFERENCES] LOI {pid}: {note}")
        else:
            refs = data.get("references") or []
            # Preserve the complete response before projecting/deduplicating:
            # even references without identifiers or titles remain auditable.
            preserve_response(p, data, arxiv_only)
            fetched[pid] = (p, len(refs), candidate_refs(refs, arxiv_only))
    return fetched, transient


def finalize(fetched: dict, fut, status: dict, arxiv_cache: dict, label: str):
    """Doi ngay arXiv cua cum, ghi references.json tung bai, luu trang thai."""
    dates = {}
    if fut is not None:
        try:
            dates = fut.result()
        except Exception as exc:
            print(f"[REFERENCES] CANH BAO arXiv that bai cho {label}: "
                  f"{type(exc).__name__}: {exc} -> dung ngay cua S2")
    n_ok = 0
    for pid, (p, total, cands) in fetched.items():
        try:
            result, complete, from_s2 = build_references(cands, dates)
            out_dir = DATA_DIR / p["folder"]
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "references.json").write_text(
                json.dumps(result, indent=2, ensure_ascii=False),
                encoding="utf-8")
            status[pid] = {"status": "ok", "total_refs": total,
                           "refs_with_arxiv_id": sum(
                               1 for c in cands.values() if c["raw"]),
                           "refs_saved": len(result),
                           "refs_metadata_ok": complete,
                           "refs_date_from_s2": from_s2}
            n_ok += 1
        except Exception as exc:
            status[pid] = {"status": "error",
                           "note": f"{type(exc).__name__}: {exc}"}
            print(f"[REFERENCES] LOI {pid}: {exc}")
    save_json(STATUS_FILE, status)
    with CACHE_LOCK:
        snap = dict(arxiv_cache)
    save_json(ARXIV_CACHE_FILE, snap, indent=None)
    print(f"[REFERENCES] {label}: da ghi {n_ok}/{len(fetched)} bai "
          f"(cache arXiv: {len(snap)} ID)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--ids", help="comma-separated IDs for a targeted run")
    ap.add_argument("--refresh", action="store_true", help="explicitly refresh selected completed records")
    ap.add_argument("--retry-no-record", action="store_true",
                    help="thu lai bai ma Semantic Scholar tung chua co ban ghi")
    ap.add_argument("--s2-dates", action="store_true",
                    help="khong goi arXiv, dung publicationDate cua Semantic Scholar")
    ap.add_argument("--arxiv-only", action="store_true",
                    help="chi giu reference co arXiv ID (mac dinh: giu tat ca)")
    args = ap.parse_args()

    if not DISCOVERY.exists():
        raise SystemExit(f"Khong tim thay {DISCOVERY.resolve()}. "
                         "Chay discover.py truoc, tu thu muc goc project.")
    print(f"[REFERENCES] S2 key: {'CO' if S2_API_KEY else 'KHONG'}, "
          f"delay={S2_DELAY}s, batch={S2_BATCH}")
    papers = json.loads(DISCOVERY.read_text(encoding="utf-8"))["papers"]
    if args.ids:
        wanted = set(args.ids.split(","))
        papers = [p for p in papers if p["id"] in wanted]
    if args.limit:
        papers = papers[:args.limit]

    status = (json.loads(STATUS_FILE.read_text(encoding="utf-8"))
              if STATUS_FILE.exists() else {})
    arxiv_cache = (json.loads(ARXIV_CACHE_FILE.read_text(encoding="utf-8"))
                   if ARXIV_CACHE_FILE.exists() else {})
    done_states = {"ok"} if args.retry_no_record else {"ok", "no_s2_record"}

    todo, skipped = [], 0
    for p in papers:
        out_file = DATA_DIR / p["folder"] / "references.json"
        if not args.refresh and out_file.exists() and status.get(p["id"], {}).get("status") in done_states:
            skipped += 1
        else:
            todo.append(p)
    print(f"[REFERENCES] Bo qua {skipped} bai da xong; con {len(todo)} bai.")

    client = arxiv.Client(page_size=ARXIV_BATCH, delay_seconds=ARXIV_DELAY,
                          num_retries=3)
    pool = ThreadPoolExecutor(max_workers=1)   # 1 luong => tuan thu 1 request/3s cua arXiv
    prev = None                                # (fetched, fut, label) cua cum truoc
    bad_chunks, rc = 0, 0
    try:
        try:
            for c0 in range(0, len(todo), CHUNK_SIZE):
                chunk = todo[c0:c0 + CHUNK_SIZE]
                label = f"Cum {c0 // CHUNK_SIZE + 1}/{-(-len(todo) // CHUNK_SIZE)}"
                t0 = time.monotonic()

                fetched, transient = s2_phase(chunk, status, args.arxiv_only)
                save_json(STATUS_FILE, status)
                bad_chunks = bad_chunks + 1 if transient == len(chunk) else 0

                raw_ids = sorted({c["raw"] for _, _, cands in fetched.values()
                                  for c in cands.values() if c["raw"]})
                fut = None
                if raw_ids and not args.s2_dates:
                    fut = pool.submit(fetch_arxiv_dates, client, raw_ids,
                                      arxiv_cache)
                print(f"[REFERENCES] {label}: S2 xong sau "
                      f"{time.monotonic() - t0:.0f}s, {len(raw_ids)} ID arXiv")

                if prev:                       # ghi cum truoc trong luc cum nay dang hoi arXiv
                    p_fetched, p_fut, p_label = prev
                    prev = None
                    finalize(p_fetched, p_fut, status, arxiv_cache, p_label)
                prev = (fetched, fut, label)

                if bad_chunks >= MAX_BAD_CHUNKS:
                    raise S2Stop(f"{MAX_BAD_CHUNKS} cum lien tiep bi loi/gioi han "
                                 "toc do. Doi vai phut roi chay lai.")
        except S2Stop as exc:
            print(f"\n[REFERENCES] DUNG: {exc}")
            rc = 1
        if prev:                               # luon ghi not cum cuoi / cum dang do
            finalize(*prev[:2], status, arxiv_cache, prev[2])
            prev = None
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
        save_json(STATUS_FILE, status)

    counts = {}
    for s in status.values():
        counts[s["status"]] = counts.get(s["status"], 0) + 1
    print("[REFERENCES] Xong:", counts)
    return rc


if __name__ == "__main__":
    sys.exit(main())
