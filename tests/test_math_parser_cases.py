
from latex_parser import extract_display_math


TEST_CASES = {
    "bracket": r"""
Text before.
\[
    x = y + 1
\]
Text after.
""",

    "dollar": r"""
Text before.
$$
    x = y + 1
$$
Text after.
""",

    "equation": r"""
Text before.
\begin{equation}
    x = y + 1
\end{equation}
Text after.
""",

    "equation_star": r"""
Text before.
\begin{equation*}
    x = y + 1
\end{equation*}
Text after.
""",

    "align": r"""
Text before.
\begin{align}
    x &= y + 1 \\
    z &= a + b
\end{align}
Text after.
""",

    "align_star": r"""
Text before.
\begin{align*}
    x &= y + 1 \\
    z &= a + b
\end{align*}
Text after.
""",
}


def main():
    print("=== LATEX MATH PARSER TESTS ===")

    for name, content in TEST_CASES.items():
        formulas = extract_display_math(content)

        print(f"\n{name}: {len(formulas)} formula(s)")

        if formulas:
            print(formulas[0]["content"])

        assert len(formulas) == 1, (
            f"Expected 1 formula for {name}, "
            f"got {len(formulas)}"
        )

    print("\nAll test cases passed!")


if __name__ == "__main__":
    main()
