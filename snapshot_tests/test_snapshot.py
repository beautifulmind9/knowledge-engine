import ast
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import pytest

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*a,**k):raise AssertionError('No network allowed')
    monkeypatch.setattr(socket,'socket',deny)
    monkeypatch.setattr(socket,'create_connection',deny)

def test_exact_allowlist_and_copied_fingerprints():
    m=json.loads((ROOT/'PUBLICATION-MANIFEST.json').read_text())
    expected={e['path'] for e in m['copied_files']}|set(m['generated_files'])
    tracked=set(subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines())
    assert tracked==expected
    for e in m['copied_files']:
        assert hashlib.sha256((ROOT/e['path']).read_bytes()).hexdigest()==e['sha256']

def test_no_private_or_binary_artifacts():
    tracked=subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines()
    assert all(not p.startswith(('legacy/','storage/','.git/')) for p in tracked)
    assert all(not p.endswith(('.pdf','.zip','.sqlite3','.docx','.env')) for p in tracked)
    assert all(not (ROOT/p).is_symlink() and b'\0' not in (ROOT/p).read_bytes() for p in tracked)

def test_selected_python_reference_sources_compile_without_importing_app():
    for p in list((ROOT/'apps/api').rglob('*.py'))+list((ROOT/'tools').glob('*.py')):
        ast.parse(p.read_text(),filename=str(p))

def test_synthetic_rights_and_frozen_fixture():
    text=(ROOT/'acceptance/extraction_quality_2026-10-17/source.md').read_text()
    assert 'Original synthetic material' in text and 'not copied or adapted' in text
    fixture=ROOT/'experiments/source_first/fixture.json'
    expected=(fixture.parent/'fixture.sha256').read_text().split()[0]
    assert hashlib.sha256(fixture.read_bytes()).hexdigest()==expected
