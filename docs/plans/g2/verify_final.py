import hashlib, json, os, runpy, sqlite3, sys
from datetime import datetime, timezone
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
x=runpy.run_path(str(HERE/'run_trial.py'))
m=x['load'](x['INPUT']);x['validate_input'](m);os.environ.update(x['pins']())
def read_copy(p):
    c=sqlite3.connect('file:'+Path(p).as_posix()+'?mode=ro&immutable=1',uri=True)
    try:
        rows=c.execute('SELECT p.domain,p.path,m.content,e.priority,e.disclosure FROM paths p JOIN memories m ON m.node_uuid=p.node_uuid AND m.deprecated=0 JOIN edges e ON e.id=p.edge_id WHERE p.path<>?',('',)).fetchall()
        actual={d+'://'+p:(body,pri,disc) for d,p,body,pri,disc in rows}
        assert len(actual)==33
        for n in m['nodes']: assert actual[n['uri']]==(n['content'],n['priority'],n['disclosure'])
        boot=json.loads(c.execute('SELECT boot_uris FROM presets WHERE is_active=1').fetchone()[0])
        assert boot['']==m['bootUris']
        assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert not c.execute('PRAGMA foreign_key_check').fetchall()
        counts={t:c.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ['nodes','paths','memories','edges','search_documents','search_documents_fts']}
        missing=c.execute('SELECT n.uuid FROM nodes n WHERE NOT EXISTS (SELECT 1 FROM paths p WHERE p.node_uuid=n.uuid)').fetchall()
        assert counts['nodes']==34 and counts['paths']==counts['memories']==counts['edges']==33
        assert missing==[('00000000-0000-0000-0000-000000000000',)]
        assert c.execute('SELECT count(*) FROM memories WHERE node_uuid=?',(missing[0][0],)).fetchone()[0]==0
        return {'status':'PASS','businessNodes':33,'counts':counts,'rootSentinelWithoutMemory':True,'boot':'2/2','integrity':'ok','mode':'ro+immutable, main file self-contained'}
    finally: c.close()
result={'phase':'G2-final-storage-verification','verifiedAt':datetime.now(timezone.utc).isoformat(),'result':'PASS','verifier':{'path':str(Path(__file__).resolve()),'sha256':x['digest'](__file__)},'currentHelperSha256':x['digest'](HERE/'run_trial.py'),'mainFile':read_copy(x['TARGET']),'backup':read_copy(x['BACKUPS']/x['BATCH']/'trial-populated.sqlite'),'restoreCopy':read_copy(x['BACKUPS']/x['BATCH']/'restored-validation.sqlite'),'audit':x['audit_new'](m),'g3Performed':False,'naturalLanguageCases':{'count':174,'executionStatus':'not_run'},'uncovered':['full natural-language routing behavior','G3 connection/rule switch','future WAL recreation directory protection']}
x['safe_sources'](m)
x['put'](HERE/'final-verification.json',result)
print(json.dumps({'result':result['result'],'mainFile':result['mainFile'],'backup':'PASS','restoreCopy':'PASS','auditBlockers':result['audit']['blockers'],'verifierSha256':result['verifier']['sha256']},ensure_ascii=True))
