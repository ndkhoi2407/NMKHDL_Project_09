"""Check static book artifacts and executed outputs after a MyST HTML build."""
import json
from pathlib import Path
from html.parser import HTMLParser

ROOT = Path(__file__).resolve().parents[1]
html_root = ROOT / '_build/html'

class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
    def handle_data(self, data):
        self.parts.append(data)

for route in ['', 'm1-crawling', 'm2-parsing', 'crawling-stats', 'colab-benchmarks']:
    file = html_root / route / 'index.html'
    content = file.read_text(encoding='utf-8')
    assert '<html' in content and len(content) > 10000, file
    text = Text()
    text.feed(content)
    rendered = ' '.join(' '.join(text.parts).split())
    assert 'Not measured MiB' not in rendered and 'Not measured s ' not in rendered, file
    assert 'A separate course rubric was not supplied' not in rendered, file
    print('HTML OK:', '/' + route)

notebooks = list((ROOT / '_build/execute').rglob('*.ipynb'))
assert len(notebooks) == 4, f'Expected 4 executable pages, found {len(notebooks)}; clean execution cache first'
charts = 0
for file in notebooks:
    notebook = json.loads(file.read_text(encoding='utf-8'))
    for cell in notebook['cells']:
        for output in cell.get('outputs', []):
            assert output.get('output_type') != 'error', (file, output)
            charts += 'application/vnd.plotly.v1+json' in output.get('data', {})
assert charts >= 13, charts
print(f'Execution OK: {len(notebooks)} pages, {charts} interactive charts; no cell errors')

baseline = json.loads((ROOT / 'audit_data/corpus_audit.json').read_text(encoding='utf-8'))
import hashlib
for name, expected in baseline['measured_export_sha256'].items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
print('Original measured export hashes unchanged')
implementation = json.loads((ROOT / 'audit_data/implementation_checks.json').read_text(encoding='utf-8'))
for name, expected in implementation['code_sha256'].items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
print('Current implementation matches separately recorded fix evidence; historical source fingerprints retained')
