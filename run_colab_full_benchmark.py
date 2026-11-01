#!/usr/bin/env python3
"""Measure an entire arXiv crawler run on Colab CPU-only.

Execute the crawler phases in a fresh output folder. Poll the crawler's
process tree for RSS and its output directory for disk consumption. This
script does not fill in benchmark results from historic Windows logs.

Example from a Google Colab cell after uploading this file and crawler.py:

    !python /content/run_colab_full_benchmark.py \
        --crawler /content/milestone1/src/crawler.py \
        --output /content/milestone1/full_cpu_benchmark \
        --report /content/drive/MyDrive/Milestone1_Backup/benchmark_source_full_colab.json

WARNING: Running all 5000 papers from scratch can take many hours, invoke
external arXiv/Semantic Scholar services, and download substantial data.
The script refuses an existing nonempty output directory to avoid overwrites.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import shutil
from datetime import datetime, timezone


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def tree_rss_bytes(pid):
    """Sum resident memory for the full crawler process tree."""
    try:
        import psutil

        root = psutil.Process(pid)
        members = [root] + root.children(recursive=True)
        total = 0
        for proc in members:
            try:
                total += proc.memory_info().rss
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return total
    except psutil.NoSuchProcess:
        return 0


def disk_usage_bytes(folder):
    # `du` measures on-disk usage. -s supplies only a single observation;
    # -B1 selects bytes without including free space on the Colab VM.
    result = subprocess.run(
        ["du", "-s", "-B1", str(folder)], capture_output=True, text=True,
        check=True, timeout=60,
    )
    return int(result.stdout.split()[0])


def bytes_or_none(v):
    return None if v is None else int(v)


def build_report(state, output, sample_interval, disk_interval):
    samples = state["ram_samples"]
    total_seconds = state["end_to_end_runtime_seconds"]
    return {
        "benchmark_scope": "end_to_end",
        "testbed": "Google Colab CPU-only (validated by runtime check)",
        "testbed_verified": state.get("testbed_verified", False),
        "end_to_end_runtime_verified": bool(
            state["all_phases_completed"] and state.get("testbed_verified")
            and (not state.get("requires_ref_dates") or
                 state["summary"].get("reference_date_enrichment_rate") == 1.0)
        ),
        "run_started_at": state["started_at"],
        "run_finished_at": state.get("finished_at"),
        "assigned_ids": 5000,
        "start_arxiv_id": "2607.13694",
        "end_arxiv_id": "2607.18693",
        "phase_wall_seconds": state["phase_wall_seconds"],
        "end_to_end_runtime_seconds": total_seconds,
        "average_seconds_per_required_paper": (
            round(total_seconds / 5000, 6) if total_seconds is not None else None
        ),
        "discovery_runtime_seconds": state["phase_wall_seconds"].get("discover"),
        "peak_process_tree_ram_bytes": max(samples) if samples else None,
        "average_process_tree_ram_bytes": (
            round(sum(samples) / len(samples)) if samples else None
        ),
        "ram_samples": len(samples),
        "ram_sample_interval_seconds": sample_interval,
        "peak_output_disk_bytes_observed": (
            max(state["disk_samples"]) if state["disk_samples"] else None
        ),
        "disk_samples": len(state["disk_samples"]),
        "disk_sample_interval_seconds": disk_interval,
        "final_output_disk_bytes": (
            state["disk_samples"][-1] if state["disk_samples"] else None
        ),
        "output_folder": str(output),
        "all_phases_completed": state["all_phases_completed"],
        "phase_failures": state["phase_failures"],
        "source_summary": state["summary"],
        "measurement_notes": [
            "Wall time includes the measured crawler phase processes and phase handoffs.",
            "RSS is sampled for crawler process trees; a discrete sampling peak may miss short spikes.",
            "Peak disk is the maximum sampled du usage, not a continuous-time mathematical maximum.",
            "The final benchmark is valid only when all phases complete and the 5000-paper summary passes checks."
        ],
    }


def write_report(state, args):
    report = build_report(state, args.output, args.ram_every, args.disk_every)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.report.with_suffix(args.report.suffix + ".partial")
    tmp.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(args.report)


def run_one_phase(args, state, phase):
    logs = args.output / "_benchmark_logs"
    logs.mkdir(exist_ok=True)
    cmd = [
        sys.executable, str(args.crawler),
        "--start", "2607.13694", "--end", "2607.18693",
        "--max-papers", "5000",
        "--phase", phase,
        "--arxiv-delay", str(args.arxiv_delay),
        "--progress-every", "100",
        "--output", str(args.output),
        "--wait-on-429",
        "--cooldown-minutes", str(args.cooldown_minutes),
        "--max-cooldowns", str(args.max_cooldowns),
    ]
    begin = time.monotonic()
    next_disk = 0.0
    print(f"[{now_utc()}] START {phase}", flush=True)
    with (logs / f"{phase}.log").open("w", encoding="utf-8") as log:
        with subprocess.Popen(
            cmd, stdout=log, stderr=subprocess.STDOUT,
            cwd=args.crawler.parent.parent,
        ) as proc:
            while True:
                # Capture a sample while the process still exists.
                memory = tree_rss_bytes(proc.pid)
                if memory:
                    state["ram_samples"].append(memory)
                elapsed = time.monotonic() - begin
                if elapsed >= next_disk:
                    try:
                        state["disk_samples"].append(disk_usage_bytes(args.output))
                    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                        pass
                    next_disk = elapsed + args.disk_every
                if proc.poll() is not None:
                    break
                time.sleep(args.ram_every)
            status = proc.wait()
    state["phase_wall_seconds"][phase] = round(time.monotonic() - begin, 3)
    state["disk_samples"].append(disk_usage_bytes(args.output))
    write_report(state, args)
    print(
        f"[{now_utc()}] END {phase}, exit={status}, "
        f"seconds={state['phase_wall_seconds'][phase]}", flush=True
    )
    return status


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--crawler", type=Path,
                        default=Path("/content/milestone1/src/crawler.py"))
    parser.add_argument("--output", type=Path,
                        default=Path("/content/milestone1/full_cpu_benchmark"))
    parser.add_argument("--report", type=Path,
                        default=Path("/content/drive/MyDrive/Milestone1_Backup/benchmark_source_full_colab.json"))
    parser.add_argument("--arxiv-delay", type=float, default=3.2)
    parser.add_argument("--ram-every", type=float, default=1.0)
    parser.add_argument("--disk-every", type=float, default=30.0)
    parser.add_argument("--cooldown-minutes", type=float, default=60.0)
    parser.add_argument("--max-cooldowns", type=int, default=2)
    parser.add_argument("--with-enrich-refs", action="store_true",
                        help="Include required reference first-submission-date enrichment")
    args = parser.parse_args()
    try:
        import google.colab  # type: ignore[reportMissingImports]  # noqa: F401
    except ImportError:
        parser.error("Run this benchmark inside Google Colab, not on the local machine.")
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi and subprocess.run([nvidia_smi], capture_output=True).returncode == 0:
        parser.error("A GPU is visible. Switch the Colab runtime to CPU-only and rerun.")
    args.output = args.output.resolve()
    args.crawler = args.crawler.resolve()
    if not args.crawler.is_file():
        parser.error(f"Crawler file not found: {args.crawler}")
    try:
        import psutil  # noqa: F401
    except ImportError:
        parser.error("psutil is required: in a Colab cell, run !pip -q install psutil")
    if args.output.exists() and any(args.output.iterdir()):
        parser.error(
            f"Refusing nonempty output folder: {args.output}. "
            "Choose a NEW benchmark folder; do not delete checkpoints."
        )
    args.output.mkdir(parents=True, exist_ok=True)
    phases = ["discover", "metadata", "sources", "references"]
    if args.with_enrich_refs:
        phases.append("enrich-refs")
    state = {
        "started_at": now_utc(), "finished_at": None,
        "phase_wall_seconds": {}, "ram_samples": [], "disk_samples": [],
        "phase_failures": [], "summary": {}, "all_phases_completed": False,
        "end_to_end_runtime_seconds": None, "testbed_verified": True,
        "requires_ref_dates": args.with_enrich_refs,
    }
    started = time.monotonic()
    try:
        for phase in phases:
            status = run_one_phase(args, state, phase)
            if status != 0:
                state["phase_failures"].append({"phase": phase, "exit_code": status})
                raise RuntimeError(
                    f"Phase {phase} failed (exit={status}). See "
                    f"{args.output / '_benchmark_logs' / (phase + '.log')}"
                )
        summary_path = args.output / "summary.json"
        if summary_path.is_file():
            raw = json.loads(summary_path.read_text(encoding="utf-8"))
            keys = [
                "assigned_ids", "discovered_papers", "total_versions_expected",
                "total_versions_source_checked", "versions_with_tex_bib",
                "pending_discovery", "pending_source_versions", "pending_s2_papers",
                "pending_exact_version_metadata", "output_disk_bytes",
                "average_observed_paper_seconds", "maximum_observed_paper_seconds",
                "total_versions_metadata_exact", "references_with_arxiv_id",
                "reference_date_enrichment_rate",
            ]
            state["summary"] = {k: raw.get(k) for k in keys}
            state["all_phases_completed"] = (
                raw.get("assigned_ids") == 5000
                and raw.get("discovered_papers") == 5000
                and raw.get("pending_discovery") == 0
                and raw.get("pending_source_versions") == 0
                and raw.get("pending_s2_papers") == 0
                and raw.get("pending_exact_version_metadata") == 0
                and (not args.with_enrich_refs or
                     raw.get("reference_date_enrichment_rate") == 1.0)
            )
        state["requires_ref_dates"] = args.with_enrich_refs

    finally:
        state["end_to_end_runtime_seconds"] = round(time.monotonic() - started, 3)
        state["finished_at"] = now_utc()
        state["disk_samples"].append(disk_usage_bytes(args.output))
        write_report(state, args)
        print("Benchmark report:", args.report, flush=True)
        print("All phases completed:", state["all_phases_completed"], flush=True)
    if not state["all_phases_completed"]:
        sys.exit("Coverage validation incomplete; benchmark is NOT full coverage.")


if __name__ == "__main__":
    main()
