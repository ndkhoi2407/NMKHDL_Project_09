
from pathlib import Path

from latex_gatherer import (
    find_root_tex,
    expand_document_content,
)


def main():
    source_dir = Path("data/2608-24007/v1")

    root_tex = find_root_tex(source_dir)

    segments = expand_document_content(root_tex)

    print("=== DOCUMENT CONTENT IN SOURCE ORDER ===")
    print(f"Total segments: {len(segments)}")

    for index, segment in enumerate(segments, start=1):
        content = segment["content"].strip()

        print(f"\nSegment {index}")
        print(f"File: {segment['file'].name}")
        print(f"Start: {segment['start']}")
        print(f"End: {segment['end']}")
        print(f"Characters: {len(segment['content'])}")
        print(f"Preview: {content[:150]!r}")

    print("\n=== FILE ORDER ===")

    file_order = []

    for segment in segments:
        if segment["file"] not in file_order:
            file_order.append(segment["file"])

    for index, tex_file in enumerate(file_order, start=1):
        print(f"{index}. {tex_file.name}")


if __name__ == "__main__":
    main()
