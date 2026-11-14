
from pathlib import Path

from latex_parser import extract_display_math, remove_comments
from element_builder import build_formula_elements


def main():
    arxiv_id = "2608.24007"

    version_formulas = {}

    for version in ["v1", "v2"]:
        tex_file = Path(
            f"data/{arxiv_id.replace('.', '-')}/{version}/appendix_sections/Theory_appendix.tex"
        )

        content = remove_comments(
            tex_file.read_text(
                encoding="utf-8",
                errors="replace"
            )
        )

        version_formulas[version] = extract_display_math(content)

    elements, version_element_ids = build_formula_elements(
        arxiv_id,
        version_formulas
    )

    # 1. Check shared element IDs
    ids_v1 = set(version_element_ids["v1"])
    ids_v2 = set(version_element_ids["v2"])

    common_ids = ids_v1 & ids_v2

    print("\n--- SHARED ELEMENT ID CHECK ---")
    print(f"Shared element IDs: {len(common_ids)}")
    print(f"Unique IDs in v1: {len(ids_v1)}")
    print(f"Unique IDs in v2: {len(ids_v2)}")

    print("\nFirst 5 shared IDs:")

    for element_id in sorted(common_ids)[:5]:
        print(element_id)

    # 2. Check total elements
    print("\n--- ELEMENT BUILDER TEST ---")
    print(f"Total unique elements: {len(elements)}")

    for version, element_ids in version_element_ids.items():
        print(f"{version}: {len(element_ids)} element references")

    # 3. Display first 5 elements
    print("\n--- FIRST 5 ELEMENTS ---")

    for element in elements[:5]:
        print(
            element["element_id"],
            element["kind"]
        )
        print(element["content"])

if __name__ == "__main__":
    main()
