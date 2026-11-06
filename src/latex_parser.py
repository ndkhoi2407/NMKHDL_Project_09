
from pathlib import Path
import re

from latex_gatherer import (
    gather_compilation_path,
    find_root_tex,
    expand_document_content,
    remove_comments,
)


HEADING_LEVELS = {
    "part": 1,
    "chapter": 2,
    "section": 3,
    "subsection": 4,
    "subsubsection": 5,
    "paragraph": 6,
    "subparagraph": 7,
}


# ============================================================
# 1. HEADING PARSER
# ============================================================

def parse_heading_content(
    content: str,
    source_file: Path,
    position_offset: int = 0
) -> list[dict]:
    """
    Extract heading commands from text content.

    Supports:
    - part, chapter, section, subsection
    - subsubsection, paragraph, subparagraph
    - Starred headings
    - Optional short titles
    - Nested braces in heading titles
    """
    command_pattern = re.compile(
        r"\\(part|chapter|section|subsection|subsubsection|"
        r"paragraph|subparagraph)(\*)?"
        r"(?:\s*\[([^\]]*)\])?\s*\{"
    )

    headings = []

    for match in command_pattern.finditer(content):
        command = match.group(1)
        starred = match.group(2) is not None
        short_title = match.group(3)

        start = match.end()
        depth = 1
        position = start

        while position < len(content) and depth > 0:
            char = content[position]

            if char == "\\":
                position += 2
                continue

            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1

            position += 1

        if depth != 0:
            continue

        title = content[start:position - 1].strip()

        headings.append({
            "command": command,
            "level": HEADING_LEVELS[command],
            "starred": starred,
            "title": title,
            "short_title": short_title,
            "file": str(source_file),
            "position": position_offset + match.start(),
        })

    return headings


def parse_headings(tex_file: Path) -> list[dict]:
    """Extract headings from one TeX file."""
    tex_file = Path(tex_file)

    content = remove_comments(
        tex_file.read_text(
            encoding="utf-8",
            errors="replace"
        )
    )

    return parse_heading_content(
        content=content,
        source_file=tex_file
    )


def parse_all_headings(source_dir: Path) -> list[dict]:
    """
    Extract headings from the expanded document body
    in actual source order.
    """
    root_tex = find_root_tex(source_dir)

    segments = expand_document_content(root_tex)

    all_headings = []

    for segment in segments:
        headings = parse_heading_content(
            content=segment["content"],
            source_file=segment["file"],
            position_offset=segment["start"]
        )

        all_headings.extend(headings)

    return all_headings


# ============================================================
# 2. DISPLAY MATH PARSER
# ============================================================

def remove_labels(text: str) -> str:
    """Remove LaTeX label commands from content."""
    return re.sub(
        r"\\label\s*\{[^{}]*\}",
        "",
        text
    ).strip()


def normalize_formula(
    math_content: str,
    original_environment: str = ""
) -> str:
    """
    Normalize display math to equation environment.

    Use aligned for align environments or content
    containing alignment markers.
    """
    math_content = remove_labels(math_content).strip()

    needs_alignment = (
        original_environment.startswith("align")
        or "&" in math_content
        or "\\\\" in math_content
    )

    if needs_alignment:
        return (
            "\\begin{equation}\n"
            "\\begin{aligned}\n"
            + math_content
            + "\n\\end{aligned}\n"
            "\\end{equation}"
        )

    return (
        "\\begin{equation}\n"
        + math_content
        + "\n\\end{equation}"
    )


def extract_display_math(content: str) -> list[dict]:
    """
    Extract display math from LaTeX content.

    Supported:
    - \\[ ... \\]
    - $$ ... $$
    - equation / equation*
    - align / align*

    All formulas are normalized to equation environments.
    """
    formulas = []

    # --------------------------------------------------------
    # 1. Extract \\[ ... \\] and $$ ... $$
    # --------------------------------------------------------

    delimiter_patterns = [
        re.compile(
            r"(?<!\\)\\\[(.*?)\\\]",
            re.DOTALL
        ),
        re.compile(
            r"(?<!\\)\$\$(.*?)\$\$",
            re.DOTALL
        ),
    ]

    for pattern in delimiter_patterns:
        for match in pattern.finditer(content):
            math_content = match.group(1)

            formulas.append({
                "kind": "formula",
                "content": normalize_formula(math_content),
                "start": match.start(),
                "end": match.end(),
            })

    # --------------------------------------------------------
    # 2. Extract equation / align environments
    # --------------------------------------------------------

    environment_pattern = re.compile(
        r"\\begin\s*\{(equation\*?|align\*?|gather\*?|multline\*?|displaymath)\}"
        r"(.*?)"
        r"\\end\s*\{\1\}",
        re.DOTALL
    )

    for match in environment_pattern.finditer(content):
        original_environment = match.group(1)
        math_content = match.group(2)

        formulas.append({
            "kind": "formula",
            "content": normalize_formula(
                math_content,
                original_environment
            ),
            "start": match.start(),
            "end": match.end(),
        })

    # --------------------------------------------------------
    # 3. Sort formulas by source position
    # --------------------------------------------------------

    formulas.sort(key=lambda item: item["start"])

    # --------------------------------------------------------
    # 4. Remove overlapping matches
    # --------------------------------------------------------

    filtered = []

    for formula in formulas:
        if (
            filtered
            and formula["start"] < filtered[-1]["end"]
        ):
            continue

        filtered.append(formula)

    return filtered



# ============================================================
# 3. ENVIRONMENT PARSER
# ============================================================

ENVIRONMENT_CATEGORIES = {
    # Figure
    "figure": "figure",
    "figure*": "figure",
    "wrapfigure": "figure",

    # Table: treated as figure according to M2
    "table": "figure",
    "table*": "figure",

    # Lists
    "itemize": "list",
    "enumerate": "list",
    "description": "list",

    # Display math
    "equation": "formula",
    "equation*": "formula",
    "align": "formula",
    "align*": "formula",
    "gather": "formula",
    "gather*": "formula",
    "multline": "formula",
    "multline*": "formula",
    "displaymath": "formula",

    # Inner mathematical structures
    "aligned": "math_inner",
    "alignedat": "math_inner",
    "gathered": "math_inner",
    "split": "math_inner",
    "array": "math_inner",
    "matrix": "math_inner",
    "pmatrix": "math_inner",
    "bmatrix": "math_inner",
    "Bmatrix": "math_inner",
    "vmatrix": "math_inner",
    "Vmatrix": "math_inner",
    "cases": "math_inner",

    # Theorem-like environments
    "theorem": "theorem",
    "lemma": "theorem",
    "corollary": "theorem",
    "proposition": "theorem",
    "definition": "theorem",
    "example": "theorem",
    "remark": "theorem",
    "claim": "theorem",
    "assumption": "theorem",

    # Proof
    "proof": "proof",

    # Layout / formatting
    "center": "layout",
    "flushleft": "layout",
    "flushright": "layout",
    "minipage": "layout",
    "tcolorbox": "layout",
    "tabular": "layout",
    "tabular*": "layout",
    "tikzpicture": "layout",

    # Abstract
    "abstract": "abstract",

    # Custom structured environments
    "datasetting": "structured_block",
    "trainingsetup": "structured_block",
    "initializationsetting": "structured_block",

    # Referenceable environments
    "setting": "structured_block",
    "model": "structured_block",
    "initialization": "structured_block",
}


def classify_environment(name: str) -> str:
    """Return the category of a LaTeX environment."""
    return ENVIRONMENT_CATEGORIES.get(name, "other")


def extract_environment_content(
    content: str,
    source_file: Path,
    position_offset: int = 0
) -> list[dict]:
    """
    Extract LaTeX environments from text content.

    Supports nested environments and optional titles.
    Preserves source file and original positions.
    """
    pattern = re.compile(
        r"\\(begin|end)\s*\{([^{}]+)\}"
        r"(?:\[([^\]]*)\])?"
    )

    stack = []
    environments = []

    for match in pattern.finditer(content):
        action = match.group(1)
        name = match.group(2).strip()

        if action == "begin":
            parent = stack[-1] if stack else None

            stack.append({
                "name": name,
                "title": (
                    match.group(3).strip()
                    if match.group(3)
                    else None
                ),
                "start": match.start(),
                "body_start": match.end(),
                "depth": len(stack),
                "parent_name": (
                    parent["name"] if parent else None
                ),
                "parent_start": (
                    parent["start"] if parent else None
                ),
            })

        elif action == "end":
            if not stack:
                continue

            if stack[-1]["name"] != name:
                continue

            opened = stack.pop()

            raw_content = content[
                opened["body_start"]:match.start()
            ]

            environments.append({
                "name": name,
                "category": classify_environment(name),
                "title": opened["title"],
                "start": position_offset + opened["start"],
                "body_start": position_offset + opened["body_start"],
                "body_end": position_offset + match.start(),
                "end": position_offset + match.end(),
                "depth": opened["depth"],
                "parent_name": opened["parent_name"],
                "parent_start": (
                    position_offset + opened["parent_start"]
                    if opened["parent_start"] is not None
                    else None
                ),
                "file": str(source_file),
                "content": remove_labels(raw_content),
            })

    environments.sort(key=lambda item: item["start"])

    return environments


def extract_environments(tex_file: Path) -> list[dict]:
    """Extract environments from one TeX file."""
    tex_file = Path(tex_file)

    content = remove_comments(
        tex_file.read_text(
            encoding="utf-8",
            errors="replace"
        )
    )

    return extract_environment_content(
        content=content,
        source_file=tex_file
    )


def parse_all_environments(source_dir: Path) -> list[dict]:
    """
    Extract environments from the expanded document body.

    Preserve actual document order across input/include files.
    Exclude environments in the preamble.
    """
    root_tex = find_root_tex(source_dir)

    segments = expand_document_content(root_tex)

    all_environments = []

    for segment in segments:
        environments = extract_environment_content(
            content=segment["content"],
            source_file=segment["file"],
            position_offset=segment["start"]
        )

        all_environments.extend(environments)

    return all_environments

# ============================================================
# 4. TEST / MAIN
# ============================================================

def main():
    source_dir = Path("data/2608-24007/v1")

    # Test heading extraction.
    headings = parse_all_headings(source_dir)

    print("=== HEADINGS ===")
    print(f"Total headings: {len(headings)}")
    print()

    for index, heading in enumerate(headings, start=1):
        indent = "  " * (heading["level"] - 1)

        marker = "*" if heading["starred"] else ""

        print(
            f"{index:03d}. "
            f"{indent}"
            f"\\{heading['command']}{marker}: "
            f"{heading['title'][:100]}"
        )

    # Test environment extraction.
    environments = parse_all_environments(source_dir)

    print()
    print("=== ENVIRONMENTS ===")
    print(f"Total environments: {len(environments)}")
    print()

    for index, env in enumerate(environments, start=1):
        filename = Path(env["file"]).name

        print(
            f'{index:03d}. '
            f'{env["name"]} | '
            f'{filename} | '
            f'depth={env["depth"]} | '
            f'parent={env["parent_name"]} | '
            f'parent_pos={env["parent_start"]} | '
            f'pos={env["start"]}'
        )


if __name__ == "__main__":
    main()
