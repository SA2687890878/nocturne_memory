import asyncio, json, os, runpy, sqlite3, sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
y=runpy.run_path(str(HERE/'continue_g2.py'))
x,need,load,put,digest=(y[k] for k in ('x','need','load','put','digest'))
AUTH=HERE/'tokenizer-repair-authorization.json'
OUT=HERE/'index-repair.json'
m=load(x['INPUT']);x['validate_input'](m)
plan=load(y['PLAN']);y['validate'](plan,m)
def validate(a):
    need(a['decision']=='授权定点修复（推荐）' and a['namespace']=='' and a['databaseUrl']==x['pinned_url'](),'Repair authorization/target mismatch')
    need(a['g3Allowed'] is False and a['oldDatabaseAllowed'] is False,'Scope expansion refused')
    need(a['sourceSha256']==digest(x['ROOT']/'backend/db/search_terms.py'),'Approved source changed')
    need(a['greenReceiptSha256']==digest(HERE/'tokenizer-green.json'),'Regression receipt changed')
    green=load(HERE/'tokenizer-green.json')
    need(green['failed']==0 and green['passed']==4 and green['codeSha256']==a['sourceSha256'],'Green regression required')
async def run():
    need(not OUT.exists(),'Repair receipt exists; inspect before retry')
    a=load(AUTH);validate(a);y['verify'](plan,m)
    backup=x['BACKUPS']/y['BATCH']
    r={'status':'running','startedAt':x['now'](),'authorizationSha256':digest(AUTH),'repairScriptSha256':digest(__file__),'sourceSha256':a['sourceSha256'],'databaseUrl':x['pinned_url'](),'namespace':'','oldDatabaseOpened':False,'g3Performed':False,'scope':'existing SearchIndexer rebuild API on fixed new trial DB only; no business node/content/edge/keyword changes'}
    guard=sqlite3.connect(str(x['TARGET']));guard.execute('SELECT count(*) FROM sqlite_master').fetchone()
    os.environ.update(x['pins']());sys.path.insert(0,str(x['BACKEND']))
    config_before=digest(x['ROOT']/'config.json')
    try:
        r['aclBefore']=x['protect']()
        r['beforeBackup']=x['backup_db'](x['TARGET'],backup/'before-index-rebuild.sqlite')
        from db import get_effective_database_url
        from db.database import DatabaseManager
        from db.search import SearchIndexer
        need(get_effective_database_url()==x['pinned_url'](),'Effective database is not the approved new trial')
        manager=DatabaseManager(x['pinned_url']())
        try:
            need(str(manager.engine.url)==x['pinned_url'](),'Manager target mismatch')
            await manager.init_db()
            indexer=SearchIndexer(manager)
            await indexer.rebuild_all_search_documents()
            r['searchProbes']=[]
            for b in plan['bindings']:
                found=await indexer.search(b['keyword'],limit=10,domain='core',namespace='')
                need(any(v['uri']==b['targetUri'] for v in found),'Rebuilt index missed keyword: '+b['keyword'])
                r['searchProbes'].append({'keyword':b['keyword'],'targetUri':b['targetUri'],'status':'PASS'})
        finally:
            await manager.close()
        y['verify'](plan,m)
        r['audit']=x['audit_new'](m)
        r['priorKeywordVerificationStatus']=load(HERE/'keyword-verification.json')['status']
        r['fullMcpVerification']='pending separate verify_keywords.py --finish; structural/index PASS is not overall G2 PASS'
        r['checkpoint']=list(guard.execute('PRAGMA wal_checkpoint(FULL)').fetchone())
        need(r['checkpoint'][0]==0,'Checkpoint busy')
        r['afterBackup']=x['backup_db'](x['TARGET'],backup/'after-index-rebuild.sqlite')
        y['verify'](plan,m,backup/'after-index-rebuild.sqlite')
        r['aclAfter']=x['protect']()
        need(digest(x['ROOT']/'config.json')==config_before,'Daily config changed')
        need(r['aclBefore']['parentAclSha256']==r['aclAfter']['parentAclSha256'],'Existing parent ACL changed')
        r['status']='PASS'
    except BaseException as e:
        r.update(status='FAILED',errorType=type(e).__name__,error=str(e)[:600]);raise
    finally:
        guard.close();r['completedAt']=x['now']();put(OUT,r)
    print(json.dumps({'status':r['status'],'auditBlockers':r['audit']['blockers'],'businessNodes':33,'nativeBindings':8},ensure_ascii=True))
if __name__=='__main__':
    if sys.argv[1:]==['--self-test']:
        a=load(AUTH);validate(a)
        for field,value in [('namespace','other'),('databaseUrl','sqlite+aiosqlite:///wrong.db'),('oldDatabaseAllowed',True),('g3Allowed',True)]:
            bad=dict(a);bad[field]=value
            try:validate(bad)
            except RuntimeError:continue
            raise RuntimeError('Repair boundary accepted: '+field)
        print(json.dumps({'selfTest':'PASS','negativeGuards':4,'filesystemWrites':0}))
    elif sys.argv[1:]==['--run']:asyncio.run(run())
    else:raise RuntimeError('Only --self-test and --run are allowed')
