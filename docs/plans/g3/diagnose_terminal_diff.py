import json
from contextlib import closing
from stage_private_database import HERE,TARGET,BACKUP,fingerprint,ro,need
base=BACKUP/'new-database-before-cutover.sqlite'
before=fingerprint(base);now=fingerprint(TARGET)
changed=[t for t in now if now[t]!=before[t]]
result={'status':'OBSERVED','firstFinalCheck':'FAILED: Non-statistical table drift','changedTables':[]}
with closing(ro(base,True)) as a,closing(ro(TARGET)) as b:
 for t in changed:
  q='"'+t.replace('"','""')+'"'
  cols=[r[1] for r in a.execute('PRAGMA table_info('+q+')')]
  old=a.execute('SELECT * FROM '+q+' ORDER BY rowid').fetchall();new=b.execute('SELECT * FROM '+q+' ORDER BY rowid').fetchall()
  fields=sorted({cols[i] for x,y in zip(old,new) for i in range(len(cols)) if x[i]!=y[i]})
  result['changedTables'].append({'table':t,'beforeRows':len(old),'afterRows':len(new),'changedColumns':fields,'columns':cols,'oldRowsPreservedAsPrefix':new[:len(old)]==old})
need(changed,'Failure not reproduced')
(HERE/'terminal-diff-diagnostic.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result))
