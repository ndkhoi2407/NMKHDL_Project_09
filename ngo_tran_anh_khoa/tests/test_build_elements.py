
from element_builder import build_elements


def main():
    arxiv_id = "2608.24007"

    # Sample elements from two versions
    version_elements = {
        "v1": [
            {
                "kind": "heading",
                "content": "Introduction",
            },
            {
                "kind": "sentence",
                "content": "This is the first sentence.",
            },
            {
                "kind": "formula",
                "content": "E = mc^2",
            },
        ],
        "v2": [
            {
                "kind": "heading",
                "content": "Introduction",
            },
            {
                "kind": "sentence",
                "content": "This is the first sentence.",
            },
            {
                "kind": "formula",
                "content": "E = mc^2",
            },
            {
                "kind": "sentence",
                "content": "This is a new sentence.",
            },
        ],
    }

    elements, version_element_ids = build_elements(
        arxiv_id,
        version_elements
    )

    print("--- BUILD ELEMENTS TEST ---")
    print(f"Total unique elements: {len(elements)}")

    for version, element_ids in version_element_ids.items():
        print(f"{version}: {len(element_ids)} element references")

    print("\n--- ELEMENT DETAILS ---")

    for element in elements:
        print(
            element["element_id"],
            element["kind"],
            element["content"]
        )

    # Check shared IDs
    ids_v1 = set(version_element_ids["v1"])
    ids_v2 = set(version_element_ids["v2"])

    common_ids = ids_v1 & ids_v2

    print("\n--- SHARED ELEMENT CHECK ---")
    print(f"Shared element IDs: {len(common_ids)}")

    # Check that different kinds do not share an ID
    print("\n--- ELEMENT TYPE CHECK ---")

    type_pairs = [
        (element["kind"], element["element_id"])
        for element in elements
    ]

    print(f"Unique element IDs: {len(set(
        element_id for _, element_id in type_pairs
    ))}")


if __name__ == "__main__":
    main()
