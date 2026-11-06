
from pathlib import Path

from latex_gatherer import remove_comments
from sentence_extractor import (
    prepare_prose_text,
    split_sentences,
)


BASE_DIR = Path("data/2608-24007/v1")

TEST_FILES = [
    "sections/intro.tex",
    "sections/experiments.tex",
    "sections/theory.tex",
    "appendix_sections/expereiments_appendix.tex",
    "appendix_sections/Theory_appendix.tex",
]


def main():
    total_sentences = 0

    print("=== MULTI-FILE SENTENCE EXTRACTION TEST ===")

    for relative_path in TEST_FILES:
        tex_file = BASE_DIR / relative_path

        if not tex_file.exists():
            print(f"\n[NOT FOUND] {relative_path}")
            continue

        content = remove_comments(
            tex_file.read_text(
                encoding="utf-8",
                errors="replace"
            )
        )

        prose = prepare_prose_text(content)
        sentences = split_sentences(prose)

        total_sentences += len(sentences)

        print(f"\nFile: {relative_path}")
        print(f"Total sentences: {len(sentences)}")

        for index, sentence in enumerate(sentences[:3], start=1):
            print(f"\nSentence {index}:")
            print(sentence[:300])

    print("\n=== SUMMARY ===")
    print(f"Total extracted sentences: {total_sentences}")


if __name__ == "__main__":
    main()
