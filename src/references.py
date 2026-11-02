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
import re
import time
from pathlib import Path

import arxiv
import requests

DATA_DIR = Path("data")
DISCOVERY = DATA_DIR / "discovery.json"
STATUS_FILE = DATA_DIR / "references_status.json"

S2_URL = "https://api.semanticscholar.org/graph/v1/paper/arXiv:{}"
S2_FIELDS = ["paperId", "title", "authors", "year", "externalIds",
             "publicationDate"]
S2_API_KEY = os.environ.get("S2_API_KEY")
# Khong co key: toi da 100 request/5 phut => cach nhau >= 3s. Co key: 1 request/s.
S2_DELAY = 3.0 if S2_API_KEY else 3.1
ARXIV_DELAY = 3
ARXIV_BATCH = 50
ARXIV_ROUNDS = 2        # so lan hoi arXiv cho ID chua thay (API doi khi tra thieu)
CHUNK_SIZE = 50      # so bai xu ly truoc moi lan tra ngay arXiv
TIMEOUT = 60
MAX_RETRIES = 5
MAX_WAIT = 300
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


def retry_after_seconds(resp: requests.Response, default: float) -> float:
    try:
        return min(float(resp.headers["Retry-After"]), MAX_WAIT)
    except (KeyError, ValueError):
        return default


def fetch_s2(arxiv_id: str) -> tuple[dict | None, str]:
    """Tra ve (json, note). note='NOT_FOUND' neu Semantic Scholar khong co bai."""
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
        except (requests.RequestException, ValueError) as exc:  # ke ca JSON hong
            note = f"{type(exc).__name__}: {exc}"
        else:
            if r.status_code == 404:
                return None, "NOT_FOUND"
            if r.status_code not in RETRY_CODES:
                return None, f"HTTP {r.status_code}"
            note = f"HTTP {r.status_code}"
            wait = retry_after_seconds(r, wait)
        if attempt < MAX_RETRIES:
            time.sleep(wait)
    return None, note or "het so lan thu lai"

def fetch_s2_batch(arxiv_ids: list[str]) -> dict[str, dict]:
    """Lay Semantic Scholar data cho nhieu paper trong mot request Batch API."""
    if not arxiv_ids:
        return {}

    url = "https://api.semanticscholar.org/graph/v1/paper/batch"

    params = {
        "fields": "paperId,title,authors,year,externalIds,publicationDate,"
                  "references.paperId,references.title,references.authors,"
                  "references.year,references.externalIds,references.publicationDate"
    }

    payload = {
        "ids": [f"ARXIV:{pid}" for pid in arxiv_ids]
    }

    max_attempts = 8

    for attempt in range(max_attempts):
        s2_wait_turn()

        try:
            r = SESSION.post(
                url,
                params=params,
                json=payload,
                timeout=TIMEOUT
            )

            if r.status_code == 200:
                data = r.json()

                return {
                    pid: item
                    for pid, item in zip(arxiv_ids, data)
                    if item is not None
                }

            # Semantic Scholar rate limit
            if r.status_code == 429:
                retry_after = r.headers.get("Retry-After")

                if retry_after:
                    try:
                        wait_seconds = float(retry_after)
                    except ValueError:
                        wait_seconds = 60 * (2 ** attempt)
                else:
                    wait_seconds = 60 * (2 ** attempt)

                wait_seconds = min(wait_seconds, MAX_WAIT)

                print(
                    f"[REFERENCES] Batch S2 bi rate limit (HTTP 429). "
                    f"Cho {wait_seconds:.1f}s roi thu lai "
                    f"(lan {attempt + 1}/{max_attempts})..."
                )

                time.sleep(wait_seconds)
                continue

            # Loi server tam thoi
            if r.status_code in {500, 502, 503, 504}:
                wait_seconds = min(10 * (2 ** attempt), MAX_WAIT)

                print(
                    f"[REFERENCES] Batch S2 loi HTTP {r.status_code}. "
                    f"Cho {wait_seconds:.1f}s roi thu lai "
                    f"(lan {attempt + 1}/{max_attempts})..."
                )

                time.sleep(wait_seconds)
                continue

            # Loi khong nen retry
            print(f"[REFERENCES] Batch S2 loi: HTTP {r.status_code}")
            raise RuntimeError(
                f"Semantic Scholar Batch API failed with HTTP {r.status_code}"
            )

        except requests.RequestException as exc:
            wait_seconds = min(10 * (2 ** attempt), MAX_WAIT)

            print(
                f"[REFERENCES] Batch S2 loi mang: {type(exc).__name__}: {exc}. "
                f"Cho {wait_seconds:.1f}s roi thu lai "
                f"(lan {attempt + 1}/{max_attempts})..."
            )

            time.sleep(wait_seconds)

        except ValueError as exc:
            print(f"[REFERENCES] Batch S2 tra ve JSON khong hop le: {exc}")
            raise RuntimeError("Semantic Scholar returned invalid JSON")

    raise RuntimeError(
        f"Semantic Scholar Batch API van that bai sau {max_attempts} lan thu."
    )

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

    client = arxiv.Client(page_size=ARXIV_BATCH, delay_seconds=ARXIV_DELAY, num_retries=0)
    try:
        for c0 in range(0, len(todo), CHUNK_SIZE):
            chunk = todo[c0:c0 + CHUNK_SIZE]

            # Buoc 1: Semantic Scholar Batch API cho ca cum
            fetched = {}   # pid -> (paper, tong_refs, cands)

            batch_ids = [p["id"] for p in chunk]
            batch_data = fetch_s2_batch(batch_ids)

            for p in chunk:
                pid = p["id"]
                data = batch_data.get(pid)

                if data is None:
                    out_dir = DATA_DIR / p["folder"]
                    out_dir.mkdir(parents=True, exist_ok=True)
                    (out_dir / "references.json").write_text("{}", encoding="utf-8")
                    status[pid] = {
                        "status": "no_s2_record",
                        "total_refs": 0,
                        "refs_with_arxiv_id": 0,
                        "refs_metadata_ok": 0
                    }
                    print(f"[REFERENCES] {pid}: Semantic Scholar khong co ban ghi")
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