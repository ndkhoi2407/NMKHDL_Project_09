
import re
from pathlib import Path

from latex_gatherer import remove_comments


TEX_FILES = [
    Path("data/2608-24007/v1/sections/intro.tex"),
    Path("data/2608-24007/v1/sections/experiments.tex"),
    Path("data/2608-24007/v1/sections/theory.tex"),
    Path("data/2608-24007/v1/appendix_sections/expereiments_appendix.tex"),
    Path("data/2608-24007/v1/appendix_sections/Theory_appendix.tex"),
]


def main():
    environment_counts = {}

    for tex_file in TEX_FILES:
        content = remove_comments(
            tex_file.read_text(
                encoding="utf-8",
                errors="replace"
            )
        )

        # Find LaTeX environment names.
        names = re.findall(
            r"\\begin\s*\{([^{}]+)\}",
            content
        )

        for name in names:
            if name in {
                "equation", "equation*",
                "align", "align*",
                "gather", "gather*",
                "multline", "multline*",
                "displaymath"
            }:
                environment_counts[name] = (
                    environment_counts.get(name, 0) + 1
                )

        # Count $$...$$ and \[...\] delimiters.
        environment_counts["$$"] = (
            environment_counts.get("$$", 0)
            + len(re.findall(r"(?<!\\)\$\$", content))
        )

        environment_counts[r"\[...\]"] = (
            environment_counts.get(r"\[...\]", 0)
            + len(re.findall(r"(?<!\\)\\\[", content))
        )

    print("=== DISPLAY MATH ENVIRONMENT STATISTICS ===")

    for name, count in sorted(environment_counts.items()):
        print(f"{name}: {count}")


if __name__ == "__main__":
    main()
