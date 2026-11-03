"""Giai doan 2b - Xoa file anh nhi phan, giu nguyen van ban va cau truc thu muc.

Doc data/download_status.json, voi moi phien ban da giai nen (ok / no_tex)
thi xoa cac file anh theo danh sach duoi mo rong ro rang, ghi them thong ke
dung luong vao chinh file status.

Chay tu thu muc goc project:
    python src/process_sources.py
"""
import json
import os
from collections import Counter
from pathlib import Path

DATA_DIR = Path("data")
STATUS_FILE = DATA_DIR / "download_status.json"

# Phien ban co thu muc giai nen can don dep (pdf_only / other_format la rong)
CLEAN_STATUSES = {"ok", "no_tex"}
SAVE_EVERY = 25   # ghi status sau moi N phien ban (va luon ghi khi thoat)

# Chi xoa nhung dinh dang anh nay. Khong xoa file la mot cach may moc.
IMAGE_EXTS = {
    ".png", ".jpg", ".jpeg", ".jpe", ".jp2", ".gif", ".bmp", ".tif", ".tiff",
    ".webp", ".ico", ".emf", ".wmf", ".eps", ".ps", ".pdf",
}
# Anh nen, vd figure.eps.gz / figure.ps.gz (hay gap o bai cu): xet duoi ben trong
COMPRESSED_EXTS = {".gz", ".z"}

# Duoi van ban/tai nguyen LaTeX da biet (khong xoa, khong bao cao)
KNOWN_TEXT_EXTS = {
    ".tex", ".bib", ".bbl", ".bst", ".sty", ".cls", ".clo", ".def", ".cfg",
    ".ins", ".dtx", ".txt", ".md", ".sh", ".py", ".csv", ".dat", ".json",
    ".svg", ".pgf", ".tikz", ".aux", ".log", ".out", ".toc", ".lof", ".lot",
    ".ind", ".idx", ".glo", ".gls", ".blg", ".sbl", ".ist", ".ltx", ".rtx",
}


def dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def save_status(status: dict):
    """Ghi qua file tam roi thay the, de crash giua chung khong lam hong file."""
    tmp = STATUS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(status, indent=2), encoding="utf-8")
    os.replace(tmp, STATUS_FILE)


def effective_ext(f: Path) -> str:
    ext = f.suffix.lower()
    if ext in COMPRESSED_EXTS:
        return Path(f.stem).suffix.lower()
    return ext


def clean_version(vdir: Path) -> dict:
    removed_files = 0
    removed_bytes = 0
    other_exts = Counter()
    other_bytes = 0

    for f in vdir.rglob("*"):
        if not f.is_file():
            continue
        ext = effective_ext(f)
        size = f.stat().st_size
        if ext in IMAGE_EXTS:
            f.unlink()
            removed_files += 1
            removed_bytes += size
        elif ext not in KNOWN_TEXT_EXTS:
            other_exts[ext or "(no extension)"] += 1
            other_bytes += size

    return {
        "cleaned": True,
        "removed_image_files": removed_files,
        "removed_image_bytes": removed_bytes,
        "extracted_bytes_after_cleanup": dir_size(vdir),
        "unrecognized_extensions": dict(other_exts),
        "unrecognized_bytes": other_bytes,
    }


def version_dir(key: str, info: dict) -> Path:
    """Uu tien duong dan do download_sources.py ghi lai; neu khong co thi suy ra."""
    if info.get("dir"):
        return Path(info["dir"])
    # key dang 2310.00001v2 -> thu muc data/2310-00001/v2
    base, ver = key.rsplit("v", 1)
    return DATA_DIR / base.replace(".", "-") / f"v{ver}"


def main():
    if not STATUS_FILE.exists():
        raise SystemExit(f"Khong tim thay {STATUS_FILE.resolve()}. "
                         "Hay chay download_sources.py truoc, tu thu muc goc project.")
    status = json.loads(STATUS_FILE.read_text(encoding="utf-8"))

    total_before = total_after = processed = 0
    unknown_total = Counter()
    unknown_bytes_total = 0

    try:
        for key, info in status.items():
            if info.get("status") not in CLEAN_STATUSES:
                continue
            if info.get("cleaned"):
                print(f"[CLEAN] Bo qua {key} (da xu ly)")
                continue

            vdir = version_dir(key, info)
            if not vdir.exists():
                print(f"[CLEAN] CANH BAO: khong thay thu muc {vdir}")
                continue

            info.update(clean_version(vdir))

            before = info.get("extracted_bytes_before_cleanup", 0)
            after = info["extracted_bytes_after_cleanup"]
            total_before += before
            total_after += after
            processed += 1
            unknown_total.update(info["unrecognized_extensions"])
            unknown_bytes_total += info["unrecognized_bytes"]
            print(f"[CLEAN] {key}: xoa {info['removed_image_files']} anh, "
                  f"{before / 1024:.0f} KB -> {after / 1024:.0f} KB")

            if processed % SAVE_EVERY == 0:
                save_status(status)
    finally:
        save_status(status)   # luon luu, ke ca khi bi Ctrl+C hoac loi giua chung

    print(f"[CLEAN] Xong {processed} phien ban (lan chay nay). "
          f"Tong: {total_before / 1e6:.2f} MB -> {total_after / 1e6:.2f} MB")
    if unknown_total:
        print("[CLEAN] Duoi file chua nhan dien (can xem lai):",
              dict(unknown_total), f"- tong {unknown_bytes_total / 1e6:.2f} MB")


if __name__ == "__main__":
    main()