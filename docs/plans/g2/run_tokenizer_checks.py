import hashlib, importlib.util, json, runpy, sys, traceback
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
phase=sys.argv[1] if len(sys.argv)==2 else ''
assert phase in ('red','green','green-final')
out=HERE/f'tokenizer-{phase}.json'
assert not out.exists(), 'Do not overwrite existing test evidence'
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'backend'))
test_path=ROOT/'backend/tests/unit/test_search_terms.py'
tests=runpy.run_path(str(test_path))
results=[]
for name, fn in tests.items():
    if name.startswith('test_') and callable(fn):
        try:
            fn();results.append({'name':name,'status':'PASS'})
        except Exception:
            results.append({'name':name,'status':'FAIL','traceback':traceback.format_exc()})
assert len(results)==4, 'Expected the same four regression functions'
r={'phase':phase,'executedAt':datetime.now(timezone.utc).isoformat(),'runner':'stdlib direct execution of unchanged pytest-style test functions; no conftest loaded','pytestInstalled':importlib.util.find_spec('pytest') is not None,'codeSha256':hashlib.sha256((ROOT/'backend/db/search_terms.py').read_bytes()).hexdigest(),'testsSha256':hashlib.sha256(test_path.read_bytes()).hexdigest(),'results':results,'passed':sum(v['status']=='PASS' for v in results),'failed':sum(v['status']=='FAIL' for v in results),'scope':'pure tokenizer tests and an in-memory SQLite FTS table; fresh subprocess for cold query; no production or trial DB fixture'}
out.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'phase':phase,'passed':r['passed'],'failed':r['failed'],'pytestInstalled':r['pytestInstalled']},ensure_ascii=True))
sys.exit(1 if r['failed'] else 0)
