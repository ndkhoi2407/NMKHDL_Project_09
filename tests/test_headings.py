
from pathlib import Path
from src.latex_parser import parse_all_headings

source_dir = Path("data/2608-24007/v1")
headings = parse_all_headings(source_dir)

for index, heading in enumerate(headings, start=1):
    filename = Path(heading["file"]).name

    print(
        f'{index:02d}. '
        f'{heading["command"]}: '
        f'{heading["title"]} | '
        f'{filename} | '
        f'pos={heading["position"]}'
    )
