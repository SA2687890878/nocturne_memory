import hashlib, json, runpy, sqlite3
from datetime import datetime, timezone
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
y=runpy.run_path(str(HERE/'continue_g2.py'))
x,need,load,digest=(y[k] for k in ('x','need','load','digest'))
m=load(x['INPUT']);x['validate_input'](m)
plan=load(y['PLAN']);y['validate'](plan,m)
k=load(HERE/'keyword-final.json');idx=load(HERE/'index-repair.json');routing=load(HERE/'routing-results.json');green=load(HERE/'tokenizer-green-final.json')
need(k['status']==idx['status']=='PASS' and green['failed']==0 and green['passed']==4,'Capability verification incomplete')
need(green['codeSha256']==digest(ROOT/'backend/db/search_terms.py') and green['testsSha256']==digest(ROOT/'backend/tests/unit/test_search_terms.py'),'Final regression sources drifted')
need(k['restart']['keywordTargets']==8 and k['nativeReadMatrix']['positivePairs']==8 and k['nativeReadMatrix']['negativePairs']==256,'Keyword evidence incomplete')
paths=[x['TARGET'],Path(k['afterBackup']['path']),Path(k['restoreCopy']['path'])]
checks=[]
for p in paths:
    c=sqlite3.connect('file:'+p.as_posix()+'?mode=ro&immutable=1',uri=True)
    try:
        rows=c.execute("SELECT p.domain,p.path,m.content,e.priority,e.disclosure,p.namespace FROM paths p JOIN memories m ON m.node_uuid=p.node_uuid AND m.deprecated=0 JOIN edges e ON e.id=p.edge_id WHERE p.path<>''").fetchall()
        actual={d+'://'+path:(body,pri,disc,ns) for d,path,body,pri,disc,ns in rows}
        expected={n['uri']:(n['content'],n['priority'],n['disclosure'],'') for n in m['nodes']}
        need(actual==expected,'Immutable body/metadata mismatch')
        words=c.execute("SELECT g.keyword,p.domain||'://'||p.path FROM glossary_keywords g JOIN paths p ON p.node_uuid=g.node_uuid AND p.namespace=g.namespace ORDER BY 1,2").fetchall()
        need(words==sorted((b['keyword'],b['targetUri']) for b in plan['bindings']),'Immutable keyword mismatch')
        need(json.loads(c.execute('SELECT boot_uris FROM presets WHERE is_active=1').fetchone()[0])=={'':m['bootUris']},'Immutable boot mismatch')
        need(c.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and not c.execute('PRAGMA foreign_key_check').fetchall(),'Immutable integrity failure')
        counts={t:c.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ('nodes','memories','paths','edges','search_documents','search_documents_fts','glossary_keywords')}
        need(counts=={'nodes':34,'memories':33,'paths':33,'edges':33,'search_documents':33,'search_documents_fts':33,'glossary_keywords':8},'Immutable row counts changed')
        checks.append({'path':p.as_posix(),'mode':'ro+immutable; main file without WAL','status':'PASS','counts':counts})
    finally:c.close()
x['safe_sources'](m)
files=['continue_g2.py','keyword-continuation.json','keyword-receipt.json','keyword-verification.json','keyword-final.json','verify_keywords.py','repair_keyword_index.py','index-repair.json','tokenizer-repair-authorization.json','run_tokenizer_checks.py','tokenizer-red.json','tokenizer-green.json','tokenizer-green-final.json','evaluate_routing.py','routing-inputs-a.json','routing-inputs-b.json','routing-context.json','routing-key-map.json','routing-requests-a.json','routing-requests-b.json','routing-fetch-a.json','routing-fetch-b.json','routing-observed-a.json','routing-observed-b.json','routing-results.json']
observed=[c for b in ('a','b') for c in load(HERE/f'routing-observed-{b}.json')['cases']]
obs={c['caseKey']:c for c in observed}
no_route_reads=sum(c['expectedMode']=='no_route' and bool(obs[c['caseKey']]['readUris'] or obs[c['caseKey']]['readFiles']) for c in routing['cases'])
r={'verifiedAt':datetime.now(timezone.utc).isoformat(),'evidenceCollection':'PASS','g2Acceptance':'NOT_ACCEPTED','keywordCapability':'PASS','tokenizerFix':'PASS','immutableChecks':checks,'businessBodiesUnchanged':33,'nativeKeywordBindings':8,'nativeKeywordTargetNodes':len({b['targetUri'] for b in plan['bindings']}),'bootBytes':k['boot']['utf8Bytes'],'keywordMatrix':{'positive':8,'negative':256},'freshMcpKeywordTargets':8,'audit':{'blockers':k['audit']['blockers'],'untriggeredLeafAdvisories':len(k['audit']['report']['untriggered_leaves'])},'routing':{'executed':174,'requiredAndForbiddenReadAssertionsPass':routing['routingPass'],'failed':routing['routingFail'],'failedIds':[c['id'] for c in routing['cases'] if not c['routeAssertionsPass']],'strictModeMatches':routing['strictModePass'],'closedListUnsafeActions':174-routing['criticalSafetyPass'],'noRouteCasesWithOtherReads':no_route_reads,'uniqueMemoryUris':len({p for c in observed for p in c['readUris']}),'uniqueFilePaths':len({p for c in observed for p in c['readFiles']}),'scope':'assisted fresh-agent scenario simulation with actual isolated MCP reads and bounded source-file reads; not daily E2E or per-case cold-start benchmark'},'artifactHashes':{name:digest(HERE/name) for name in files},'sourceHashes':{p:digest(ROOT/p) for p in ('backend/db/search_terms.py','backend/tests/unit/test_search_terms.py')},'runtimeConfigSha256':digest(ROOT/'config.json'),'oldDatabaseOpened':False,'g3Performed':False,'action':['stdlib regression red/green-final','native manage_triggers 8 additions; duplicate additions skipped','fixed-trial SearchIndexer.rebuild_all_search_documents','isolated MCP full keyword matrix and fresh-process search','174 blind routing simulations and frozen expectation scoring','immutable main/backup/restore-copy validation'],'result':'Keywords and tokenizer verified; raw routing gate still 170/174, do not relabel G2 fully accepted','scope':['new fixed work-memory.db','one logical tokenizer source line and two regression functions','G2 evidence and owned backups only'],'uncovered':['Full pytest suite: pytest not installed; same four test functions ran with stdlib instead','Daily MCP/Web end-to-end cutover and rule application','Per-scenario cold-start token/cost comparison','Long-term WAL/SHM recreation ACL','Four frozen routing read-boundary assertions remain failed; peer interpretation is not a changed expectation'],'residual':['Glossary links are not an automatic user-message listener','A peer classified three read failures as fixture semantics and one as overread; strict results stay unchanged pending boundary resolution','Existing daily processes were not restarted; future processes load changed tokenizer code'],'confidence':{'keywordsAndStorage':'A','assistedRouting':'B','dailyUseAndCost':'unverified'}}
out=HERE/'continuation-final.json';need(not out.exists(),'Final receipt exists; inspect instead of overwrite')
x['put'](out,r)
print(json.dumps({'evidenceCollection':r['evidenceCollection'],'g2Acceptance':r['g2Acceptance'],'keywords':8,'freshMcpTargets':8,'immutableCopies':len(checks),'routing':str(routing['routingPass'])+'/174'},ensure_ascii=True))
