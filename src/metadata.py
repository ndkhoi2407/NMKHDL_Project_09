"""Giai doan 3a - Tao metadata.json cho tung bai.

Lay title/authors/published tu data/discovery.json.
- Bai chi co v1: du thong tin, KHONG can goi them request nao.
- Bai nhieu phien ban: lay ngay cua TUNG phien ban tu OAI-PMH
  (metadataPrefix=arXivRaw).
Khong luu venue (de bai chi yeu cau neu co: "if applicable").

Chay tu thu muc goc project:
    python src/metadata.py
    python src/metadata.py --limit 3

Tuy chon: dat bien moi truong ARXIV_CRAWLER_CONTACT (email) de dua vao
User-Agent. Khong ghi email truc tiep trong code vi repo la public.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import xml.etree.ElementTree as ET
from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

DATA_DIR = Path("data")
DISCOVERY = DATA_DIR / "discovery.json"
STATUS_FILE = DATA_DIR / "metadata_status.json"

OAI_URL = "https://oaipmh.arxiv.org/oai"
NS_OAI = "http://www.openarchives.org/OAI/2.0/"
NS_RAW = "http://arxiv.org/OAI/arXivRaw/"

DELAY_SECONDS = 3
TIMEOUT = 60
MAX_RETRIES = 3
MAX_WAIT = 120        # tran thoi gian cho theo Retry-After (giay)
SAVE_EVERY = 25       # ghi status sau moi N bai (va luon ghi khi thoat)

# De bai tap ghi ro "revised dates" co tinh ngay v1 hay khong. Hien tinh ca v1
# (khop huong dan nhom). Doi thanh False neu giang vien xac nhan chi tinh v2+.
INCLUDE_V1_IN_REVISED = True

_contact = os.environ.get("ARXIV_CRAWLER_CONTACT")
HEADERS = {"User-Agent": "arxiv-milestone1-crawler/1.0 (student project"
                         + (f"; contact: {_contact}" if _contact else "") + ")"}


def save_status(status: dict):
    """Ghi qua file tam roi thay the, de crash giua chung khong lam hong file."""
    tmp = STATUS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(status, indent=2), encoding="utf-8")
    os.replace(tmp, STATUS_FILE)


def retry_after_seconds(resp: requests.Response, default: int) -> int:
    """Retry-After co the la so giay hoac ngay HTTP; khong doc duoc thi dung default."""
    try:
        return min(int(resp.headers["Retry-After"]), MAX_WAIT)
    except (KeyError, ValueError):
        return default


def fetch_raw_record(arxiv_id: str) -> tuple[ET.Element | None, str]:
    """Goi OAI-PMH GetRecord. Tra ve (root_xml, note_loi)."""
    params = {
        "verb": "GetRecord",
        "identifier": f"oai:arXiv.org:{arxiv_id}",
        "metadataPrefix": "arXivRaw",
    }
    note = ""
    for attempt in range(1, MAX_RETRIES + 1):
        wait = DELAY_SECONDS * 2 ** attempt
        try:
            r = requests.get(OAI_URL, params=params, headers=HEADERS,
                             timeout=TIMEOUT)
            if r.status_code in (429, 503):
                wait = retry_after_seconds(r, wait)
                note = f"HTTP {r.status_code}, da thu {attempt} lan"
            elif r.status_code != 200:
                return None, f"HTTP {r.status_code}"
            else:
                root = ET.fromstring(r.content)
                err = root.find(f"{{{NS_OAI}}}error")
                if err is not None:
                    return None, f"OAI error {err.get('code')}: {err.text}"
                return root, ""
        except (requests.RequestException, ET.ParseError) as exc:
            note = f"{type(exc).__name__}: {exc}"
        if attempt < MAX_RETRIES:
            time.sleep(wait)
    return None, note


def parse_versions(root: ET.Element) -> list[tuple[str, str]]:
    """Tra ve [(v1, '2023-10-01'), (v2, '2023-11-15'), ...] theo thu tu phien ban."""
    out = []
    for v in root.iter(f"{{{NS_RAW}}}version"):
        date_text = v.findtext(f"{{{NS_RAW}}}date")
        dt = parsedate_to_datetime(date_text).astimezone(timezone.utc)
        out.append((v.get("version"), dt.date().isoformat()))
    out.sort(key=lambda x: int(x[0].lstrip("v")))
    return out


def make_meta(paper: dict, versions: list[tuple[str, str]]) -> dict:
    dates = [d for _, d in versions]
    return {
        "title": paper["title"],
        "authors": paper["authors"],
        "submission_date": dates[0],
        "revised_dates": dates if INCLUDE_V1_IN_REVISED else dates[1:],
    }


def build_metadata_oai(paper: dict, root: ET.Element) -> tuple[dict, str]:
    versions = parse_versions(root)
    warning = ""
    if len(versions) != paper["latest_version"]:
        warning = (f"discovery bao {paper['latest_version']} phien ban, "
                   f"OAI tra ve {len(versions)}")
    return make_meta(paper, versions), warning


def write_meta(out_dir: Path, meta: dict):
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "metadata.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    if not DISCOVERY.exists():
        raise SystemExit(f"Khong tim thay {DISCOVERY.resolve()}. "
                         "Chay discover.py truoc, tu thu muc goc project.")
    papers = json.loads(DISCOVERY.read_text(encoding="utf-8"))["papers"]
    if args.limit:
        papers = papers[:args.limit]
    if papers and "authors" not in papers[0]:
        raise SystemExit("discovery.json chua co 'authors'. "
                         "Hay sua discover.py va chay lai.")

    status = (json.loads(STATUS_FILE.read_text(encoding="utf-8"))
              if STATUS_FILE.exists() else {})

    handled = 0
    try:
        for p in papers:
            out_dir = DATA_DIR / p["folder"]
            if ((out_dir / "metadata.json").exists()
                    and status.get(p["id"], {}).get("status") == "ok"):
                print(f"[METADATA] Bo qua {p['id']} (da xong)")
                continue

            used_network = False
            try:
                if p["latest_version"] == 1:
                    # Chi co v1: ngay nop = published, khong can OAI-PMH
                    meta = make_meta(p, [("v1", p["published"])])
                    write_meta(out_dir, meta)
                    status[p["id"]] = {"status": "ok", "source": "discovery",
                                       "note": ""}
                    print(f"[METADATA] Saved {p['id']} (tu discovery)")
                else:
                    used_network = True
                    root, note = fetch_raw_record(p["id"])
                    if root is None:
                        status[p["id"]] = {"status": "error", "note": note}
                        print(f"[METADATA] LOI {p['id']}: {note}")
                    else:
                        meta, warning = build_metadata_oai(p, root)
                        write_meta(out_dir, meta)
                        status[p["id"]] = {"status": "ok", "source": "oai",
                                           "note": warning}
                        print(f"[METADATA] Saved {p['id']}"
                              f"{' (CANH BAO: ' + warning + ')' if warning else ''}")
            except Exception as exc:
                status[p["id"]] = {"status": "error",
                                   "note": f"{type(exc).__name__}: {exc}"}
                print(f"[METADATA] LOI {p['id']}: {exc}")

            handled += 1
            if handled % SAVE_EVERY == 0:
                save_status(status)
            if used_network:
                time.sleep(DELAY_SECONDS)   # chi can nghi khi vua goi arXiv
    finally:
        save_status(status)

    ok = sum(1 for s in status.values() if s["status"] == "ok")
    via_oai = sum(1 for s in status.values() if s.get("source") == "oai")
    print(f"[METADATA] Xong: {ok}/{len(status)} bai thanh cong "
          f"({via_oai} bai phai goi OAI-PMH)")


if __name__ == "__main__":
    main()
