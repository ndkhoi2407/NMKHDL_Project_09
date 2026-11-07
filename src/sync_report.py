from __future__ import annotations
import argparse
from pathlib import Path
import shutil


def sync(data: Path, report: Path):
    out = report / "report_data"
    out.mkdir(parents=True, exist_ok=True)
    required = {
        "summary.json": data / "summary.json",
        "status.csv": data / "tables" / "status.csv",
        "runs.jsonl": data / "runs.jsonl",
    }
    optional = {
        "benchmark_discovery.json": data / "benchmark_discovery.json",
        "benchmark_source.json": data / "benchmark_source.json",
        "benchmark_full_colab.json": data / "benchmark_full_colab.json",
    }
    for name, source in required.items():
        if not source.is_file():
            raise FileNotFoundError(f"Required file missing: {source}. Run the crawler first.")
        shutil.copy2(source, out / name)
        print(f"Created: {out / name}")
    for name, source in optional.items():
        if source.is_file():
            shutil.copy2(source, out / name)
            print(f"Created: {out / name}")
        else:
            print(f"Not present yet (optional): {source}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Copy aggregate crawl and benchmark statistics into report repo")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    sync(args.data.resolve(), args.report.resolve())
