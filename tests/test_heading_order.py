
from pathlib import Path

from latex_parser import parse_all_headings


def main():
    source_dir = Path("data/2608-24007/v1")

    headings = parse_all_headings(source_dir)

    print("=== HEADINGS IN DOCUMENT ORDER ===")
    print(f"Total headings: {len(headings)}")

    for index, heading in enumerate(headings, start=1):
        indent = "  " * (heading["level"] - 1)

        marker = "*" if heading["starred"] else ""

        print(
            f"{index:03d}. {indent}"
            f"\\{heading['command']}{marker}: "
            f"{heading['title'][:100]}"
        )

        print(f"     File: {Path(heading['file']).name}")


if __name__ == "__main__":
    main()
