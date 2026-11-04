"""Static Pages wiring and publishable-file checks. Does not push or deploy."""
from pathlib import Path
import subprocess
import yaml

ROOT=Path(__file__).resolve().parents[1]
workflow=yaml.load((ROOT/'.github/workflows/deploy.yml').read_text(encoding='utf-8'),Loader=yaml.BaseLoader)
assert set(workflow['on'])=={'push','workflow_dispatch'}
assert workflow['permissions']=={'contents':'read','pages':'write','id-token':'write'}
steps=workflow['jobs']['deploy']['steps']
assert any(s.get('run')=='npm run build' and 'BASE_URL' in s.get('env',{}) for s in steps)
assert any(s.get('run')=='python scripts/validate_html.py' for s in steps)
assert any(s.get('uses')=='actions/upload-pages-artifact@v3' and s['with']['path']=='_build/html' for s in steps)
assert any(s.get('uses')=='actions/deploy-pages@v4' for s in steps)
assert any('check_pipeline.py' in s.get('run','') and 'check_colab_workflow.py' in s.get('run','') for s in steps)
files=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT).decode().split('\0')
for name in filter(None,files):
    parts=Path(name).parts
    assert not any(p in {'data','_build','node_modules','.venv','__pycache__','.aws'} for p in parts),name
    assert not Path(name).name.startswith('.env'),name
    assert (ROOT/name).stat().st_size<5*1024**2,f'Unexpected large publication input: {name}'
print('PASS: Pages YAML/build wiring and nonignored repository file inventory')
print('PARTIAL: GitHub execution, separate report repository and publication require remote review/approval')
