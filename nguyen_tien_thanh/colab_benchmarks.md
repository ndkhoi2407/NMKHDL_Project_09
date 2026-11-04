# Google Colab CPU benchmark protocol

**Status: instructions prepared; no Colab measurements are available.** Existing Windows exports remain in `m1_data/` and `m2_data/`. Do not relabel them as Colab runs.

The final testbed is specified by the [official M1 performance requirements](https://hcmus-cs-ta.github.io/lab-book/intro-ds/statement/crawling/) and [M2 report requirements](https://hcmus-cs-ta.github.io/lab-book/intro-ds/statement/parsing/).

## Executable workflow (recommended)

Open `notebooks/colab_cpu_benchmarks.ipynb` in Google Colab, select CPU-only runtime, and upload the reviewed checkout including `src/` and `scripts/`. The notebook contains no outputs and defaults to plan mode. Set its explicit opt-in only when ready for the complete assigned range.

The same runner can be reviewed locally without executing a benchmark:

```powershell
python scripts/colab_benchmark.py --stage both --workdir /content/arxiv-new-run --single-trial
```

On a genuine Colab CPU runtime, explicit execution is:

```python
!python /content/arxiv-code/scripts/colab_benchmark.py --stage both --workdir /content/arxiv-new-run --single-trial --workers 2 --execute
```

Supply `S2_API_KEY` privately first. Existing run paths are refused. M2-only mode accepts `--input-data` and copies it while excluding previous parse outputs; the input is never modified. The runner retains environment/source hashes, exact commands, logs, independent corpus-disk samples, full benchmark summaries, a separate single-paper trial and separately timed merged-table export. Offline fixture tests cover plan mode, CPU guards, isolated input copying and retained failure artifacts. Those tests are not Colab performance results.

Current archive-size statistics distinguish logical uncompressed member bytes (read from archive metadata without extracting unwanted files) from actual retained corpus bytes and sampled peak disk. Never label logical member sizes as measured temporary storage.

## 1. Prepare an isolated runtime

Choose **Runtime → Change runtime type → CPU** (hardware accelerator: None). Upload a reviewed copy of the project's `src/` directory to `/content/arxiv-code/src/`, or clone the reviewed code commit into `/content/arxiv-code`. Do not benchmark the unreviewed default branch: local code may not have been pushed yet.

Install only the pipeline dependencies; the report's Python 3.14 environment is separate from Colab's supplied interpreter:

```python
%pip install arxiv==4.0.2 requests==2.34.2 psutil==7.2.2
```

Create a new directory for each run. Never mount the original Windows corpus as writable benchmark storage. Run on Colab's local disk, and copy results to durable storage afterward.

```python
import hashlib, json, os, platform, shutil, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
import psutil

code = Path('/content/arxiv-code').resolve()
assert (code / 'src/benchmark.py').exists()
assert os.environ.get('COLAB_GPU', '0') in ('0', ''), 'Select a CPU-only runtime'
assert not any(os.environ.get(key) for key in ['TPU_NAME', 'COLAB_TPU_ADDR']), 'Disable TPU acceleration'
if shutil.which('nvidia-smi'):
    gpu = subprocess.run(['nvidia-smi', '-L'], capture_output=True, text=True)
    assert gpu.returncode != 0 or not gpu.stdout.strip(), 'Select a CPU-only runtime first'

stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
run = Path('/content') / ('arxiv-m1-' + stamp)
run.mkdir(exist_ok=False)
os.chdir(run)
environment = {
    'platform': platform.platform(), 'python': sys.version,
    'cpu_count': psutil.cpu_count(), 'ram_bytes': psutil.virtual_memory().total,
    'disk_free_bytes_before': shutil.disk_usage(run).free,
    'cpuinfo': Path('/proc/cpuinfo').read_text(),
    'packages': subprocess.check_output([sys.executable, '-m', 'pip', 'freeze'], text=True),
    'source_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((code/'src').glob('*.py'))},
    'testbed': 'Google Colab CPU-only; selected manually and checked for visible NVIDIA devices',
}
(run/'environment.json').write_text(json.dumps(environment, indent=2))
```

Supply the Semantic Scholar key without printing it or saving it in the notebook:

```python
import getpass
os.environ['S2_API_KEY'] = getpass.getpass('Semantic Scholar API key: ')
```

## 2. M1 fresh end-to-end run

Use the reviewed corrected revision with source-only extraction, raw-reference preservation and versioned metadata enabled. Historical corpus gaps remain separate; any residual failure must be reported in the new run. Do not delete any existing `data/`: use a new run directory instead.

```python
assert not (run/'data').exists(), 'Use a new directory for a cold local-state run'
command = [sys.executable, str(code/'src/benchmark.py'),
           '--prefix', '2607', '--start', '3694', '--end', '8693', '--interval', '1']
(run/'command.json').write_text(json.dumps(command))
import threading, time
disk_samples, stop_disk = [], threading.Event()
def sample_corpus_disk():
    started = time.perf_counter()
    while not stop_disk.is_set():
        corpus = run/'data'
        if corpus.exists():
            sample = subprocess.run(['du', '-sb', str(corpus)], capture_output=True, text=True)
            if sample.returncode == 0:
                disk_samples.append({'seconds': time.perf_counter()-started,
                                     'apparent_corpus_bytes': int(sample.stdout.split()[0])})
        stop_disk.wait(1)
monitor = threading.Thread(target=sample_corpus_disk, daemon=True)
monitor.start()
try:
    with (run/'m1.log').open('w') as log:
        result = subprocess.run(command, cwd=run, stdout=log, stderr=subprocess.STDOUT)
finally:
    stop_disk.set()
    monitor.join()
    (run/'corpus_disk_samples.json').write_text(json.dumps(disk_samples, indent=2))
print('Return code:', result.returncode)
```

Inspect `data/timings.json`: discovery must actually execute, rather than be skipped. Retain the process-tree RAM samples, summary, per-paper records, error counts and logs, including failed runs. On Linux the existing monitor prefers PSS when available and otherwise RSS; retain its `memory.metric` value. Its disk series is the sampled change in total filesystem usage, **not an exact corpus-only absolute disk peak**: unrelated filesystem writes may affect it, and short peaks may be missed. The separate `du -sb` series above records apparent corpus bytes at roughly one-second intervals plus scan overhead; its maximum is a sampled observation, not a guarantee of the instantaneous peak. Record allocated bytes separately if filesystem allocation is required. Neither a final directory size nor baseline plus delta is a directly measured corpus peak.

Measure one publication separately using the existing `single_trial` helper, outside the full-run timing, and retain the resulting JSON. This helper runs into a temporary directory and removes only its own temporary output:

```python
import argparse
sys.path.insert(0, str(code/'src'))
import benchmark
trial = benchmark.single_trial(argparse.Namespace(prefix='2607', start=3694, skip=''))
(run/'single_paper_trial.json').write_text(json.dumps(trial, indent=2))
```

The trial covers only that publication, not the distribution of all publications. Average full-run time is wall time divided by the stated processed-paper denominator.

## 3. M2 fresh parsing run

Prepare an isolated copy of the verified M1 input, including discovery and download statuses. Check local free disk before copying; a second corpus plus parsed outputs can exceed the instance capacity. The M1 results above can be used directly if no parsing outputs exist, avoiding a second copy. Do not include any existing `parsed.json`, `parse_status.json` or merged tables. No `--fresh` deletion is necessary with genuinely fresh inputs.

```python
os.chdir(run)
assert not (run/'data/parse_status.json').exists()
assert not list((run/'data').glob('*/parsed.json'))
assert not (run/'data/tables').exists()
command = [sys.executable, str(code/'src/benchmark_parse.py'), '--workers', '2', '--interval', '1']
(run/'m2-command.json').write_text(json.dumps(command))
with (run/'m2.log').open('w') as log:
    result = subprocess.run(command, cwd=run, stdout=log, stderr=subprocess.STDOUT)
print('Return code:', result.returncode)
```

Worker count is explicit for reproducibility; record the runtime's actual CPU allocation. The existing benchmark times parser execution and per-publication JSON output. Merged-table export is a separate operation (`parse.py --export-only`); if performed, record its time and bytes separately rather than folding unmeasured work into the parser wall time.

## 4. Archive and publish evidence

Retain `environment.json`, commands, logs, raw samples, summaries, per-paper records, discovery timings and output sizes. Verify all expected IDs and versions, distinguish processing completion from parsing success, and report residual failures. Export small report inputs into a **new Colab-labelled directory**, preserving the Windows exports. Add Colab figures only after reviewing those actual artifacts. No expected runtime, RAM, disk or success result is predicted here.
