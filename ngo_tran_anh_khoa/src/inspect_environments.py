
from pathlib import Path

from latex_parser import extract_environments


def main():
    tex_file = Path(
        "data/2608-24007/v1/sections/theory.tex"
    )

    environments = extract_environments(tex_file)

    target_names = {
        "trainingsetup",
        "datasetting",
        "initializationsetting",
        "theorem",
    }

    for env in environments:
        if env["name"] in target_names:
            print(f"\n--- {env['name']} ---")
            print(f"Title: {env['title']}")
            print("Content:")
            print(env["content"][:700])


if __name__ == "__main__":
    main()
