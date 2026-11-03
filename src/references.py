"""Giai doan 3b - Tao references.json cho tung bai qua Semantic Scholar.

Voi moi bai trong data/discovery.json:
  1. Goi Semantic Scholar lay danh sach references.
  2. Giu cac reference co arXiv ID, chuan hoa ve dang yymm-id
     (ID cu truoc 2007 nhu hep-th/9901001 giu nguyen).
  3. Lay ngay nop (submission_date) tu arXiv API; neu thieu thi dung
     publicationDate cua Semantic Scholar.
  4. Ghi data/{yymm-id}/references.json va thong ke vao
     data/references_status.json.

Xu ly theo cum CHUNK_SIZE bai: goi Semantic Scholar cho ca cum, roi tra ngay
arXiv cho TOAN BO ID (da loai trung) cua cum bang cac batch lon, thay vi goi
rieng cho tung bai. Cach nay giam so request arXiv di rat nhieu.

Chay tu thu muc goc project:
    python src/references.py
    python src/references.py --limit 3
    python src/references.py --retry-no-record   # thu lai bai S2 chua co ban ghi

Tuy chon: dat bien moi truong de tang gioi han / ghi User-Agent:
    S2_API_KEY               khoa Semantic Scholar (tang gioi han request)
    ARXIV_CRAWLER_CONTACT    email dua vao User-Agent (khong ghi vao code)
    PowerShell:  $env:S2_API_KEY="your-key"
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from dotenv import load_dotenv

import arxiv
import requests

load_dotenv()  # Doc S2_API_KEY tu file .env neu co

DATA_DIR = Path("data")
DISCOVERY = DATA_DIR / "discovery.json"
STATUS_FILE = DATA_DIR / "references_status.json"

S2_URL = "https://api.semanticscholar.org/graph/v1/paper/arXiv:{}"
S2_FIELDS = ["paperId", "title", "authors", "year", "externalIds",
             "publicationDate"]
S2_API_KEY = os.environ.get("S2_API_KEY")
# Khong co key: toi da 100 request/5 phut => cach nhau >= 3s. Co key: 1 request/s.
S2_DELAY = 1.1 if S2_API_KEY else 3.1
ARXIV_DELAY = 3
ARXIV_BATCH = 50
ARXIV_ROUNDS = 2        # so lan hoi arXiv cho ID chua thay (API doi khi tra thieu)
CHUNK_SIZE = 100        # so bai xu ly truoc moi lan tra ngay arXiv
TIMEOUT = 60
MAX_RETRIES = 5             # tong so lan thu, tinh ca lan dau
BACKOFF_BASE = 2.0           # 2, 4, 8, 16... giay (tru khi Retry-After chi dinh)
MAX_WAIT = 300               # gioi han thoi gian cho moi lan
JITTER = 1.0                 # them ngau nhien 0..1 giay tranh nhieu client dong bo
RETRY_CODES = {429, 500, 502, 503, 504}

_contact = os.environ.get("ARXIV_CRAWLER_CONTACT")
HEADERS = {"User-Agent": "arxiv-milestone1-crawler/1.0 (student project"
                         + (f"; contact: {_contact}" if _contact else "") + ")"}
S2_HEADERS = dict(HEADERS, **({"x-api-key": S2_API_KEY} if S2_API_KEY else {}))

SESSION = requests.Session()
SESSION.headers.update(S2_HEADERS)
_last_s2_start = 0.0

VERSION_SUFFIX = re.compile(r"v\d+$")


def s2_wait_turn():
    """Giu khoang cach >= S2_DELAY giua cac request Semantic Scholar (tu luc bat dau)."""
    global _last_s2_start
    remaining = S2_DELAY - (time.monotonic() - _last_s2_start)
    if remaining > 0:
        time.sleep(remaining)
    _last_s2_start = time.monotonic()


def save_status(status: dict):
    """Ghi qua file tam roi thay the, de crash giua chung khong lam hong file."""
    tmp = STATUS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(status, indent=2), encoding="utf-8")
    os.replace(tmp, STATUS_FILE)


def retry_after_seconds(resp: requests.Response, fallback: float) -> float:
    """Doc Retry-After dang so giay hoac HTTP-date; fallback neu khong co."""
    value = resp.headers.get("Retry-After")
    if not value:
        return min(fallback, MAX_WAIT)
    try:
        return max(0.0, min(float(value), MAX_WAIT))
    except ValueError:
        try:
            when = parsedate_to_datetime(value)
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            seconds = (when - datetime.now(timezone.utc)).total_seconds()
            return max(0.0, min(seconds, MAX_WAIT))
        except (TypeError, ValueError, OverflowError):
            return min(fallback, MAX_WAIT)


def fetch_s2(arxiv_id: str) -> tuple[dict | None, str]:
    """Tra ve (JSON, note). Dung exponential backoff cho loi tam thoi."""
    params = {"fields": ",".join(f"references.{f}" for f in S2_FIELDS)}
    url = S2_URL.format(arxiv_id)
    note = ""

    for attempt in range(1, MAX_RETRIES + 1):
        # Backoff tang theo cap so nhan 2; retry-after cua server duoc uu tien.
        fallback_wait = min(BACKOFF_BASE * (2 ** (attempt - 1)), MAX_WAIT)
        s2_wait_turn()
        try:
            response = SESSION.get(url, params=params, timeout=TIMEOUT)
            if response.status_code == 200:
                try:
                    return response.json(), ""
                except ValueError as exc:
                    note = f"JSON khong hop le: {exc}"
                    # Phan hoi 200 nhung JSON hong: thu lai co gioi han.
            elif response.status_code == 404:
                return None, "NOT_FOUND"
            elif response.status_code not in RETRY_CODES:
                # 401/403/400... thuong khong tu het; khong retry vo ich.
                return None, f"HTTP {response.status_code}: {response.text[:300]}"
            else:
                note = f"HTTP {response.status_code}"
                fallback_wait = retry_after_seconds(response, fallback_wait)
        except (requests.RequestException, ValueError) as exc:
            note = f"{type(exc).__name__}: {exc}"

        if attempt < MAX_RETRIES:
            wait = min(fallback_wait + random.uniform(0, JITTER), MAX_WAIT)
            print(f"[REFERENCES] {arxiv_id}: {note}; thu lai "
                  f"{attempt + 1}/{MAX_RETRIES} sau {wait:.1f}s")
            time.sleep(wait)

    return None, note or "het so lan thu lai"


def candidate_refs(refs: list | None) -> dict:
    """{key_chuan_hoa: {'raw': id_goc_khong_version, 'ref': du_lieu_S2}}."""
    out = {}
    for ref in refs or []:
        raw = (ref.get("externalIds") or {}).get("ArXiv")
        if not raw:
            continue
        raw_base = VERSION_SUFFIX.sub("", raw.strip())
        key = raw_base if "/" in raw_base else raw_base.replace(".", "-")
        out.setdefault(key, {"raw": raw_base, "ref": ref})
    return out


def fetch_arxiv_dates(client: arxiv.Client, raw_ids: list[str]) -> dict:
    """{id_goc: 'YYYY-MM-DD'} cho cac ID arXiv tim thay (ngay nop v1).

    Client tu giu delay giua cac request nen khong sleep them. ID chua thay
    duoc hoi lai (API doi khi tra thieu); batch loi mang bi bo qua, khi do
    reference dung ngay publicationDate cua Semantic Scholar.
    """
    dates: dict = {}
    pending = list(raw_ids)
    for _ in range(ARXIV_ROUNDS):
        if not pending:
            break
        for i in range(0, len(pending), ARXIV_BATCH):
            batch = pending[i:i + ARXIV_BATCH]
            search = arxiv.Search(id_list=batch, max_results=len(batch))
            try:
                for r in client.results(search):
                    base = VERSION_SUFFIX.sub("", r.get_short_id())
                    dates[base] = r.published.date().isoformat()
            except arxiv.UnexpectedEmptyPageError:
                pass
            except Exception as exc:
                print(f"[REFERENCES] CANH BAO batch arXiv loi "
                      f"({batch[0]}..): {type(exc).__name__}: {exc}")
        pending = [i for i in raw_ids if i not in dates]
    return dates


def build_references(cands: dict, arxiv_dates: dict) -> tuple[dict, int, int]:
    """Tra ve (references.json, so_ref_du_metadata, so_ref_dung_ngay_S2)."""
    out, complete, from_s2 = {}, 0, 0
    for key, c in cands.items():
        ref = c["ref"]
        if not ref.get("paperId"):
            continue  # khong co Semantic Scholar ID => bo qua
        date = arxiv_dates.get(c["raw"])
        if not date and ref.get("publicationDate"):
            date, from_s2 = ref["publicationDate"], from_s2 + 1
        entry = {
            "title": ref.get("title"),
            "authors": [a["name"] for a in ref.get("authors") or []
                        if a.get("name")],
            "submission_date": date,
            "semantic_scholar_id": ref["paperId"],
            "year": ref.get("year"),
        }
        out[key] = entry
        if entry["title"] and entry["authors"] and entry["submission_date"]:
            complete += 1
    return out, complete, from_s2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--retry-no-record", action="store_true",
                    help="thu lai bai ma Semantic Scholar tung chua co ban ghi")
    args = ap.parse_args()

    if not DISCOVERY.exists():
        raise SystemExit(f"Khong tim thay {DISCOVERY.resolve()}. "
                         "Chay discover.py truoc, tu thu muc goc project.")
    papers = json.loads(DISCOVERY.read_text(encoding="utf-8"))["papers"]
    if args.limit:
        papers = papers[:args.limit]

    status = (json.loads(STATUS_FILE.read_text(encoding="utf-8"))
              if STATUS_FILE.exists() else {})
    done_states = {"ok"} if args.retry_no_record else {"ok", "no_s2_record"}

    todo = []
    for p in papers:
        out_file = DATA_DIR / p["folder"] / "references.json"
        if out_file.exists() and status.get(p["id"], {}).get("status") in done_states:
            print(f"[REFERENCES] Bo qua {p['id']} (da xong)")
        else:
            todo.append(p)

    client = arxiv.Client(page_size=ARXIV_BATCH, delay_seconds=ARXIV_DELAY,
                          num_retries=3)
    try:
        for c0 in range(0, len(todo), CHUNK_SIZE):
            chunk = todo[c0:c0 + CHUNK_SIZE]

            # Buoc 1: Semantic Scholar cho ca cum
            fetched = {}   # pid -> (paper, tong_refs, cands)
            for p in chunk:
                pid = p["id"]
                data, note = fetch_s2(pid)
                if data is None and note == "NOT_FOUND":
                    out_dir = DATA_DIR / p["folder"]
                    out_dir.mkdir(parents=True, exist_ok=True)
                    (out_dir / "references.json").write_text("{}", encoding="utf-8")
                    status[pid] = {"status": "no_s2_record", "total_refs": 0,
                                   "refs_with_arxiv_id": 0, "refs_metadata_ok": 0}
                    print(f"[REFERENCES] {pid}: Semantic Scholar khong co ban ghi")
                elif data is None:
                    status[pid] = {"status": "error", "note": note}
                    print(f"[REFERENCES] LOI {pid}: {note}")
                else:
                    refs = data.get("references") or []
                    fetched[pid] = (p, len(refs), candidate_refs(refs))

            # Buoc 2: tra ngay arXiv cho moi ID cua cum (loai trung, batch lon)
            raw_ids = sorted({c["raw"] for _, _, cands in fetched.values()
                              for c in cands.values()
                              if c["ref"].get("paperId")})  # ref bi bo qua thi khong can ngay
            dates = fetch_arxiv_dates(client, raw_ids) if raw_ids else {}

            # Buoc 3: ghi references.json tung bai
            for pid, (p, total, cands) in fetched.items():
                try:
                    result, complete, from_s2 = build_references(cands, dates)
                    out_dir = DATA_DIR / p["folder"]
                    out_dir.mkdir(parents=True, exist_ok=True)
                    (out_dir / "references.json").write_text(
                        json.dumps(result, indent=2, ensure_ascii=False),
                        encoding="utf-8")
                    status[pid] = {"status": "ok", "total_refs": total,
                                   "refs_with_arxiv_id": len(cands),
                                   "refs_saved": len(result),
                                   "refs_metadata_ok": complete,
                                   "refs_date_from_s2": from_s2}
                    print(f"[REFERENCES] Saved {pid}: {total} refs, "
                          f"{len(cands)} co arXiv ID, {complete} du metadata")
                except Exception as exc:
                    status[pid] = {"status": "error",
                                   "note": f"{type(exc).__name__}: {exc}"}
                    print(f"[REFERENCES] LOI {pid}: {exc}")

            save_status(status)   # sau moi cum; chay lai se tiep tuc tu day
    finally:
        save_status(status)

    counts = {}
    for s in status.values():
        counts[s["status"]] = counts.get(s["status"], 0) + 1
    print("[REFERENCES] Xong:", counts)


if __name__ == "__main__":
    main()