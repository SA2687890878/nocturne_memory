import json, sys
from pathlib import Path
from stage_private_database import HERE,ROOT,URL,need,sha,read_json
HOME=Path('C:/Users/admin/.dsh')
BEFORE=ROOT/'backups/g3-20261023-v1'
def check():
    sem=(ROOT/'docs/plans/g1/semantic-diff.md').read_text(encoding='utf-8')
    old_cs=(BEFORE/'csharp.md.before').read_text(encoding='utf-8-sig')
    cs=(HOME/'knowledge/rules/languages/csharp.md').read_text(encoding='utf-8-sig')
    old='- async/await 全链路一致，禁止 `.Result`/`.Wait()`'
    new='- async/await全链路一致；禁止用Task<T>.Result或Task.Wait()同步等待；普通业务对象的Result属性不在本条范围内。'
    need(old_cs.count(old)==1 and new in sem and cs==old_cs.replace(old,new),'C# precise patch differs')
    old_sql=(BEFORE/'sqlserver.md.before').read_text(encoding='utf-8-sig')
    sql=(HOME/'knowledge/rules/languages/sqlserver.md').read_text(encoding='utf-8-sig')
    section=sem.split('#### 5.1.2 SQL追加拟文（未生效）',1)[1].split('```markdown\n',1)[1].split('\n```',1)[0]
    anchor='- 默认不在建表脚本插入菜单数据、不自动授权角色'
    need(sql==old_sql.replace(anchor,anchor+'\n\n'+section),'SQL append differs')
    old_resident=(BEFORE/'AGENTS.md.before').read_text(encoding='utf-8-sig')
    prod=old_resident.split('## 生产库操作红线',1)[1].split('## 验证纪律',1)[0].strip()
    resident=(HOME/'AGENTS.md').read_text(encoding='utf-8-sig')
    need(prod in resident,'Original production safety removed before handoff')
    need(resident==(HERE/'resident-candidate.md').read_text(encoding='utf-8'),'Resident draft mismatch')
    need('实现或审查.NET工件前加载 ~/.dsh/knowledge/rules/languages/csharp.md。' in resident,'C# preload absent')
    cfg=read_json(ROOT/'config.json');before=read_json(BEFORE/'config.json.before')
    expected=dict(before,database_url=URL);need(cfg==expected,'Formal config changed beyond database_url')
    sys.path.insert(0,str(ROOT/'backend'))
    import config
    need(config.get('database_url')==URL,'Same-source config parser mismatch')
    from db import get_effective_database_url
    need(get_effective_database_url()==URL,'Default application target mismatch')
    from scripts import audit_memory
    need(audit_memory.db_path()==URL.split('///',1)[1],'Existing audit CLI still points to old DB')
    r={'status':'PASS','csharpExactReplacement':True,'sqlExactAppend':True,'oldProductionSafetyPreserved':True,'sqlServerHandoffExercise':'NOT_PERFORMED','residentUtf8Bytes':len(resident.encode()),'residentBeforeBytes':(BEFORE/'AGENTS.md.before').stat().st_size,'sameSourceConfigParser':True,'existingAuditDefaultTarget':audit_memory.db_path(),'onlyConfigDatabaseUrlChanged':True,'sourceHashes':{p.as_posix():sha(p) for p in (HOME/'AGENTS.md',HOME/'knowledge/rules/languages/csharp.md',HOME/'knowledge/rules/languages/sqlserver.md',ROOT/'config.json')}}
    return r
if __name__=='__main__':
    need(sys.argv[1:]==['--run'],'Only --run allowed')
    out=HERE/'formal-rules-verification.json';need(not out.exists(),'Verification receipt exists')
    r=check();out.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in r.items() if k!='sourceHashes'},ensure_ascii=True))
