
from pathlib import Path

from latex_gatherer import remove_comments
from mixed_extractor import extract_mixed_elements


TEX_FILES = [
    Path("data/2608-24007/v1/sections/intro.tex"),
    Path("data/2608-24007/v1/sections/experiments.tex"),
    Path("data/2608-24007/v1/sections/theory.tex"),
    Path("data/2608-24007/v1/appendix_sections/expereiments_appendix.tex"),
    Path("data/2608-24007/v1/appendix_sections/Theory_appendix.tex"),
]


def main():
    total_sentences = 0
    total_formulas = 0
    total_elements = 0

    print("=== MIXED EXTRACTION STATISTICS ===")

    for tex_file in TEX_FILES:
        content = remove_comments(
            tex_file.read_text(
                encoding="utf-8",
                errors="replace"
            )
        )

        elements = extract_mixed_elements(content)

        sentences = sum(
            element["kind"] == "sentence"
            for element in elements
        )

        formulas = sum(
            element["kind"] == "formula"
            for element in elements
        )

        total_sentences += sentences
        total_formulas += formulas
        total_elements += len(elements)

        print(f"\nFile: {tex_file.name}")
        print(f"Sentences: {sentences}")
        print(f"Formulas: {formulas}")
        print(f"Total elements: {len(elements)}")

    print("\n=== TOTAL ===")
    print(f"Sentences: {total_sentences}")
    print(f"Formulas: {total_formulas}")
    print(f"Total elements: {total_elements}")


if __name__ == "__main__":
    main()
