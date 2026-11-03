"""Giai doan 2a - Tai va giai nen source tung phien ban.

Doc data/discovery.json, tai https://export.arxiv.org/src/{id}v{n},
giai nen vao data/{yymm-id}/v{n}/ va ghi trang thai vao
data/download_status.json (chay lai se bo qua phien ban da xong).

Chay tu thu muc goc project:
    python src/download_sources.py
    python src/download_sources.py --limit 3     # thu 3 bai dau

Trang thai moi phien ban:
    ok            co file .tex
    no_tex        giai nen duoc nhung khong thay .tex
    pdf_only      source chi la PDF            -> giu empty record (thu muc rong)
    other_format  docx/PostScript/khac         -> giu empty record (thu muc rong)
    error         loi tai/giai nen             -> se thu lai o lan chay sau

Anh (png, jpg, pdf, eps...) duoc xoa ngay sau khi giai nen tung phien ban
(xem process_sources.clean_version), nen dia khong bi day len.

Tuy chon: dat bien moi truong ARXIV_CRAWLER_CONTACT (email) de dua vao
User-Agent. Khong ghi email truc tiep trong code vi repo la public.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import tarfile
import time
import zipfile
from pathlib import Path

import requests

from process_sources import clean_version   # xoa anh ngay sau khi giai nen

DATA_DIR = Path("data")
DISCOVERY = DATA_DIR / "discovery.json"
STATUS_FILE = DATA_DIR / "download_status.json"
TMP_DIR = DATA_DIR / "_tmp"

DELAY_SECONDS = 3
TIMEOUT = 60
MAX_RETRIES = 3
RETRY_CODES = {429, 500, 502, 503, 504, 404}
BLOCK_CODES = {403, 429}       # dau hieu bi arXiv chan / gioi han
MAX_CONSECUTIVE_BLOCKS = 5     # lien tiep bi chan chung nay lan thi dung han
DONE_STATUSES = {"ok", "no_tex", "pdf_only", "other_format"}

_contact = os.environ.get("ARXIV_CRAWLER_CONTACT")
HEADERS = {"User-Agent": "arxiv-milestone1-crawler/1.0 (student project"
                         + (f"; contact: {_contact}" if _contact else "") + ")"}


def load_json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save_status(status: dict):
    """Ghi qua file tam roi thay the, de crash giua chung khong lam hong file."""
    tmp = STATUS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(status, indent=2), encoding="utf-8")
    os.replace(tmp, STATUS_FILE)


def dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def fetch_to_file(url: str, dest: Path) -> tuple[int | None, str]:
    """Tai url ve file dest (stream, khong nap het vao RAM).

    Tra ve (http_code, note). note rong neu thanh cong.
    http_code la None neu loi mang (khong co phan hoi).
    """
    last_code, last_note = None, ""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with requests.get(url, headers=HEADERS, timeout=TIMEOUT,
                              stream=True) as r:
                if r.status_code == 200:
                    with open(dest, "wb") as f:
                        for chunk in r.iter_content(1024 * 256):
                            f.write(chunk)
                    return 200, ""
                if r.status_code not in RETRY_CODES:
                    return r.status_code, f"HTTP {r.status_code}"
                last_code = r.status_code
                last_note = f"HTTP {r.status_code}, da thu {attempt} lan"
        except requests.RequestException as exc:
            last_code, last_note = None, f"{type(exc).__name__}: {exc}"
        if attempt < MAX_RETRIES:
            time.sleep(DELAY_SECONDS * 2 ** attempt)
    return last_code, last_note


def sniff(path: Path, n: int = 2048) -> bytes:
    """Doc n byte dau (khong nap ca file vao RAM)."""
    with open(path, "rb") as f:
        return f.read(n)


def looks_like_text(head: bytes) -> bool:
    return b"\x00" not in head


def safe_extract_tar(tar: tarfile.TarFile, dest: Path):
    """Giai nen an toan: bo qua symlink va duong dan thoat ra ngoai dest."""
    dest_resolved = dest.resolve()
    for member in tar.getmembers():
        target = (dest / member.name).resolve()
        if dest_resolved not in target.parents and target != dest_resolved:
            continue
        if not (member.isfile() or member.isdir()):
            continue
        try:
            # filter="data" (Python >= 3.9.17/3.12) chuan hoa quyen file
            tar.extract(member, dest, filter="data")
        except TypeError:          # Python cu khong ho tro tham so filter
            tar.extract(member, dest)
        except tarfile.FilterError:
            continue


def extract_archive(raw: Path, dest: Path) -> str:
    """Nhan dien dinh dang va giai nen.

    Tra ve: 'tar' | 'zip' | 'single_file' | 'pdf_only' | 'other_format'.
    Moi thao tac doc deu theo luong, khong nap ca archive vao RAM.
    """
    head = sniff(raw)
    if head.startswith(b"%PDF"):
        return "pdf_only"
    if head.startswith(b"%!PS"):
        return "other_format"

    if tarfile.is_tarfile(raw):          # tar thuong hoac tar.gz
        with tarfile.open(raw) as tar:
            safe_extract_tar(tar, dest)
        return "tar"

    if zipfile.is_zipfile(raw):          # zip co .tex, hoac docx (khong co .tex)
        with zipfile.ZipFile(raw) as z:
            if any(n.lower().endswith(".tex") for n in z.namelist()):
                z.extractall(dest)       # zipfile tu loai bo '..' va '/' dau
                return "zip"
        return "other_format"

    if head[:2] == b"\x1f\x8b":          # gzip chua dung 1 file
        tmp = dest / "_single"
        with gzip.open(raw, "rb") as src, open(tmp, "wb") as out:
            shutil.copyfileobj(src, out)
        inner = sniff(tmp)
        if inner.startswith(b"%PDF"):
            tmp.unlink()
            return "pdf_only"
        if inner.startswith(b"%!PS") or not looks_like_text(inner):
            tmp.unlink()
            return "other_format"
        tmp.rename(dest / "main.tex")
        return "single_file"

    if looks_like_text(head):            # server da tu giai nen gzip -> .tex tran
        shutil.move(str(raw), dest / "main.tex")
        return "single_file"

    return "other_format"


def process_version(paper_id: str, folder: str, ver: str) -> dict:
    key = f"{paper_id}{ver}"
    url = f"https://export.arxiv.org/src/{key}"
    dest = DATA_DIR / folder / ver
    raw = TMP_DIR / f"{key}.download"

    if dest.exists():
        shutil.rmtree(dest)  # lan truoc co the bi do dang
    dest.mkdir(parents=True)

    code, note = fetch_to_file(url, raw)
    if code != 200:
        raw.unlink(missing_ok=True)
        shutil.rmtree(dest, ignore_errors=True)
        return {"status": "error", "http": code, "url": url, "note": note}

    archive_bytes = raw.stat().st_size
    try:
        kind = extract_archive(raw, dest)
    except Exception as exc:
        shutil.rmtree(dest, ignore_errors=True)
        return {"status": "error", "http": 200, "url": url,
                "archive_bytes": archive_bytes, "note": str(exc)}
    finally:
        raw.unlink(missing_ok=True)

    result = {"http": 200, "url": url, "format": kind,
              "dir": dest.as_posix(),
              "archive_bytes": archive_bytes,
              "extracted_bytes_before_cleanup": dir_size(dest)}
    if kind in ("pdf_only", "other_format"):
        result["status"] = kind          # thu muc phien ban de rong (empty record)
    else:
        files = [p for p in dest.rglob("*") if p.is_file()]
        has_tex = any(p.suffix.lower() == ".tex" for p in files)
        result["has_tex"] = has_tex
        result["has_bib"] = any(p.suffix.lower() == ".bib" for p in files)
        result["status"] = "ok" if has_tex else "no_tex"
        # Xoa anh ngay de dia khong phinh to. extracted_bytes_before_cleanup
        # da duoc ghi o tren (truoc khi xoa) nen thong ke truoc/sau van dung.
        result.update(clean_version(dest))
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="chi xu ly N bai dau")
    args = ap.parse_args()

    if not DISCOVERY.exists():
        raise SystemExit(f"Khong thay {DISCOVERY}. Chay discover.py truoc.")
    papers = load_json(DISCOVERY, {}).get("papers", [])
    if args.limit:
        papers = papers[:args.limit]
    status = load_json(STATUS_FILE, {})
    TMP_DIR.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    blocked, stop = 0, False
    for p in papers:
        for ver in p["versions"]:
            key = f"{p['id']}{ver}"
            if status.get(key, {}).get("status") in DONE_STATUSES:
                print(f"[SOURCE] Bo qua {key} (da xong)")
                continue
            result = process_version(p["id"], p["folder"], ver)
            status[key] = result
            save_status(status)  # luu ngay de chay lai khong mat tien do
            print(f"[SOURCE] {key}: {result['status']}"
                  f"{' - ' + result['note'] if result.get('note') else ''}")

            blocked = blocked + 1 if result.get("http") in BLOCK_CODES else 0
            if blocked >= MAX_CONSECUTIVE_BLOCKS:
                print(f"[SOURCE] Bi chan/gioi han {blocked} lan lien tiep "
                      f"(HTTP {result['http']}). Dung de tranh bi khoa; "
                      "chay lai sau se tiep tuc tu cho cu.")
                stop = True
                break
            time.sleep(DELAY_SECONDS)
        if stop:
            break

    shutil.rmtree(TMP_DIR, ignore_errors=True)
    counts = {}
    for v in status.values():
        counts[v["status"]] = counts.get(v["status"], 0) + 1
    print(f"[SOURCE] Xong sau {time.perf_counter() - t0:.1f}s:", counts)
    if stop:
        raise SystemExit(2)   # de main.py dung lai thay vi chay tiep cac buoc sau


if __name__ == "__main__":
    main()