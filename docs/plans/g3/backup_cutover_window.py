import json, shutil, sqlite3, sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from stage_private_database import HERE,ROOT,DATA,TARGET,URL,BACKUP,sha,ro,need,read_json,backup,fingerprint
OUT=HERE/'window-backup-receipt.json'
need(sys.argv[1:]==['--run'],'Only --run is allowed')
need(not OUT.exists(),'Window backup receipt exists; inspect before retry')
freeze=read_json(HERE/'freeze-observation.json')
need(freeze['connectorEnabled'] is False and freeze['relatedProcessCount']==0,'Observed old writer not frozen')
need(read_json(HERE/'stage-receipt.json')['status']=='PASS','Private stage must pass first')
cfg=read_json(ROOT/'config.json');old=DATA/'工作记忆.db'
need(cfg['database_url']=='sqlite+aiosqlite:///'+old.as_posix(),'Old config target differs')
need(old.is_file() and TARGET.is_file(),'Current database missing')
old_hash=sha(old); dest=BACKUP/'old-database-before.sqlite'
need(not dest.exists(),'Old backup destination occupied')
with closing(ro(old)) as src, closing(sqlite3.connect(str(dest))) as dst: src.backup(dst)
with closing(ro(dest,True)) as c:
    need(c.execute('PRAGMA integrity_check').fetchone()[0]=='ok','Old backup integrity failure')
    counts={t:c.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ('nodes','memories','paths')}
need(sha(old)==old_hash,'Old main database bytes changed during backup')
restore=BACKUP/'old-database-restore-validation.sqlite'
shutil.copyfile(dest,restore)
need(sha(dest)==sha(restore),'Old restore copy differs')
with closing(ro(restore,True)) as c: need(c.execute('PRAGMA integrity_check').fetchone()[0]=='ok','Old restore integrity failure')
old_url=cfg['database_url']
import hashlib
old_key=hashlib.sha1(old_url.encode()).hexdigest()[:12]
old_snapshot=ROOT/'snapshots'/old_key/'changeset.json'
snap={'defaultPool':old_snapshot.as_posix(),'exists':old_snapshot.is_file(),'processOverrideBeforeFreeze':'not directly observed; connector had no explicit SNAPSHOT_DIR'}
if old_snapshot.is_file():
    snapshot_dest=BACKUP/'old-changeset-before.json';need(not snapshot_dest.exists(),'Old snapshot backup occupied')
    shutil.copyfile(old_snapshot,snapshot_dest);need(sha(old_snapshot)==sha(snapshot_dest),'Old snapshot backup mismatch')
    snap.update(backup=snapshot_dest.as_posix(),sha256=sha(snapshot_dest))
new_before=fingerprint(TARGET)
need(backup(TARGET,BACKUP/'new-database-before-cutover.sqlite')==new_before,'New baseline backup differs')
new_snap=DATA/'work/snapshots/ce02f04cd63c/changeset.json';new_dest=BACKUP/'new-changeset-before-cutover.json'
need(not new_dest.exists(),'New changeset backup occupied');shutil.copyfile(new_snap,new_dest)
need(sha(new_snap)==sha(new_dest),'New changeset baseline differs')
r={'status':'PASS','at':datetime.now(timezone.utc).isoformat(),'oldDatabase':{'source':old.as_posix(),'mainSha256Before':old_hash,'mainSha256After':sha(old),'backup':dest.as_posix(),'backupSha256':sha(dest),'integrity':'ok','restoreCopy':restore.as_posix(),'restoreCopySha256':sha(restore),'metadataCounts':counts,'projectContentReadForMigration':False},'oldSnapshots':snap,'newBaseline':{'path':(BACKUP/'new-database-before-cutover.sqlite').as_posix(),'fingerprint':new_before,'snapshotSha256':sha(new_dest)},'g1OldDatabaseBusinessBaseline':'not captured in G1; no fabricated historical delta','oldWriteFreezeScope':freeze['scope'],'sourceConfigSha256':sha(ROOT/'config.json')}
OUT.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':'PASS','oldBackupIntegrity':'ok','oldMainBytesUnchanged':True,'restoreCopyMatches':True,'oldDefaultSnapshotExists':old_snapshot.is_file(),'newBaseline':'PASS'}))
