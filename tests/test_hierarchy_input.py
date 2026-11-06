from latex_gatherer import expand_document_content
from latex_parser import parse_all_headings, parse_all_environments
from mixed_extractor import extract_mixed_elements

SOURCE_DIR = "data/2608-24007/v1"

print("=== 1. DOCUMENT SEGMENTS ===")
segments = expand_document_content(
    __import__("pathlib").Path(SOURCE_DIR) / "main.tex"
)

print("Type:", type(segments))
print("First segment:")
print(segments[0])

print("\n=== 2. HEADINGS ===")
headings = parse_all_headings(SOURCE_DIR)

print("Total:", len(headings))
print("First heading:")
print(headings[0])

print("\n=== 3. ENVIRONMENTS ===")
environments = parse_all_environments(SOURCE_DIR)

print("Total:", len(environments))
print("First environment:")
print(environments[0])

print("\n=== 4. MIXED ELEMENTS ===")
elements = extract_mixed_elements(segments[0]["content"])

print("Total:", len(elements))
print("First element:")
print(elements[0])