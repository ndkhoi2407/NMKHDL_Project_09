"""Separate M2 benchmark: end-to-end wall time, peak RAM and output storage."""
from __future__ import annotations
import argparse, json, subprocess, sys, time
from pathlib import Path
try:
    import psutil
except ImportError:
    psutil=None

def _size_bytes(folder):
    return sum(p.stat().st_size for p in Path(folder).rglob("*") if p.is_file())

def benchmark(data="data",output="m2_output",discovery="discovery.json",limit=None,
              sample_interval=0.1):
    script=Path(__file__).with_name("m2_pipeline.py")
    cmd=[sys.executable,str(script),"--data",str(data),"--output",str(output),
         "--discovery",str(discovery)]
    if limit is not None: cmd += ["--limit",str(limit)]
    process=subprocess.Popen(cmd)
    monitored=psutil.Process(process.pid) if psutil else None
    peak=0; started=time.perf_counter()
    while process.poll() is None:
        if monitored:
            try:
                rss=monitored.memory_info().rss
                for child in monitored.children(recursive=True):
                    try: rss+=child.memory_info().rss
                    except psutil.Error: pass
                peak=max(peak,rss)
            except psutil.Error: pass
        time.sleep(sample_interval)
    elapsed=time.perf_counter()-started
    if process.returncode:
        raise subprocess.CalledProcessError(process.returncode,cmd)
    out=Path(output)
    summary=json.loads((out/"summary.json").read_text(encoding="utf-8"))
    summary["benchmark_wall_seconds"]=round(elapsed,3)
    summary["peak_ram_mb_sampled"]=round(peak/(1024**2),2) if peak else None
    summary["output_storage_mb"]=round(_size_bytes(out)/(1024**2),3)
    (out/"benchmark.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    return summary

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--data",default="data"); p.add_argument("--output",default="m2_output")
    p.add_argument("--discovery",default="discovery.json"); p.add_argument("--limit",type=int)
    a=p.parse_args(); benchmark(a.data,a.output,a.discovery,a.limit)
if __name__=="__main__": main()
