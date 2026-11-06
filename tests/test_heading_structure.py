
from pathlib import Path

from latex_parser import parse_all_headings


def main():
    source_dir = Path("data/2608-24007/v1")

    headings = parse_all_headings(source_dir)

    print("=== HEADING STRUCTURE ===")
    print(f"Total headings: {len(headings)}")

    for index, heading in enumerate(headings[:40], start=1):
        print(f"\nHeading {index}")

        for key, value in heading.items():
            print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
