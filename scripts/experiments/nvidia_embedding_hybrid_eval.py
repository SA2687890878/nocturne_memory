"""Compare current SQLite FTS5, NVIDIA vector search, and RRF hybrid on frozen real-memory benchmark."""
import json, sqlite3, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
SOURCE_DB=Path(r"E:\\myPrivateSpace\\记忆系统数据库\\work\\work-memory.db")
REPORT=ROOT/'.tmp'/'nvidia_embedding_real_memory_eval.json'
BENCH=ROOT/'docs'/'project'/'v3.2-independent-evaluation.json'
sys.path.insert(0,str(ROOT/'backend'))
from db.search import SearchIndexer, _partial_match_coverage, MIN_PARTIAL_MATCH_COVERAGE, MAX_PARTIAL_FALLBACK_RESULTS
from db.search_terms import expand_query_alternatives

def fts_search(con, query, limit=10):
    sql="""SELECT sd.domain,sd.path,sd.node_uuid,sd.uri,sd.priority,sd.memory_id,sd.summary_content,
      CASE WHEN snippet(search_documents_fts,6,'','',' … ',24)!='' THEN snippet(search_documents_fts,6,'','',' … ',24) ELSE substr(sd.content,1,240) END AS snippet,
      sd.disclosure,bm25(search_documents_fts,0.0,0.0,2.5,0.0,2.0,2.5,1.0,1.0,0.75) AS score
      FROM search_documents sd JOIN nodes n ON n.uuid=sd.node_uuid
      JOIN search_documents_fts ON search_documents_fts.namespace=sd.namespace AND search_documents_fts.domain=sd.domain AND search_documents_fts.path=sd.path
      WHERE search_documents_fts MATCH ? AND sd.namespace=? AND n.lifecycle_status!='obsolete'
      ORDER BY score ASC,sd.priority ASC,length(sd.path) ASC LIMIT ?"""
    match=SearchIndexer._to_sqlite_match_query(query)
    rows=con.execute(sql,(match,'',max(limit*5,50))).fetchall() if match else []
    lane='strict'
    if not rows:
        synonym=[]
        for alt in expand_query_alternatives(query):
            alt_match=SearchIndexer._to_sqlite_match_query(alt)
            if alt_match:
                synonym.extend(con.execute(sql,(alt_match,'',max(limit*5,50))).fetchall())
        if synonym:
            rows=synonym; lane='alias'
        else:
            or_match=SearchIndexer._to_sqlite_match_query(query,operator='OR')
            candidates=con.execute(sql,(or_match,'',max(limit*5,50))).fetchall() if or_match else []
            filtered=[]
            for row in candidates:
                d=dict(zip(['domain','path','node_uuid','uri','priority','memory_id','summary_content','snippet','disclosure','score'],row))
                _,coverage=_partial_match_coverage(query,d)
                if coverage>=MIN_PARTIAL_MATCH_COVERAGE: filtered.append(row)
            rows=filtered[:min(limit,MAX_PARTIAL_FALLBACK_RESULTS)]; lane='partial'
    seen=set(); result=[]
    for row in rows:
        node=row[2]
        if node in seen: continue
        seen.add(node); result.append(row[3])
        if len(result)>=limit: break
    return result,lane

def metric(cases,rankings):
    out={}
    for k in (1,3,5,10): out[f'recall_at_{k}']=round(sum(c['expected_uri'] in rankings[c['id']][:k] for c in cases)/len(cases),4)
    out['mrr']=round(sum((1/(rankings[c['id']].index(c['expected_uri'])+1) if c['expected_uri'] in rankings[c['id']] else 0) for c in cases)/len(cases),4)
    return out

def main():
    report=json.loads(REPORT.read_text(encoding='utf-8'))
    cases=json.loads(BENCH.read_text(encoding='utf-8'))['cases']
    con=sqlite3.connect(f'file:{SOURCE_DB.as_posix()}?mode=ro',uri=True)
    fts={}; lanes={}
    for c in cases:
        fts[c['id']],lanes[c['id']]=fts_search(con,c['query'])
    con.close()
    vec={x['id']:[y['uri'] for y in x['top10']] for x in report['cases']}
    hybrid={}
    for c in cases:
        scores={}
        for rank,uri in enumerate(fts[c['id']],1): scores[uri]=scores.get(uri,0)+1/(60+rank)
        for rank,uri in enumerate(vec[c['id']],1): scores[uri]=scores.get(uri,0)+1/(60+rank)
        hybrid[c['id']]=[uri for uri,_ in sorted(scores.items(),key=lambda x:(-x[1],x[0]))[:10]]
    report['fts5_current']={'metrics':metric(cases,fts),'lanes':lanes,'cases':[{'id':c['id'],'rank':(fts[c['id']].index(c['expected_uri'])+1 if c['expected_uri'] in fts[c['id']] else None),'top10':fts[c['id']]} for c in cases]}
    report['vector_current']={'metrics':report['metrics'],'cases':[{'id':x['id'],'rank':x['rank'],'top10':vec[x['id']]} for x in report['cases']]}
    report['hybrid_rrf_k60']={'metrics':metric(cases,hybrid),'cases':[{'id':c['id'],'rank':(hybrid[c['id']].index(c['expected_uri'])+1 if c['expected_uri'] in hybrid[c['id']] else None),'top10':hybrid[c['id']]} for c in cases]}
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('FTS5',json.dumps(report['fts5_current']['metrics'],ensure_ascii=False))
    print('VECTOR',json.dumps(report['vector_current']['metrics'],ensure_ascii=False))
    print('HYBRID_RRF_K60',json.dumps(report['hybrid_rrf_k60']['metrics'],ensure_ascii=False))
    for c in cases:
        print('CASE',c['id'],'FTS',report['fts5_current']['cases'][cases.index(c)]['rank'],'VECTOR',report['vector_current']['cases'][cases.index(c)]['rank'],'HYBRID',report['hybrid_rrf_k60']['cases'][cases.index(c)]['rank'],'LANE',lanes[c['id']])
if __name__=='__main__': main()
