import json, runpy, sqlite3
from datetime import datetime, timezone
from pathlib import Path
HERE=Path(__file__).resolve().parent
b=runpy.run_path(str(HERE/'routing_boundary.py'))
x,y,need,load,put,digest=(b[k] for k in ('x','y','need','load','put','digest'))
m=b['expected']();plan=b['keyword_plan']
g=runpy.run_path(str(HERE/'evaluate_routing.py'))
def immutable(path):
    c=sqlite3.connect('file:'+path.as_posix()+'?mode=ro&immutable=1',uri=True)
    try:
        rows=c.execute("SELECT p.domain,p.path,m.content,e.priority,e.disclosure,p.namespace FROM paths p JOIN memories m ON m.node_uuid=p.node_uuid AND m.deprecated=0 JOIN edges e ON e.id=p.edge_id WHERE p.path<>''").fetchall()
        actual={d+'://'+p:(body,pri,disc,ns) for d,p,body,pri,disc,ns in rows}
        need(actual=={n['uri']:(n['content'],n['priority'],n['disclosure'],'') for n in m['nodes']},'Current approved memory state mismatch')
        words=c.execute("SELECT g.keyword,p.domain||'://'||p.path FROM glossary_keywords g JOIN paths p ON p.node_uuid=g.node_uuid AND p.namespace=g.namespace ORDER BY 1,2").fetchall()
        need(words==sorted((v['keyword'],v['targetUri']) for v in plan['bindings']),'Keyword binding drift')
        need(json.loads(c.execute('SELECT boot_uris FROM presets WHERE is_active=1').fetchone()[0])=={'':m['bootUris']},'Boot mismatch')
        need(c.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and not c.execute('PRAGMA foreign_key_check').fetchall(),'Integrity failure')
        return {'path':path.as_posix(),'mode':'ro+immutable without WAL','status':'PASS','activeBusinessNodes':len(actual),'keywordBindings':len(words),'memoryVersions':c.execute('SELECT count(*) FROM memories').fetchone()[0]}
    finally:c.close()
def run():
    out=HERE/'routing-boundary-final.json';need(not out.exists(),'Final recheck receipt already exists')
    patch=load(HERE/'routing-boundary-receipt.json');need(patch['status']=='PASS','Patch did not finish')
    inputs=load(HERE/'routing-recheck-inputs.json')['cases']
    mapping={v['caseKey']:v['originalId'] for v in load(HERE/'routing-recheck-map.json')['mapping']}
    requests=load(HERE/'routing-recheck-requests.json');req={v['caseKey']:v for v in requests['cases']}
    fetch=load(HERE/'routing-recheck-fetch.json');fet={v['caseKey']:v for v in fetch['cases']}
    correction=load(HERE/'routing-recheck-correction.json')
    hashes=correction['hashes']
    need(hashes['originalObserved']['sha256']==digest(HERE/'routing-recheck-observed.json') and hashes['correctedObserved']['sha256']==digest(HERE/'routing-recheck-observed-corrected.json'),'Observation correction chain changed')
    need(hashes['requests']['sha256']==digest(HERE/'routing-recheck-requests.json') and hashes['fetch']['sha256']==digest(HERE/'routing-recheck-fetch.json'),'Native read evidence changed during correction')
    observed=load(HERE/'routing-recheck-observed-corrected.json');obs={v['caseKey']:v for v in observed['cases']}
    original_observations={v['caseKey']:v for v in load(HERE/'routing-recheck-observed.json')['cases']}
    need(all(c['readUris']==original_observations[key]['readUris'] and c['readFiles']==original_observations[key]['readFiles'] and c['actions']==original_observations[key]['actions'] for key,c in obs.items()),'Correction changed actual read/action choices')
    need(fetch['status']=='PASS' and fetch['requestSha256']==digest(HERE/'routing-recheck-requests.json'),'Actual read evidence changed')
    keys={v['caseKey'] for v in inputs};need(len(keys)==len(obs)==len(observed['cases'])==6 and keys==set(req)==set(fet)==set(obs)==set(mapping),'Incomplete/injected recheck cases')
    expected={v['id']:v for v in load(x['ROOT']/'docs/plans/g1/routing-cases.json')['cases']}
    initial=load(HERE/'routing-results.json')
    need(initial['frozenExpectedSha256']==digest(x['ROOT']/'docs/plans/g1/routing-cases.json'),'Frozen expectations changed')
    files={g['norm'](v['path']):v for v in observed['fileEvidence']}
    results=[]
    for key,c in obs.items():
        need(set(c['readUris'])==set(req[key]['readUris'])=={v['uri'] for v in fet[key]['reads']},'Claimed memory reads differ from native evidence')
        need(all(g['norm'](p) in files for p in c['readFiles']),'Missing file read evidence')
        need(all(files[g['norm'](p)]['readMethod'] in ('read','ctx_execute') and files[g['norm'](p)]['note'] for p in c['readFiles']),'File evidence missing method/anchor')
        original=mapping[key];a=g['assess'](expected[original]['expected'],c)
        results.append({'id':original,'caseKey':key,'routeAssertionsPass':a['routeAssertionsPass'],'criticalSafetyPass':a['criticalSafetyPass'],'modeMatches':a['modeMatches'],'issues':{k:v for k,v in a.items() if isinstance(v,list) and v},'readUris':c['readUris'],'readFiles':c['readFiles'],'decision':c['decision']})
    y['verify'](plan,m)
    checks=[immutable(p) for p in (x['TARGET'],Path(patch['afterBackup']['path']),Path(patch['restoreCopy']['path']))]
    audit=x['audit_new'](m);x['safe_sources'](m)
    latest={v['id']:v['routeAssertionsPass'] for v in initial['cases']}
    latest.update({v['id']:v['routeAssertionsPass'] for v in results})
    remaining=sorted(k for k,v in latest.items() if not v)
    r={'verifiedAt':datetime.now(timezone.utc).isoformat(),'status':'PASS' if not remaining else 'PARTIAL','frozenExpectedSha256':initial['frozenExpectedSha256'],'initialRouting':{'passed':initial['routingPass'],'total':174},'affectedRetest':{'count':6,'passed':sum(v['routeAssertionsPass'] for v in results),'cases':sorted(results,key=lambda v:v['id'])},'combinedCoverage':{'covered':174,'latestPassing':sum(latest.values()),'remainingFailedIds':remaining,'scope':'Initial 174-case run plus one fresh six-case affected-area recheck; not a second full 174-case rerun'},'approvedBodyChanges':1,'unchangedBodies':32,'nativeKeywordBindings':8,'boot':patch['boot'],'keywordMatrix':{'positive':8,'negative':256},'auditBlockers':audit['blockers'],'untriggeredLeafAdvisories':len(audit['report']['untriggered_leaves']),'immutableChecks':checks,'artifactHashes':{p:digest(HERE/p) for p in ('routing-boundary-plan.json','routing_boundary.py','routing-boundary-receipt.json','routing-context-v2.json','routing-recheck-inputs.json','routing-recheck-map.json','routing-recheck-requests.json','routing-recheck-fetch.json','routing-recheck-observed.json','routing-recheck-observed-corrected.json','routing-recheck-correction.json','routing-results.json','tokenizer-green-final.json','keyword-final.json')},'runtimeConfigSha256':digest(x['ROOT']/'config.json'),'g3Performed':False,'oldDatabaseOpened':False,'uncovered':['Daily MCP/Web end-to-end and actual rule adoption','Full pytest suite: not installed; four same regression functions ran with stdlib','Per-scenario cold-start token/cost comparison','Long-term WAL/SHM recreation ACL','No second complete 174-case run after the one-node clarification'],'residual':['Glossary is read-time cross-linking, not automatic user-message listening','Scenario simulations used a source directory as auxiliary input; no claim about daily-session minimal-token routing'],'confidence':{'nativeDataAndKeywords':'A','assistedRoutingRecheck':'B','dailyBehaviorAndCost':'not_verified'}}
    put(out,r)
    print(json.dumps({'status':r['status'],'affectedRetest':str(r['affectedRetest']['passed'])+'/6','combinedLatestPassing':str(sum(latest.values()))+'/174','remainingFailedIds':remaining,'immutableCopies':len(checks),'g3Performed':False},ensure_ascii=True))
if __name__=='__main__':run()
