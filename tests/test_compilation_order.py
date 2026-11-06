
from pathlib import Path

from latex_gatherer import find_root_tex, gather_compilation_path


def main():
    source_dir = Path("data/2608-24007/v1")

    root_tex = find_root_tex(source_dir)
    tex_files = gather_compilation_path(source_dir)

    print("=== ROOT TEX ===")
    print(root_tex)

    print("\n=== COMPILATION FILE ORDER ===")

    for index, tex_file in enumerate(tex_files, start=1):
        print(f"{index}. {tex_file}")


if __name__ == "__main__":
    main()
