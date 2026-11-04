"""Verify fixes on fixtures and two isolated versions; optionally save current-code evidence."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--record',action='store_true',help='write audit_data/implementation_checks.json')
    args=ap.parse_args()
    baseline=json.loads((ROOT/'audit_data/corpus_audit.json').read_text(encoding='utf-8'))
    for name,digest in baseline['measured_export_sha256'].items():
        assert sha(ROOT/name)==digest,name
    suites=[]
    for name in ['check_parser_logic.py','check_pipeline.py','check_colab_workflow.py']:
        result=subprocess.run([sys.executable,str(ROOT/'scripts'/name)],cwd=ROOT,capture_output=True,text=True)
        print(result.stderr.strip())
        assert result.returncode==0,name
        suites.append({'suite':name,'result':'PASS','scope':'offline fixtures; no real benchmark'})
    spec=importlib.util.spec_from_file_location('arxiv_parser',ROOT/'src/parse.py')
    parser=importlib.util.module_from_spec(spec);spec.loader.exec_module(parser)
    probes=[]
    original_hashes={}
    for folder in ['2607-05431','2607-07654']:
        source=ROOT/'data'/folder/'v1'
        original=ROOT/'data'/folder/'parsed.json'
        original_hashes[str(original.relative_to(ROOT))]=sha(original)
        for path in source.iterdir():
            if path.is_file():original_hashes[str(path.relative_to(ROOT))]=sha(path)
        with tempfile.TemporaryDirectory(dir=ROOT/'.cache') as temp:
            target=Path(temp)/'v1';shutil.copytree(source,target)
            result=parser.parse_version(target)
            probes.append({'version':folder.replace('-','.')+'v1','status':result['status'],
                           'reason':result.get('reason'),'root':result.get('root_file'),
                           'scope':'isolated copy, in-memory version parse; no parsed.json written'})
    assert probes[0]['status']=='failed' and probes[0]['reason']=='no_root_file'
    assert probes[1]['status']=='ok',probes[1]
    for name,digest in original_hashes.items():assert sha(ROOT/name)==digest,name
    for name,digest in baseline['measured_export_sha256'].items():assert sha(ROOT/name)==digest,name
    sources=['src/parse.py','src/download_sources.py','src/discover.py','src/metadata.py','src/references.py','src/process_sources.py','src/main.py']
    evidence={'historical_exports_unchanged':True,'original_failure_files_unchanged':True,'suites':suites,
              'targeted_probes':probes,'code_sha256':{name:sha(ROOT/name) for name in sources},
              'scope':'current implementation tests; not corpus statistics or performance benchmarks'}
    if args.record:
        (ROOT/'audit_data/implementation_checks.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    print(json.dumps(evidence,indent=2))

if __name__=='__main__':main()
