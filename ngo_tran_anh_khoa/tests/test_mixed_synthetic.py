
from mixed_extractor import extract_mixed_elements


def main():
    content = r"""
The first equation describes the relationship.
\[
    x = y + 1
\]
The second equation uses dollar delimiters.
$$
    y = 2x
$$
We can also use an equation environment.
\begin{equation}
    z = x + y
\end{equation}
Finally, an aligned formula:
\begin{align*}
    a &= b + c \\
    d &= e + f
\end{align*}
"""

    elements = extract_mixed_elements(content)

    print("=== SYNTHETIC MIXED EXTRACTION ===")
    print(f"Total elements: {len(elements)}")

    for index, element in enumerate(elements, start=1):
        print(f"\nElement {index}")
        print(f"Kind: {element['kind']}")
        print(f"Content: {element['content']}")

    sentences = [
        item for item in elements
        if item["kind"] == "sentence"
    ]

    formulas = [
        item for item in elements
        if item["kind"] == "formula"
    ]

    assert len(formulas) == 4, (
        f"Expected 4 formulas, got {len(formulas)}"
    )

    assert len(sentences) == 4, (
        f"Expected 4 sentences, got {len(sentences)}"
    )

    assert all(
        item["content"].startswith("\\begin{equation}")
        for item in formulas
    )

    print("\nAll mixed extraction tests passed!")


if __name__ == "__main__":
    main()
