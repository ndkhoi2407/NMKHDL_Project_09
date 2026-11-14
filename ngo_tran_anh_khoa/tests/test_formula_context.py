
from pathlib import Path

from latex_gatherer import remove_comments
from latex_parser import extract_display_math
from sentence_extractor import split_sentences


def main():
    # 1. Read and clean the original LaTeX file.
    tex_file = Path(
        "data/2608-24007/v1/appendix_sections/Theory_appendix.tex"
    )

    content = remove_comments(
        tex_file.read_text(
            encoding="utf-8",
            errors="replace"
        )
    )

    # 2. Extract the target block.
    start = content.find("Throughout this subsection")

    if start == -1:
        raise ValueError("Cannot find target starting text.")

    end = content.find("Write the ReLU activation function", start)

    if end == -1:
        raise ValueError("Cannot find target ending text.")

    block = content[start:end]

    # 3. Extract display formulas.
    formulas = extract_display_math(block)

    print("=== DISPLAY FORMULA SUMMARY ===")
    print(f"Total formulas: {len(formulas)}")

    # 4. Display text segments between formulas.
    parts = []
    last_position = 0

    for formula in formulas:
        parts.append(
            block[last_position:formula["start"]].strip()
        )
        last_position = formula["end"]

    parts.append(block[last_position:].strip())

    print("\n=== TEXT BETWEEN DISPLAY FORMULAS ===")

    for index, part in enumerate(parts, start=1):
        print(f"\n--- TEXT {index} ---")
        print(part)

    # 5. Replace formulas with placeholders.
    normalized = block

    for index, formula in reversed(
        list(enumerate(formulas, start=1))
    ):
        placeholder = f"⟦FORMULA_{index}⟧"

        normalized = (
            normalized[:formula["start"]]
            + placeholder
            + normalized[formula["end"]:]
        )

    # 6. Remove redundant outer braces.
    normalized = normalized.strip()

    if normalized.endswith("}"):
        normalized = normalized[:-1].rstrip()

    if normalized.startswith("{"):
        normalized = normalized[1:].lstrip()

    print("\n=== TEXT WITH FORMULA PLACEHOLDERS ===")
    print(normalized)

    # 7. Split sentences while preserving formula placeholders.
    sentences = split_sentences(normalized)

    print("\n=== SENTENCES WITH FORMULA PLACEHOLDERS ===")
    print(f"Total sentences: {len(sentences)}")

    for index, sentence in enumerate(sentences, start=1):
        print(f"\nSentence {index}:")
        print(sentence)


if __name__ == "__main__":
    main()
