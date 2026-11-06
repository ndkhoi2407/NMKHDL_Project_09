
import json
import shutil
from pathlib import Path
from collections import Counter

BASE = Path(__file__).resolve().parent.parent

ORIGINAL = BASE / "m2_output"
RECOVERY = BASE / "m2_recovery" / "output"
FINAL = BASE / "m2_final"

DATA_FILES = [
    "elements.jsonl",
    "hierarchy.jsonl",
    "bibtex.jsonl",
]


def read_jsonl(path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def write_jsonl(path, rows):
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def count_jsonl(path):
    with path.open("r", encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def main():
    # --------------------------------------------------
    # 1. Kiểm tra thư mục đầu vào
    # --------------------------------------------------
    for folder in [ORIGINAL, RECOVERY]:
        if not folder.exists():
            raise FileNotFoundError(f"Không tìm thấy: {folder}")

    if FINAL.exists():
        raise FileExistsError(
            f"{FINAL} đã tồn tại. "
            "Hãy đổi tên hoặc di chuyển thư mục này trước khi chạy."
        )

    original_stats_path = ORIGINAL / "paper_stats.jsonl"
    recovery_stats_path = RECOVERY / "paper_stats.jsonl"

    original_stats = list(read_jsonl(original_stats_path))
    recovery_stats = list(read_jsonl(recovery_stats_path))

    print("Original publications:", len(original_stats))
    print("Recovery publications:", len(recovery_stats))

    # --------------------------------------------------
    # 2. Xác định 104 bài lỗi ban đầu
    # --------------------------------------------------
    failed_rows = [
        row for row in original_stats
        if row.get("status") == "error"
    ]

    failed_ids = {
        row["arxiv_id"] for row in failed_rows
    }

    recovery_ids = {
        row["arxiv_id"] for row in recovery_stats
    }

    print("Original failed publications:", len(failed_ids))
    print("Recovery IDs:", len(recovery_ids))

    if len(failed_ids) != 104:
        raise ValueError(
            f"Mong đợi 104 bài lỗi, tìm thấy {len(failed_ids)}"
        )

    if failed_ids != recovery_ids:
        missing = failed_ids - recovery_ids
        unexpected = recovery_ids - failed_ids

        raise ValueError(
            f"ID không khớp!\n"
            f"Thiếu trong recovery: {sorted(missing)[:10]}\n"
            f"Ngoài danh sách lỗi: {sorted(unexpected)[:10]}"
        )

    if len(recovery_stats) != 104:
        raise ValueError("Recovery không có đúng 104 bản ghi.")

    if any(row.get("status") != "ok" for row in recovery_stats):
        raise ValueError("Recovery vẫn còn bản ghi không phải ok.")

    # --------------------------------------------------
    # 3. Tạo danh sách thống kê cuối cùng
    # --------------------------------------------------
    merged_stats = [
        row for row in original_stats
        if row.get("status") != "error"
    ] + recovery_stats

    merged_ids = [
        row["arxiv_id"] for row in merged_stats
    ]

    if len(merged_stats) != 5000:
        raise ValueError(
            f"Số bài cuối cùng không bằng 5000: {len(merged_stats)}"
        )

    if len(set(merged_ids)) != 5000:
        raise ValueError("Phát hiện arxiv_id bị trùng.")

    # --------------------------------------------------
    # 4. Tạo thư mục kết quả
    # --------------------------------------------------
    FINAL.mkdir(parents=True)

    try:
        # Ghép các file JSONL bằng streaming
        for filename in DATA_FILES:
            output_path = FINAL / filename
            total = 0

            with output_path.open("w", encoding="utf-8") as out:
                for source_folder in [ORIGINAL, RECOVERY]:
                    source_path = source_folder / filename

                    if not source_path.exists():
                        raise FileNotFoundError(source_path)

                    with source_path.open("r", encoding="utf-8") as src:
                        shutil.copyfileobj(src, out)

                    total += count_jsonl(source_path)

            actual = count_jsonl(output_path)

            if actual != total:
                raise ValueError(
                    f"Lỗi số dòng {filename}: "
                    f"mong đợi {total}, nhận được {actual}"
                )

            print(f"{filename}: {actual:,} rows")

        # Ghi paper_stats đã thay thế 104 bài lỗi
        write_jsonl(
            FINAL / "paper_stats.jsonl",
            merged_stats
        )

        # --------------------------------------------------
        # 5. Tính lại thống kê
        # --------------------------------------------------
        status_counts = Counter(
            row.get("status", "unknown")
            for row in merged_stats
        )

        def sum_field(field):
            return sum(
                row.get(field, 0) or 0
                for row in merged_stats
            )

        expected = sum_field("versions_expected")
        parsed = sum_field("versions_parsed")
        empty = sum_field("versions_empty")
        version_errors = sum_field("versions_error")

        classified = parsed + empty + version_errors

        elements_rows = count_jsonl(FINAL / "elements.jsonl")
        hierarchy_rows = count_jsonl(FINAL / "hierarchy.jsonl")
        bibtex_rows = count_jsonl(FINAL / "bibtex.jsonl")

        original_summary = json.loads(
            (ORIGINAL / "summary.json").read_text(encoding="utf-8")
        )
        recovery_summary = json.loads(
            (RECOVERY / "summary.json").read_text(encoding="utf-8")
        )

        wall_seconds = (
            original_summary.get("wall_seconds", 0)
            + recovery_summary.get("wall_seconds", 0)
        )

        output_storage_mb = sum(
            path.stat().st_size
            for path in FINAL.iterdir()
            if path.is_file()
        ) / (1024 * 1024)

        summary = {
            "publications_requested": len(merged_stats),
            "publications_ok": status_counts.get("ok", 0),
            "publications_partial": status_counts.get("partial", 0),
            "publications_error": status_counts.get("error", 0),

            "versions_expected": expected,
            "versions_parsed": parsed,
            "versions_empty": empty,
            "versions_error": version_errors,
            "versions_unclassified": expected - classified,

            "elements_rows": elements_rows,
            "hierarchy_rows": hierarchy_rows,
            "hierarchy_integrity_errors": (
                original_summary.get("hierarchy_integrity_errors", 0)
                + recovery_summary.get("hierarchy_integrity_errors", 0)
            ),
            "bibtex_rows": bibtex_rows,

            "elements_before_dedup": sum_field("elements_before_dedup"),
            "elements_after_dedup": sum_field("elements_after_dedup"),
            "bibtex_before_dedup": sum_field("bibtex_before_dedup"),
            "bibtex_after_dedup": sum_field("bibtex_after_dedup"),

            "version_parse_success_rate": (
                parsed / (expected - empty)
                if expected > empty else 0
            ),

            "wall_seconds_including_recovery": wall_seconds,
            "average_seconds_per_publication_including_recovery": (
                wall_seconds / len(merged_stats)
                if merged_stats else 0
            ),

            "process_rss_mb_at_end_max_across_runs": max(
                original_summary.get("process_rss_mb_at_end", 0),
                recovery_summary.get("process_rss_mb_at_end", 0)
            ),

            "output_storage_mb": round(output_storage_mb, 3),

            "merge_note": (
                "Original error records replaced by recovery records. "
                "Runtime and RSS are reported across separate runs; "
                "RSS is not peak RAM."
            )
        }

        (FINAL / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        # --------------------------------------------------
        # 6. Kiểm tra cuối
        # --------------------------------------------------
        print("\n========== M2 FINAL SUMMARY ==========")
        print(json.dumps(summary, ensure_ascii=False, indent=2))

        if summary["publications_requested"] != 5000:
            raise ValueError("Sai số lượng publications.")

        if summary["publications_error"] != 0:
            raise ValueError("Vẫn còn publication lỗi.")

        if summary["hierarchy_integrity_errors"] != 0:
            raise ValueError("Có lỗi hierarchy integrity.")

        print("\nSUCCESS: M2 FINAL DATASET CREATED")
        print("Output:", FINAL)

    except Exception:
        print(
            "\nCó lỗi trong quá trình ghép. "
            "Thư mục m2_final có thể chưa hoàn chỉnh."
        )
        raise


if __name__ == "__main__":
    main()
