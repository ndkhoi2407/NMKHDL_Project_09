
from pathlib import Path
from collections import Counter

from latex_parser import extract_display_math
from latex_gatherer import remove_comments


def main():
    versions = ["v1", "v2"]
    results = {}

    # 1. Extract formulas from both versions
    for version in versions:
        tex_file = Path(
            f"data/2608-24007/{version}/appendix_sections/Theory_appendix.tex"
        )

        content = remove_comments(
            tex_file.read_text(
                encoding="utf-8",
                errors="replace"
            )
        )

        formulas = extract_display_math(content)
        results[version] = formulas

        print(f"{version}: {len(formulas)} formulas")

    # 2. Compare duplicate formulas
    contents_v1 = Counter(
        formula["content"] for formula in results["v1"]
    )

    contents_v2 = Counter(
        formula["content"] for formula in results["v2"]
    )

    common = set(contents_v1) & set(contents_v2)

    print("\n--- DUPLICATE CHECK ---")
    print(f"Unique formulas in v1: {len(contents_v1)}")
    print(f"Unique formulas in v2: {len(contents_v2)}")
    print(f"Common formulas: {len(common)}")

    # Find formulas that appear in only one version
    only_v1 = set(contents_v1) - set(contents_v2)
    only_v2 = set(contents_v2) - set(contents_v1)

    print(f"Only in v1: {len(only_v1)}")
    print(f"Only in v2: {len(only_v2)}")

    # Display the first 3 formulas found only in v2
    print("\n--- FORMULAS ONLY IN V2 ---")

    for index, formula in enumerate(sorted(only_v2)[:3], start=1):
        print(f"\n--- New Formula {index} ---")
        print(formula)

    # 3. Inspect formulas in each version
    for version in versions:
        formulas = results[version]

        print(f"\n========== {version.upper()} ==========")
        print(f"Total formulas extracted: {len(formulas)}")

        for index, formula in enumerate(formulas[:5], start=1):
            print(f"\n--- Formula {index} ---")
            print(formula["content"])

        # 4. Formula statistics
        align_count = sum(
            1 for formula in formulas
            if "&" in formula["content"]
        )

        multiline_count = sum(
            1 for formula in formulas
            if "\\\\" in formula["content"]
        )

        print("\n--- FORMULA STATISTICS ---")
        print(f"Formulas containing &: {align_count}")
        print(f"Formulas containing \\\\: {multiline_count}")

        # 5. Alignment formula check
        alignment_formulas = [
            formula for formula in formulas
            if "\\begin{aligned}" in formula["content"]
        ]

        print("\n--- ALIGNMENT FORMULA CHECK ---")
        print(f"Formulas using aligned: {len(alignment_formulas)}")

        for index, formula in enumerate(
            alignment_formulas[:3], start=1
        ):
            print(f"\n--- Alignment Formula {index} ---")
            print(formula["content"])


if __name__ == "__main__":
    main()