"""Validate and publish an individual six-table Parquet dataset to Hugging Face."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from src.milestone3.export import TABLES, in_range, schema_for


def validate_bundle(dataset: Path, minimum: str, maximum: str) -> dict:
    if not minimum or not maximum:
        raise ValueError("Both endpoints of the student's assigned arXiv range are required.")
    if minimum > maximum:
        raise ValueError("The minimum arXiv ID must not be greater than the maximum.")
    summary_path = dataset / "export_summary.json"
    card_path = dataset / "README.md"
    if not summary_path.is_file() or not card_path.is_file():
        raise FileNotFoundError("The dataset folder must include README.md and export_summary.json.")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("mode") != "parquet":
        raise ValueError("The dataset manifest is not a completed Parquet export.")
    if summary.get("student_arxiv_min") != minimum or summary.get("student_arxiv_max") != maximum:
        raise ValueError("The manifest arXiv range does not match the confirmed student range.")
    card = card_path.read_text(encoding="utf-8")
    if not card.startswith("---\nconfigs:") or f"`{minimum}` through `{maximum}`" not in card:
        raise ValueError("The Hugging Face dataset card is missing valid table metadata or ID scope.")
    for table in TABLES:
        if (f"- config_name: {table}" not in card
                or f"path: data/{table}/*.parquet" not in card):
            raise ValueError(f"The Hugging Face dataset card is missing the {table} configuration.")

    try:
        import pyarrow.parquet as pq
    except ImportError as error:
        raise RuntimeError("Install pyarrow before validating the Parquet files.") from error

    for table in TABLES:
        table_dir = dataset / "data" / table
        expected = summary.get("tables", {}).get(table)
        if (not isinstance(expected, dict)
                or not isinstance(expected.get("rows"), int)
                or expected["rows"] <= 0
                or not isinstance(expected.get("parquet_shards"), int)
                or expected["parquet_shards"] <= 0):
            raise ValueError(f"{table}: manifest has no rows to publish.")
        files = sorted(table_dir.glob("part-*.parquet"))
        all_parquet = sorted(table_dir.glob("*.parquet"))
        if len(files) != expected.get("parquet_shards") or files != all_parquet:
            raise ValueError(f"{table}: Parquet shard files do not match the manifest.")
        observed_rows = 0
        for shard in files:
            parquet = pq.ParquetFile(shard)
            if not parquet.schema_arrow.equals(schema_for(table), check_metadata=False):
                raise ValueError(f"{shard}: schema does not match the required {table} schema.")
            if "arxiv_id" not in parquet.schema_arrow.names:
                raise ValueError(f"{shard}: missing arxiv_id column.")
            observed_rows += parquet.metadata.num_rows
            for batch in parquet.iter_batches(columns=["arxiv_id"], batch_size=25_000):
                for identifier in batch.column(0).to_pylist():
                    if not isinstance(identifier, str) or not in_range(identifier, minimum, maximum):
                        raise ValueError(f"{shard}: contains arxiv_id outside the assigned range.")
        if observed_rows != expected["rows"]:
            raise ValueError(f"{table}: {observed_rows} Parquet rows, expected {expected['rows']}.")
    return summary


def publish(dataset: Path, repo_id: str, minimum: str, maximum: str, confirm_public: bool) -> str:
    if not confirm_public:
        raise ValueError("Publishing requires explicit --confirm-public consent.")
    if not re.fullmatch(r"[^/\s]+/[^/\s]+", repo_id):
        raise ValueError("Use a Hugging Face dataset repo ID in OWNER/NAME form.")
    dataset = dataset.resolve()
    summary = validate_bundle(dataset, minimum, maximum)
    if summary.get("manual_labeling_complete") is not True:
        raise ValueError("Manual labels are not confirmed as human-reviewed; publication is blocked.")
    if summary.get("training_complete") is not True:
        raise ValueError("The model has not been retrained after manual review; publication is blocked.")
    try:
        from huggingface_hub import HfApi
        from huggingface_hub.errors import RepositoryNotFoundError
    except ImportError as error:
        raise RuntimeError(
            "Install the project requirements, including huggingface_hub, before publishing."
        ) from error

    api = HfApi()
    try:
        info = api.repo_info(repo_id=repo_id, repo_type="dataset")
    except RepositoryNotFoundError:
        api.create_repo(repo_id=repo_id, repo_type="dataset", private=False, exist_ok=False)
        info = api.repo_info(repo_id=repo_id, repo_type="dataset")
    if info.private:
        raise ValueError(
            f"{repo_id} already exists as a private dataset. No visibility settings were changed."
        )

    card_path = dataset / "README.md"
    card = card_path.read_text(encoding="utf-8").replace("OWNER/DATASET", repo_id)
    card_path.write_text(card, encoding="utf-8")
    api.upload_folder(
        folder_path=str(dataset),
        repo_id=repo_id,
        repo_type="dataset",
        commit_message="Publish individual arXiv project dataset",
        allow_patterns=["README.md", "export_summary.json", "data/**/*.parquet"],
    )
    info = api.repo_info(repo_id=repo_id, repo_type="dataset")
    if info.private:
        raise RuntimeError("The dataset repository is not public after upload.")

    dataset_url = f"https://huggingface.co/datasets/{repo_id}"
    summary["published_online"] = True
    summary["huggingface_dataset_url"] = dataset_url
    summary_path = dataset / "export_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    api.upload_file(
        path_or_fileobj=str(summary_path),
        path_in_repo="export_summary.json",
        repo_id=repo_id,
        repo_type="dataset",
        commit_message="Record public dataset URL",
    )
    return dataset_url


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--repo-id", required=True, help="Your Hugging Face dataset ID: OWNER/NAME")
    parser.add_argument("--min-id", required=True, help="Inclusive assigned arXiv ID range start")
    parser.add_argument("--max-id", required=True, help="Inclusive assigned arXiv ID range end")
    parser.add_argument("--confirm-public", action="store_true", help="Confirm creation/upload of a public dataset")
    args = parser.parse_args()
    url = publish(args.dataset, args.repo_id, args.min_id, args.max_id, args.confirm_public)
    print(f"Published public dataset: {url}")
    print("Paste this public URL into the course Moodle submission field.")


if __name__ == "__main__":
    main()
