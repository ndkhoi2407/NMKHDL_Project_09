from pathlib import Path
from collections import Counter, defaultdict
import json
import sys

base = Path("data/milestone2/records_data/records")
full = "--all" in sys.argv

samples = [
    "2607-13695",  # Multiple TeX files
    "2607-16774",  # Two versions
    "2607-17102",  # Plain TeX
    "2607-17969",  # Plain TeX
]

folders = (
    sorted(p for p in base.iterdir() if p.is_dir())
    if full else [base / name for name in samples]
)

errors = []
counts = Counter()

def read(folder, name):
    with (folder / f"{name}.jsonl").open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]

def fail(paper, message):
    errors.append(f"{paper}: {message}")

for number, folder in enumerate(folders, 1):
    paper = folder.name

    try:
        elements = read(folder, "elements")
        edges = read(folder, "hierarchy")
        refs = read(folder, "bibtex")
        versions = read(folder, "versions")
    except (OSError, json.JSONDecodeError) as e:
        fail(paper, f"Cannot read JSONL: {e}")
        continue

    counts["publications"] += 1

    ids = [e["element_id"] for e in elements]
    lookup = {e["element_id"]: e for e in elements}
    keys = [r["citation_key"] for r in refs]

    # Element and bibliography identity
    if len(ids) != len(lookup):
        fail(paper, "Duplicate element IDs")

    if len(keys) != len(set(keys)):
        fail(paper, "Duplicate citation keys")

    # Positional items and document roots are allowed
    # to have identical text but distinct IDs.
    content = [
        (e["kind"], e["content"])
        for e in elements
        if e["kind"] not in ("document", "list", "item") and not e.get("structural_exception")
    ]
    if len(content) != len(set(content)):
        fail(paper, "Duplicate normalized content")

    # Parent-child edges
    by_version = defaultdict(list)
    seen_edges = set()

    for edge in edges:
        n = edge["version"]
        child = edge["element_id"]
        parent = edge["parent_id"]

        by_version[n].append(edge)

        identity = (n, child, parent)
        if identity in seen_edges:
            fail(paper, "Duplicate hierarchy edge")
        seen_edges.add(identity)

        if child not in lookup or parent not in lookup:
            fail(paper, "Missing parent or child")

        if child == parent:
            fail(paper, "Self-parent edge")

    # Version coverage and connectivity
    valid_versions = {v["version"] for v in versions}

    for n in by_version:
        if n not in valid_versions:
            fail(paper, f"Unknown hierarchy version: {n}")

    for v in versions:
        n = v["version"]
        status = v["parse_status"]
        root = v.get("root_id")
        ve = by_version[n]

        counts["versions"] += 1
        counts[status] += 1

        if status == "empty":
            if root is not None or ve:
                fail(paper, f"v{n}: empty with root/edges")
            continue

        if status != "ok":
            fail(paper, f"v{n}: status={status}")
            continue

        if root not in lookup or lookup[root]["kind"] != "document":
            fail(paper, f"v{n}: invalid document root")
            continue

        if not v.get("root_file") or not v.get("files_used"):
            fail(paper, f"v{n}: missing source files")

        # Check reachability from document root
        children = defaultdict(list)
        for e in ve:
            children[e["parent_id"]].append(e["element_id"])

        visited = {root}
        stack = [root]

        while stack:
            for child in children[stack.pop()]:
                if child not in visited:
                    visited.add(child)
                    stack.append(child)

        unreachable = {
            e["element_id"] for e in ve
        } - visited

        if unreachable:
            fail(paper, f"v{n}: {len(unreachable)} unreachable nodes")

        # Canonical citation targets must exist
        for canonical in v.get(
            "canonical_citation_keys", {}
        ).values():
            if canonical not in keys:
                fail(paper, f"v{n}: missing canonical citation")

    if not full:
        print(f"\nPAPER {paper}")
        print("Statuses:", [v["parse_status"] for v in versions])
        print("Elements:", len(elements))
        print("Hierarchy:", len(edges))
        print("BibTeX:", len(refs))

        for v in versions:
            print(
                f"  v{v['version']} root={v.get('root_file')}",
                "files_used=", v.get("files_used", [])
            )

        if paper == "2607-16774":
            a = {e["element_id"] for e in by_version[1]}
            b = {e["element_id"] for e in by_version[2]}
            print("Shared element IDs v1/v2:", len(a & b))

    elif number % 500 == 0:
        print(
            f"AUDIT {number}/{len(folders)} | issues={len(errors)}",
            flush=True
        )

if full:
    expected = {
        "publications": 5000,
        "versions": 6417,
        "ok": 6105,
        "empty": 312,
    }
    for key, value in expected.items():
        if counts[key] != value:
            fail("TOTAL", f"{key}={counts[key]}, expected={value}")

result = {
    "scope": "full" if full else "sample",
    "counts": dict(counts),
    "problem_count": len(errors),
    "problems": errors[:50],
}

destination = Path("../report_repo/report_data") / (
    "milestone2_quality_full.json" if full
    else "milestone2_quality_sample.json"
)
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(
    json.dumps(result, indent=2, ensure_ascii=False),
    encoding="utf-8"
)

print("\nAUDIT FINISHED")
print("Publications:", counts["publications"])
print("Problems:", len(errors))
print("Saved:", destination)

for error in errors[:20]:
    print("FAIL:", error)

if errors:
    sys.exit(1)

print("PASS: BASIC STRUCTURAL AUDIT")
