"""Publication-wide element identity assignment and cross-version deduplication."""
from __future__ import annotations

import re
import unicodedata

PREFIX = {
    "document": "root",
    "heading": "h",
    "paragraph": "p",
    "sentence": "s",
    "formula": "f",
    "figure": "fig",
    "list": "list",
    "list_item": "li",
    "abstract": "a",
    "acknowledgements": "ack",
}


def normalize_element_content(content: str) -> str:
    text = unicodedata.normalize("NFKC", str(content or ""))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def build_elements(arxiv_id: str, version_elements: dict):
    """
    Deduplicate normalized (kind, content) across versions.

    Preserve positional alignment with the original node lists:
    empty nodes receive None instead of being removed from the ID list.
    """
    unique = {}
    rows = []
    ids = {}
    counters = {}

    for version, items in version_elements.items():
        ids[version] = []

        for item in items:
            kind = str(item.get("kind", "sentence"))
            content = normalize_element_content(item.get("content", ""))

            if not content:
                ids[version].append(None)
                continue

            key = (kind, content)

            # Root nodes must remain version-specific.
            if kind == "document":
                key = (kind, version, content)

            if key not in unique:
                counters[kind] = counters.get(kind, 0) + 1
                prefix = PREFIX.get(kind, kind[:2] or "e")
                element_id = f"{arxiv_id}#{prefix}{counters[kind]}"

                unique[key] = element_id

                rows.append({
                    "element_id": element_id,
                    "arxiv_id": arxiv_id,
                    "kind": kind,
                    "content": content,
                })

            ids[version].append(unique[key])

    return rows, ids


def build_formula_elements(arxiv_id: str, version_formulas: dict):
    converted = {}

    for version, formulas in version_formulas.items():
        converted[version] = [
            {"kind": "formula", "content": f.get("content", "")}
            for f in formulas
        ]

    return build_elements(arxiv_id, converted)