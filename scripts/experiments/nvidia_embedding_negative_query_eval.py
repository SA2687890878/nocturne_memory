"""Evaluate vector retrieval abstention using frozen synthetic out-of-domain queries."""
import asyncio, json, sqlite3, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'scripts'/'experiments'/'nvidia_embedding_real_memory_eval.py'
NEG=ROOT/'docs'/'project'/'nvidia-embedding-negative-query-diagnostic.json'
POS_REPORT=ROOT/'.tmp'/'nvidia_embedding_real_memory_eval.json'
INDEX=ROOT/'.tmp'/'nvidia_embedding_real_memory_eval.db'
OUT=ROOT/'.tmp'/'nvidia_embedding_negative_query_eval.json'

def main_metrics(positives, negatives):
    pos=[x['target_distance'] for x in positives if x['target_distance'] is not None]
    neg=[x['nearest_distance'] for x in negatives]
    thresholds=sorted(set([round(x,3) for x in pos+neg]))
    rows=[]
    for threshold in thresholds:
        tp=sum(x<=threshold for x in pos); fp=sum(x<=threshold for x in neg)
        rows.append({'max_l2_distance':threshold,'positive_accept_rate':round(tp/len(pos),4),'negative_false_accept_rate':round(fp/len(neg),4)})
    return {'positive_count':len(pos),'negative_count':len(neg),'positive_target_distance_min':min(pos),'positive_target_distance_max':max(pos),'negative_nearest_distance_min':min(neg),'negative_nearest_distance_max':max(neg),'threshold_sweep':rows}

async def run():
    started=time.perf_counter()
    base=__import__('runpy').run_path(str(BASE),run_name='negative_eval_helpers')
    cases=json.loads(NEG.read_text(encoding='utf-8'))['cases']
    vectors=await base['embed_batched']([x['query'] for x in cases],'query')
    con=sqlite3.connect(INDEX); con.enable_load_extension(True)
    import sqlite_vec
    sqlite_vec.load(con)
    results=[]
    for case,vector in zip(cases,vectors):
        rows=con.execute("""SELECT m.uri,v.distance FROM memory_vectors v JOIN memory_meta m ON m.rowid=v.rowid
          WHERE v.embedding MATCH ? AND k=10 ORDER BY v.distance""",(sqlite_vec.serialize_float32(vector),)).fetchall()
        results.append({'id':case['id'],'query':case['query'],'nearest_uri':rows[0][0],'nearest_distance':float(rows[0][1]),'top5':[{'uri':r[0],'distance':float(r[1])} for r in rows[:5]]})
    con.close()
    pos_report=json.loads(POS_REPORT.read_text(encoding='utf-8'))
    positives=[]
    for case in pos_report['cases']:
        match=next((x for x in case['top10'] if x['uri']==case['expected_uri']),None)
        positives.append({'id':case['id'],'target_distance':match['distance'] if match else None,'target_rank':case['rank']})
    report={'benchmark':'nvidia-embedding-negative-query-diagnostic.json','frozen':True,'model':'nvidia/nemotron-3-embed-1b','dimensions':len(vectors[0]),'distance_metric':'sqlite-vec default L2 distance; lower is closer','positive_reference':'v3.2-independent-evaluation.json target distances','negative_results':results,'positive_reference':positives,'threshold_analysis':main_metrics(positives,results),'elapsed_seconds':round(time.perf_counter()-started,2)}
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('NEGATIVE_COUNT',len(results),'POSITIVE_REFERENCE_COUNT',len(positives))
    print('POSITIVE_DISTANCE_RANGE',report['threshold_analysis']['positive_target_distance_min'],report['threshold_analysis']['positive_target_distance_max'])
    print('NEGATIVE_NEAREST_RANGE',report['threshold_analysis']['negative_nearest_distance_min'],report['threshold_analysis']['negative_nearest_distance_max'])
    for row in results: print('NEG',row['id'],'DIST',round(row['nearest_distance'],4),'URI',row['nearest_uri'])
    for row in report['threshold_analysis']['threshold_sweep']:
        if row['positive_accept_rate']>=0.8 or row['negative_false_accept_rate']<=0.1:
            print('THRESHOLD',row)
    print('REPORT',OUT.name,'ELAPSED',report['elapsed_seconds'])

if __name__=='__main__': asyncio.run(run())
