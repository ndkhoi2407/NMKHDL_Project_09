
from pathlib import Path
from collections import Counter

from latex_parser import parse_all_environments


def main():
    source_dir = Path("data/2608-24007/v1")

    environments = parse_all_environments(source_dir)

    print("=== ENVIRONMENT CLASSIFICATION ===")
    print(f"Total environments: {len(environments)}")
    print()

    counts = Counter(
        env["category"] for env in environments
    )

    print("=== CATEGORY STATISTICS ===")

    for category, count in sorted(counts.items()):
        print(f"{category}: {count}")

    print()
    print("=== ENVIRONMENT DETAILS ===")

    for index, env in enumerate(environments, start=1):
        print(
            f'{index:03d}. '
            f'{env["name"]:<18} '
            f'category={env["category"]:<12} '
            f'file={Path(env["file"]).name:<30} '
            f'depth={env["depth"]}'
        )


if __name__ == "__main__":
    main()
