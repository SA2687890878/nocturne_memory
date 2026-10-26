import asyncio, copy, hashlib, json, os, runpy, sqlite3, sys
from contextlib import closing
from datetime import timedelta
from pathlib import Path
HERE=Path(__file__).resolve().parent
y=runpy.run_path(str(HERE/'continue_g2.py'))
x,need,load,put,digest=(y[k] for k in ('x','need','load','put','digest'))
PLAN=HERE/'routing-boundary-plan.json'
APPROVED_PLAN_SHA='4e7f6f8d87957a6bbd90fbbc18ce1335514939f65f17d50eb3a9e96f67b77a8d'
a=load(PLAN)
base=load(x['INPUT']);x['validate_input'](base)
keyword_plan=load(y['PLAN'])
URI='core://agent/source-catalog'
BACKUP=x['BACKUPS']/y['BATCH']
def validate(q):
    need(q['decision']=='同意按此补充并复验（推荐）' and q['databaseUrl']==x['pinned_url']() and q['namespace']=='' and q['g3Allowed'] is False,'Boundary authorization mismatch')
    need(q['targetUri']==URI and q['baseInputSha256']==digest(x['INPUT']),'Only approved existing catalog is writable')
    need(q['append']==a['append'] and q['disclosure']==a['disclosure'],'Approved prose changed')
    m=copy.deepcopy(base)
    n=next(n for n in m['nodes'] if n['uri']==URI)
    n['content']+=q['append'];n['disclosure']=q['disclosure']
    n['contentSha256']=hashlib.sha256(n['content'].encode()).hexdigest();n['contentBytes']=len(n['content'].encode())
    need(n['contentBytes']<=2400,'Existing body budget exceeded')
    return m
def expected():
    need(digest(PLAN)==APPROVED_PLAN_SHA,'Approved boundary plan changed')
    return validate(a)
async def patch():
    m=expected();out=HERE/'routing-boundary-receipt.json'
    need(not out.exists(),'Patch receipt exists; inspect before retry')
    y['verify'](keyword_plan,base)
    os.environ.update(x['pins']())
    guard=sqlite3.connect(str(x['TARGET']));guard.execute('SELECT count(*) FROM sqlite_master').fetchone()
    r={'status':'running','startedAt':x['now'](),'authorizationSha256':digest(PLAN),'scriptSha256':digest(__file__),'targetUri':URI,'unchangedBodies':32,'g3Performed':False,'oldDatabaseOpened':False,'calls':[]}
    try:
        r['aclBefore']=x['protect']();r['beforeBackup']=x['backup_db'](x['TARGET'],BACKUP/'before-routing-boundary.sqlite')
        from mcp import ClientSession,StdioServerParameters
        from mcp.client.stdio import stdio_client
        params=StdioServerParameters(command=sys.executable,args=[str(HERE/'run_trial.py'),'--server'],cwd=str(x['BACKEND']),env=x['pins']())
        # Existing client is intentionally read-only for prose; this one-shot capability cannot write other nodes.
        with (BACKUP/'mcp-stderr.log').open('a',encoding='utf-8') as log:
            async with stdio_client(params,errlog=log) as (rd,wr):
                async with ClientSession(rd,wr) as s:
                    await s.initialize()
                    before=next(n for n in base['nodes'] if n['uri']==URI)
                    after=next(n for n in m['nodes'] if n['uri']==URI)
                    calls=[('read_memory',{'uri':URI}),('update_memory',{'uri':URI,'append':a['append'],'disclosure':a['disclosure']}),('read_memory',{'uri':URI})]
                    for i,(name,args) in enumerate(calls):
                        result=await s.call_tool(name,args,read_timeout_seconds=timedelta(seconds=60))
                        text='\n'.join(getattr(v,'text','') for v in result.content)
                        need(not getattr(result,'isError',False) and not text.lstrip().startswith('Error:'),'Native boundary call failed')
                        if i==0:need(before['content'] in text and before['disclosure'] in text,'Catalog drifted before update')
                        if i==1:need(text.startswith('Success:'),'Native update unconfirmed')
                        if i==2:need(after['content'] in text and after['disclosure'] in text,'Native updated readback mismatch')
                        r['calls'].append({'tool':name,'uri':URI,'resultSha256':hashlib.sha256(text.encode()).hexdigest()})
                        put(out,r)
        y['verify'](keyword_plan,m)
        async with y['client'](r,keyword_plan) as call:
            await y['matrix'](keyword_plan,{n['uri']:n for n in m['nodes']},call,r)
        r['audit']=x['audit_new'](m)
        r['checkpoint']=list(guard.execute('PRAGMA wal_checkpoint(FULL)').fetchone());need(r['checkpoint'][0]==0,'Checkpoint busy')
        r['afterBackup']=x['backup_db'](x['TARGET'],BACKUP/'after-routing-boundary.sqlite')
        r['restoreCopy']=x['backup_db'](BACKUP/'after-routing-boundary.sqlite',BACKUP/'routing-boundary-restore.sqlite')
        for p in (BACKUP/'after-routing-boundary.sqlite',BACKUP/'routing-boundary-restore.sqlite'):y['verify'](keyword_plan,m,p)
        r['aclAfter']=x['protect']();need(r['aclBefore']['parentAclSha256']==r['aclAfter']['parentAclSha256'],'Existing parent ACL changed')
        r['afterNode']={k:after[k] for k in ('uri','contentSha256','contentBytes','disclosure')}
        r['status']='PASS'
    except BaseException as e:
        r.update(status='FAILED',errorType=type(e).__name__,error=str(e)[:600]);raise
    finally:guard.close();r['completedAt']=x['now']();put(out,r)
    print(json.dumps({'status':r['status'],'changedBodies':1,'unchangedBodies':32,'keywordPairs':'8 positive/256 negative','auditBlockers':r['audit']['blockers']},ensure_ascii=True))
async def probe():
    m=expected();y['verify'](keyword_plan,m)
    inp=HERE/'routing-recheck-requests.json';out=HERE/'routing-recheck-fetch.json'
    need(not out.exists(),'Recheck fetch exists; inspect before retry')
    requests=load(inp);need(len(requests['cases'])==6,'Expected six affected scenarios')
    r={'status':'running','requestSha256':digest(inp),'calls':[],'cases':[],'scope':'actual isolated MCP reads chosen by a fresh blind agent; cached within six-case batch'}
    os.environ.update(x['pins']())
    guard=sqlite3.connect(str(x['TARGET']));guard.execute('SELECT count(*) FROM sqlite_master').fetchone()
    try:
        x['protect']()
        async with y['client'](r,keyword_plan) as call:
            cache={}
            for c in requests['cases']:
                need(set(c)=={'caseKey','readUris'} and len(c['readUris'])<=12 and len(c['readUris'])==len(set(c['readUris'])),'Invalid recheck request')
                reads=[]
                for uri in c['readUris']:
                    need(uri in {n['uri'] for n in m['nodes']},'Unapproved URI')
                    if uri not in cache:cache[uri]=await call('read_memory',{'uri':uri})
                    reads.append({'uri':uri,'text':cache[uri]})
                r['cases'].append({'caseKey':c['caseKey'],'reads':reads})
        y['verify'](keyword_plan,m);x['protect']();r['status']='PASS'
    finally:guard.close();put(out,r)
    print(json.dumps({'status':r['status'],'cases':len(r['cases']),'nativeCalls':len(r['calls'])},ensure_ascii=True))
if __name__=='__main__':
    if sys.argv[1:]==['--self-test']:
        expected()
        for field,value in [('databaseUrl','sqlite+aiosqlite:///wrong.db'),('namespace','other'),('g3Allowed',True),('targetUri','core://other'),('append','unapproved'),('disclosure','unapproved')]:
            bad=dict(a);bad[field]=value
            try:validate(bad)
            except RuntimeError:continue
            raise RuntimeError('Boundary guard accepted: '+field)
        print(json.dumps({'selfTest':'PASS','negativeGuards':6,'filesystemWrites':0}))
    elif sys.argv[1:]==['--patch']:asyncio.run(patch())
    elif sys.argv[1:]==['--probe']:asyncio.run(probe())
    else:raise RuntimeError('Only self-test, fixed patch and fixed read probe are allowed')
