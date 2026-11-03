"""Plan or explicitly execute isolated CPU-only Colab benchmarks. Never edits report exports."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]

def write(path, value):
    path.write_text(json.dumps(value, indent=2), encoding='utf-8')

def command(stage, workers):
    if stage == 'm1':
        return [sys.executable, str(ROOT/'src/benchmark.py'), '--prefix', '2607', '--start', '3694', '--end', '8693', '--interval', '1']
    return [sys.executable, str(ROOT/'src/benchmark_parse.py'), '--workers', str(workers), '--interval', '1']

def require_colab_cpu():
    import psutil
    if platform.system() != 'Linux' or not Path('/content').is_dir() or importlib.util.find_spec('google.colab') is None:
        raise RuntimeError('Execution requires Google Colab. Plan mode is available locally.')
    if os.environ.get('COLAB_GPU', '0') not in ('0', '') or any(os.environ.get(k) for k in ['TPU_NAME','COLAB_TPU_ADDR']):
        raise RuntimeError('Select CPU-only runtime (no GPU/TPU).')
    if shutil.which('nvidia-smi'):
        result = subprocess.run(['nvidia-smi', '-L'], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            raise RuntimeError('Visible GPU detected; select CPU-only runtime.')
    return {'platform': platform.platform(), 'python': sys.version, 'cpu_count': psutil.cpu_count(),
            'ram_bytes': psutil.virtual_memory().total, 'cpuinfo': Path('/proc/cpuinfo').read_text(),
            'packages': subprocess.check_output([sys.executable, '-m', 'pip', 'freeze'], text=True),
            'testbed': 'Google Colab CPU-only',
            'source_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'src').glob('*.py')}}

def monitored(command_line, workdir, name):
    """Record observed corpus disk peaks separately from filesystem-wide deltas."""
    samples, stop = [], threading.Event()
    started = time.perf_counter()
    def disk_sample():
        apparent = allocated = 0
        try:
            for directory, _, files in os.walk(workdir/'data'):
                for filename in files:
                    try:
                        info = (Path(directory)/filename).stat()
                        apparent += info.st_size
                        allocated += getattr(info, 'st_blocks', 0) * 512
                    except FileNotFoundError:
                        continue
            samples.append({'seconds':time.perf_counter()-started, 'apparent_bytes':apparent, 'allocated_bytes':allocated})
        except OSError as error:
            samples.append({'seconds':time.perf_counter()-started, 'error':type(error).__name__})
    def monitor():
        while not stop.is_set():
            disk_sample()
            stop.wait(1)
    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    write(workdir/(name+'-command.json'), command_line)
    try:
        with (workdir/(name+'.log')).open('w', encoding='utf-8') as log:
            result = subprocess.run(command_line, cwd=workdir, stdout=log, stderr=subprocess.STDOUT)
    finally:
        stop.set(); thread.join(); disk_sample()
        write(workdir/(name+'-disk-samples.json'), samples)
    write(workdir/(name+'-runner.json'), {'returncode':result.returncode,
          'wrapper_wall_seconds':time.perf_counter()-started,
          'note':'Wrapper includes summary generation; use benchmark summary for pipeline wall time. Disk peaks are sampled observations.'})
    return result.returncode

def seed_m2(source, destination):
    """Copy an input into a new sandbox, omitting all previous parser outputs."""
    if source.resolve() == destination.resolve() or source.resolve() in destination.resolve().parents:
        raise ValueError('M2 destination must not be inside its input source')
    if not (source/'discovery.json').is_file() or not (source/'download_status.json').is_file():
        raise ValueError('M2 input requires discovery.json and download_status.json')
    def ignore(directory, names):
        return [n for n in names if n in {'parsed.json','parse_status.json','tables','benchmark','benchmark_parse','_tmp'}]
    shutil.copytree(source, destination, ignore=ignore)

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--stage', choices=['m1','m2','both'], default='both')
    ap.add_argument('--workdir', type=Path, required=True, help='new directory below /content, outside code checkout')
    ap.add_argument('--input-data', type=Path, help='M2-only: copy of existing M1 data; never modified')
    ap.add_argument('--workers', type=int, default=2)
    ap.add_argument('--single-trial', action='store_true')
    ap.add_argument('--execute', action='store_true', help='explicitly start the requested full benchmark on Colab')
    a = ap.parse_args()
    if a.workers < 1: ap.error('--workers must be positive')
    stages = ['m1','m2'] if a.stage == 'both' else [a.stage]
    if a.stage == 'm2' and not a.input_data: ap.error('M2-only requires --input-data')
    if a.stage != 'm2' and a.input_data: ap.error('--input-data is only for M2-only runs; M1 must start empty')
    workdir = a.workdir.resolve()
    if not a.execute:
        print(json.dumps({'mode':'plan only; no files or datasets changed', 'workdir':str(workdir),
                          'commands':[command(s,a.workers) for s in stages], 'single_trial':a.single_trial}, indent=2))
        return 0
    environment = require_colab_cpu()
    if Path('/content') not in workdir.parents or workdir == ROOT or ROOT in workdir.parents or workdir.exists():
        ap.error('Use a new directory under /content outside the code checkout; existing paths are refused')
    workdir.mkdir(parents=True, exist_ok=False)
    environment['disk_before'] = dict(zip(['total','used','free'], shutil.disk_usage(workdir)))
    write(workdir/'environment.json', environment)
    if a.stage == 'm2':
        seed_m2(a.input_data.resolve(), workdir/'data')
    for stage in stages:
        rc = monitored(command(stage,a.workers),workdir,stage)
        if rc: return rc
        if stage == 'm1' and a.single_trial:
            sys.path.insert(0,str(ROOT/'src'))
            import benchmark
            trial = benchmark.single_trial(argparse.Namespace(prefix='2607',start=3694,skip=''))
            write(workdir/'single-paper-trial.json',trial)
            if trial['returncode']: return trial['returncode']
        if stage == 'm2':
            rc = monitored([sys.executable,str(ROOT/'src/parse.py'),'--export-only'],workdir,'m2-table-export')
            if rc: return rc
            write(workdir/'merged-table-sizes.json', {p.name:p.stat().st_size for p in (workdir/'data/tables').glob('*.jsonl')})
    print(f'Benchmark artifacts retained at {workdir}; no report exports overwritten.')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
