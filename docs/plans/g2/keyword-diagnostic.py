import hashlib, importlib.util, json, runpy
from pathlib import Path
from contextlib import closing
HERE=Path(__file__).resolve().parent
x=runpy.run_path(str(HERE/'run_trial.py'))
t=runpy.run_path(str(x['BACKEND']/'db/search_terms.py'))
word='多项目工作区'
cold=t['expand_query_terms'](word).split()
synthetic=t['build_document_search_terms']('x','core://x','','',word).split()
warm=t['expand_query_terms'](word).split()
with closing(x['ro'](x['TARGET'])) as c:
    row=c.execute("SELECT uri,search_terms FROM search_documents WHERE uri='core://agent/environment/workspaces'").fetchone()
    actual=row[1].split()
    boot=c.execute('SELECT name,is_active,boot_uris FROM presets').fetchall()
    keywords=c.execute('SELECT keyword,namespace FROM glossary_keywords ORDER BY keyword').fetchall()
spec=importlib.util.spec_from_file_location('g2_keyword_diagnostic_audit',x['BACKEND']/'scripts/audit_memory.py')
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a);a.db_path=lambda:x['TARGET'].as_posix()
report=a.audit()
r={'scope':'read-only fixed new trial database; pure tokenizer calls in this process; no application/database repair','coldQueryTokens':cold,'warmQueryTokens':warm,'syntheticIndexMissingColdTokens':sorted(set(cold)-set(synthetic)),'actualTargetUri':row[0],'actualTargetMissingColdTokens':sorted(set(cold)-set(actual)),'actualTargetContainsWholeKeyword':word in actual,'activePresets':boot,'nativeBindings':keywords,'auditBlockers':a.issue_count(report),'audit':report,'diagnosticSha256':x['digest'](__file__)}
x['put'](HERE/'keyword-diagnostic.json',r)
print(json.dumps({k:r[k] for k in ('coldQueryTokens','warmQueryTokens','syntheticIndexMissingColdTokens','actualTargetMissingColdTokens','actualTargetContainsWholeKeyword','auditBlockers')},ensure_ascii=True))
