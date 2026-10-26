import hashlib, json, os, shutil, sqlite3, sys
from contextlib import closing
from datetime import datetime, timezone
from stage_private_database import HERE,ROOT,DATA,TARGET,URL,SNAP,POOL,BACKUP,sha,ro,need,read_json,backup,fingerprint,business_bodies,acl,pins
OLD=DATA/'工作记忆.db'
ROLLBACK=BACKUP/'old-database-restore-validation.sqlite'
ROLLBACK_URL='sqlite+aiosqlite:///'+ROLLBACK.as_posix()
def comparable_nodes(path):
    with closing(ro(path)) as c:
        cols=[r[1] for r in c.execute('PRAGMA table_info(nodes)') if r[1] not in {'access_count','last_accessed_at'}]
        names=','.join('"'+x.replace('"','""')+'"' for x in cols)
        rows=sorted(json.dumps(row,ensure_ascii=False) for row in c.execute('SELECT '+names+' FROM nodes'))
        return hashlib.sha256(('\n'.join(rows)).encode()).hexdigest()
def validate_access_append(old, new, valid_nodes):
    need(len(new)>=len(old) and new[:len(old)]==old,'Existing access logs changed')
    last=old[-1][0] if old else 0
    for row in new[len(old):]:
        need(row[0]>last and row[1] in valid_nodes and row[2]=='' and isinstance(row[3],str) and bool(row[3]),'Unexpected appended access log')
        last=row[0]
    return len(new)-len(old)
def access_log_delta():
    with closing(ro(BACKUP/'new-database-before-cutover.sqlite',True)) as a, closing(ro(TARGET)) as b:
        cols=[r[1] for r in b.execute('PRAGMA table_info(memory_access_logs)')]
        need(cols==['id','node_uuid','namespace','accessed_at','context'],'Access log schema differs')
        old=a.execute('SELECT * FROM memory_access_logs ORDER BY id').fetchall()
        new=b.execute('SELECT * FROM memory_access_logs ORDER BY id').fetchall()
        valid={r[0] for r in b.execute("SELECT node_uuid FROM paths WHERE namespace=''")}
        return validate_access_append(old,new,valid)
def self_test():
    old=[(1,'a','','before',None)];good=old+[(2,'a','','now',None)]
    need(validate_access_append(old,good,{'a'})==1,'Valid append rejected')
    for bad in [[],[(1,'changed','','before',None)],old+[(1,'a','','now',None)],old+[(2,'other','','now',None)],old+[(2,'a','other','now',None)]]:
        try:validate_access_append(old,bad,{'a'})
        except RuntimeError:continue
        raise RuntimeError('Access-log negative guard accepted')
    print(json.dumps({'selfTest':'PASS','negativeAccessGuards':5,'positiveAccessAppend':1}))
def old_unchanged():
    window=read_json(HERE/'window-backup-receipt.json')
    need(sha(OLD)==window['oldDatabase']['mainSha256After'],'Protected old main changed')
    return True
def prepare():
    out=HERE/'rollback-prepare.json';need(not out.exists(),'Rollback preparation exists')
    need(old_unchanged(),'Old database drift')
    current=fingerprint(TARGET);dest=BACKUP/'new-before-rollback.sqlite'
    need(backup(TARGET,dest)==current,'Current new backup differs')
    need(sha(ROLLBACK)==read_json(HERE/'window-backup-receipt.json')['oldDatabase']['restoreCopySha256'],'Old restore copy changed before rehearsal')
    key=hashlib.sha1(ROLLBACK_URL.encode()).hexdigest()[:12]
    pool=SNAP/key;pool.mkdir(exist_ok=False)
    old_snap=BACKUP/'old-changeset-before.json'
    need(old_snap.is_file(),'Old changeset baseline missing')
    shutil.copyfile(old_snap,pool/'changeset.json')
    need(sha(old_snap)==sha(pool/'changeset.json'),'Rollback snapshot copy differs')
    config=read_json(HERE/'nocturne-connector-after.safe.json')
    config['connections'][0]['env']['NOCTURNE_DB_URL']=ROLLBACK_URL
    (HERE/'nocturne-connector-rollback.safe.json').write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    r={'status':'PASS','at':datetime.now(timezone.utc).isoformat(),'scope':'same daily connector temporarily points to old restore copy, never original old DB','restoreUrl':ROLLBACK_URL,'snapshotPoolKey':key,'newBeforeRollbackFingerprint':current,'newBackup':dest.as_posix(),'oldMainUnchanged':True}
    out.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'status':'PASS','oldMainUnchanged':True,'rollbackScope':'old restore copy only'}))
def final():
    out=HERE/'terminal-state.json';need(not out.exists(),'Terminal receipt exists')
    os.environ.update(pins());sys.path.insert(0,str(ROOT/'backend'))
    from db import get_effective_database_url,get_changeset_store
    from scripts import audit_memory
    need(get_effective_database_url()==URL and audit_memory.db_path()==TARGET.as_posix(),'Final audit/app target differs')
    report=audit_memory.audit();need(audit_memory.issue_count(report)==0,'Final audit blocked')
    fp=fingerprint(TARGET);before=read_json(HERE/'window-backup-receipt.json')['newBaseline']['fingerprint']
    need(fp.keys()==before.keys(),'Terminal table set differs')
    changed=[k for k in fp if fp[k]!=before[k]]
    need(set(changed)<= {'nodes','memory_access_logs'},'Non-statistical table drift')
    access_delta=access_log_delta()
    need(comparable_nodes(TARGET)==comparable_nodes(BACKUP/'new-database-before-cutover.sqlite'),'Node non-access fields drift')
    bodies=business_bodies(TARGET);need(len(bodies)==33 and bodies==business_bodies(DATA/'work-memory.db'),'Terminal business bodies differ')
    store=get_changeset_store();need(str(store.snapshot_dir).replace('\\','/')==(SNAP/POOL).as_posix(),'Terminal snapshot pool mismatch')
    before_snapshot=sha(SNAP/POOL/'changeset.json');loaded=store._load()
    need(len(loaded['rows'])==141 and sha(SNAP/POOL/'changeset.json')==before_snapshot,'Native changeset loading drift')
    restore=BACKUP/'new-final-restore.sqlite';need(backup(TARGET,restore)==fp and fingerprint(restore,True)==fp,'Final backup restore mismatch')
    r={'status':'PASS','at':datetime.now(timezone.utc).isoformat(),'databaseUrl':URL,'snapshotPoolKey':POOL,'terminalFingerprint':fp,'changedTablesSinceCutoverBaseline':changed,'onlyAccessMetadataChanged':True,'accessLogAppendCount':access_delta,'oldAccessLogRowsUnchanged':True,'businessBodiesEqual':33,'nativeChangesetLoadRows':141,'nativeChangesetSha256':before_snapshot,'oldMainUnchangedSinceFreeze':old_unchanged(),'audit':{'blockers':0,'untriggeredLeafAdvisories':len(report['untriggered_leaves']),'target':report['db']},'acl':acl(),'restoreCopy':restore.as_posix(),'restoreCopyLogicalEquality':True,'oldDatabaseOpenedByStageMeaning':'stage SOURCE is G2 trial work-memory.db, not protected daily 工作记忆.db; old daily DB was read only for authorized window backup','scope':'terminal SQLite consistency and same-source configuration; actual daily reads in separate receipts'}
    out.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'status':'PASS','changedTables':changed,'businessNodes':33,'auditBlockers':0,'oldMainUnchanged':True,'nativeChangesetRows':141,'finalRestoreMatches':True}))
if __name__=='__main__':
    if sys.argv[1:]==['--self-test']:self_test()
    elif sys.argv[1:]==['--prepare-rollback']:prepare()
    elif sys.argv[1:]==['--final']:final()
    else:raise RuntimeError('Use --prepare-rollback or --final only')
