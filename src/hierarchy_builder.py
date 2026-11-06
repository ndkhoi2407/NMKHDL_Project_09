"""Hierarchy edge construction and integrity validation for M2."""
from __future__ import annotations


def build_hierarchy_rows(
    arxiv_id: str,
    version: int,
    element_ids: list[str | None],
    parent_indices: list[int | None],
):
    """
    Convert ordered nodes into hierarchy edges.

    Empty nodes have ID None. When a node's immediate parent is empty,
    attach it to the nearest existing ancestor.
    """
    if len(element_ids) != len(parent_indices):
        raise ValueError(
            "element_ids and parent_indices must have equal length"
        )

    rows = []

    for index, parent_index in enumerate(parent_indices):
        child_id = element_ids[index]

        # An empty child is not represented in the elements table.
        if child_id is None:
            continue

        visited = set()

        while parent_index is not None:
            if (
                not isinstance(parent_index, int)
                or parent_index < 0
                or parent_index >= len(element_ids)
            ):
                raise ValueError(
                    f"Invalid parent index {parent_index} for node {index}"
                )

            if parent_index in visited:
                raise ValueError(
                    f"Cycle detected in parent chain for node {index}"
                )

            visited.add(parent_index)
            parent_id = element_ids[parent_index]

            if parent_id is not None:
                rows.append({
                    "arxiv_id": arxiv_id,
                    "version": int(version),
                    "element_id": child_id,
                    "parent_id": parent_id,
                })
                break

            # Skip empty ancestors and search higher in the tree.
            parent_index = parent_indices[parent_index]

    return rows


def validate_hierarchy(elements, hierarchy):
    """Return referential-integrity and schema errors."""
    element_ids = {
        row.get("element_id")
        for row in elements
    }

    errors = []

    for i, row in enumerate(hierarchy):
        if not row.get("element_id"):
            errors.append(f"hierarchy[{i}] missing element_id")

        if not row.get("parent_id"):
            errors.append(f"hierarchy[{i}] missing parent_id")

        if row.get("element_id") not in element_ids:
            errors.append(
                f"hierarchy[{i}] element_id not in elements"
            )

        if row.get("parent_id") not in element_ids:
            errors.append(
                f"hierarchy[{i}] parent_id not in elements"
            )

        if not isinstance(row.get("version"), int):
            errors.append(
                f"hierarchy[{i}] version is not int"
            )

    return errors