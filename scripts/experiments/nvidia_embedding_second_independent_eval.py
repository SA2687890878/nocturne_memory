"""Run the already-frozen fresh paraphrase diagnostic against current FTS/vector/hybrid retrieval.
No tuning or source database writes. Query text is sent to NVIDIA; document vectors are reused locally.
"""
import asyncio, json, runpy, sqlite3, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'scripts'/'experiments'/'nvidia_embedding_real_memory_eval.py'
HYBRID=ROOT/'scripts'/'experiments'/'nvidia_embedding_hybrid_eval.py'
BENCH=ROOT/'docs'/'project'/'v3.2-second-independent-synthetic-diagnostic.json'
INDEX=ROOT/'.tmp'/'nvidia_embedding_real_memory_eval.db'
OUT=ROOT/'.tmp'/'nvidia_embedding_second_independent_eval.json'

def metric(cases, rankings):
    result={}
    for k in (1,3,5,10): result[f'recall_at_{k}']=round(sum(c['expected_uri'] in rankings[c['id']][:k] for c in cases)/len(cases),4)
    result['mrr']=round(sum((1/(rankings[c['id']].index(c['expected_uri'])+1) if c['expected_uri'] in rankings[c['id']] else 0) for c in cases)/len(cases),4)
    return result

async def main():
    started=time.perf_counter()
    bench=json.loads(BENCH.read_text(encoding='utf-8')); cases=bench['cases']
    base=runpy.run_path(str(BASE),run_name='nvidia_eval_helpers')
    hybrid_mod=runpy.run_path(str(HYBRID),run_name='nvidia_hybrid_helpers')
    queries=[c['query'] for c in cases]
    qvec=await base['embed_batched'](queries,'query')
    con=sqlite3.connect(INDEX)
    con.enable_load_extension(True)
    import sqlite_vec
    sqlite_vec.load(con)
    fts_con=sqlite3.connect(f"file:{Path(r'E:\\myPrivateSpace\\记忆系统数据库\\work\\work-memory.db').as_posix()}?mode=ro",uri=True)
    fts={}; vec={}; lanes={}; rrf={}
    for c,v in zip(cases,qvec):
        vecrows=con.execute("SELECT m.uri FROM memory_vectors x JOIN memory_meta m ON m.rowid=x.rowid WHERE x.embedding MATCH ? AND k=10 ORDER BY x.distance",(sqlite_vec.serialize_float32(v),)).fetchall()
        vec[c['id']]=[x[0] for x in vecrows]
        fts[c['id']],lanes[c['id']]=hybrid_mod['fts_search'](fts_con,c['query'])
        scores={}
        for rank,u in enumerate(fts[c['id']],1): scores[u]=scores.get(u,0)+1/(60+rank)
        for rank,u in enumerate(vec[c['id']],1): scores[u]=scores.get(u,0)+1/(60+rank)
        rrf[c['id']]=[u for u,_ in sorted(scores.items(),key=lambda x:(-x[1],x[0]))[:10]]
    con.close(); fts_con.close()
    report={'evaluated_at':time.strftime('%Y-%m-%dT%H:%M:%S'),'benchmark':'v3.2-second-independent-synthetic-diagnostic.json','status':'frozen_no_tuning_after_evaluation','document_vectors_reused':True,'new_query_embeddings':len(cases),'dimensions':len(qvec[0]),'elapsed_seconds':round(time.perf_counter()-started,2),'fts5':{'metrics':metric(cases,fts),'cases':[]},'vector':{'metrics':metric(cases,vec),'cases':[]},'hybrid_rrf_k60':{'metrics':metric(cases,rrf),'cases':[]}}
    for c in cases:
        for name,ranking in [('fts5',fts),('vector',vec),('hybrid_rrf_k60',rrf)]:
            arr=ranking[c['id']]; rank=arr.index(c['expected_uri'])+1 if c['expected_uri'] in arr else None
            report[name]['cases'].append({'id':c['id'],'rank':rank,'top10':arr})
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('FRESH_HOLDOUT_FTS',json.dumps(report['fts5']['metrics']))
    print('FRESH_HOLDOUT_VECTOR',json.dumps(report['vector']['metrics']))
    print('FRESH_HOLDOUT_HYBRID',json.dumps(report['hybrid_rrf_k60']['metrics']))
    print('ELAPSED',report['elapsed_seconds'],'| OUT',OUT.name)
    for c in cases:
        print('CASE',c['id'],'FTS',next(x['rank'] for x in report['fts5']['cases'] if x['id']==c['id']),'VECTOR',next(x['rank'] for x in report['vector']['cases'] if x['id']==c['id']),'HYBRID',next(x['rank'] for x in report['hybrid_rrf_k60']['cases'] if x['id']==c['id']))

if __name__=='__main__': asyncio.run(main())
