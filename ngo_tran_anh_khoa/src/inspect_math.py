import re
from pathlib import Path

from latex_gatherer import gather_compilation_path, remove_comments


def main():
    source_dir = Path("data/2608-24007/v1")
    tex_files = gather_compilation_path(source_dir)

    total_open = 0
    total_close = 0

    for tex_file in tex_files:
        content = remove_comments(
            tex_file.read_text(
                encoding="utf-8",
                errors="replace"
            )
        )

        opens = []
        closes = []

        for line_number, line in enumerate(
            content.splitlines(), start=1
        ):
            if re.search(r"(?<!\\)\\\[(?![0-9.])", line):
                opens.append(line_number)

            if re.search(r"(?<!\\)\\\]", line):
                closes.append(line_number)
        total_open += len(opens)
        total_close += len(closes)

        if len(opens) != len(closes):
            print(f"\nFile: {tex_file}")
            print(f"Opening: {len(opens)}")
            print(f"Closing: {len(closes)}")
            print("Opening lines:", opens)
            print("Closing lines:", closes)

    print("\nTOTAL")
    print(f"Opening: {total_open}")
    print(f"Closing: {total_close}")


if __name__ == "__main__":
    main()
