
from latex_parser import extract_display_math
from sentence_extractor import (
    split_sentences,
    prepare_prose_text,
    remove_environment,
)


ACADEMIC_ENVIRONMENTS = [
    "datasetting",
    "trainingsetup",
    "initializationsetting",
    "setting",
    "model",
    "initialization",
    "theorem",
    "lemma",
    "corollary",
    "proposition",
    "definition",
    "example",
    "remark",
    "claim",
    "assumption",
    "proof",
]


def unwrap_academic_environments(text: str) -> str:
    """
    Remove academic environment wrappers while preserving their contents.

    This must run on the complete text before extracting formulas.
    Otherwise, begin/end tags may be separated by formula boundaries.
    """

    for environment in ACADEMIC_ENVIRONMENTS:
        text = remove_environment(
            text,
            environment,
            preserve_content=True
        )

    return text


def extract_mixed_elements(text: str) -> list[dict]:
    """
    Extract sentences and display formulas in source order.

    Academic environment wrappers are removed before formula extraction.
    Prose is cleaned before sentence splitting.
    Display formulas are preserved as independent elements.
    """

    # 1. Unwrap academic environments across the complete text.
    text = unwrap_academic_environments(text)

    # 2. Find display formulas and sort by source position.
    formulas = sorted(
        extract_display_math(text),
        key=lambda item: item["start"]
    )

    elements = []
    cursor = 0

    def add_sentences(prose: str):
        """Clean prose and split it into sentences."""

        cleaned_prose = prepare_prose_text(prose)
        sentences = split_sentences(cleaned_prose)

        for sentence in sentences:
            sentence = sentence.strip()

            if sentence:
                elements.append({
                    "kind": "sentence",
                    "content": sentence
                })

    # 3. Extract prose and formulas in source order.
    for formula in formulas:
        start = formula["start"]
        end = formula["end"]

        # Ignore invalid or overlapping formula positions.
        if start < cursor or end <= start:
            continue

        # Process prose before the formula.
        add_sentences(text[cursor:start])

        # Preserve the normalized formula.
        elements.append({
            "kind": "formula",
            "content": formula["content"]
        })

        cursor = end

    # 4. Process remaining prose.
    add_sentences(text[cursor:])

    return elements
