"""Evaluate conservative FTS/vector agreement as an abstention signal.
Uses frozen synthetic positives/negatives, cached vector results, and read-only source DB.
Does not call the embedding API or modify either database.
"""
import json, runpy, sqlite3, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HYBRID=ROOT/'scripts'/'experiments'/'nvidia_embedding_hybrid_eval.py'
SOURCE=Path(r'E:\myPrivateSpace\记忆系统数据库\work\work-memory.db')
NEG=ROOT/'.tmp'/'nvidia_embedding_negative_query_eval.json'
POS_REPORTS=[
 (ROOT/'docs'/'project'/'v3.2-independent-evaluation.json', ROOT/'.tmp'/'nvidia_embedding_real_memory_eval.json'),
 (ROOT/'docs'/'project'/'v3.2-fresh-paraphrase-diagnostic.json', ROOT/'.tmp'/'nvidia_embedding_fresh_holdout_eval.json'),
 (ROOT/'docs'/'project'/'v3.2-second-independent-synthetic-diagnostic.json', ROOT/'.tmp'/'nvidia_embedding_second_independent_eval.json'),
]
OUT=ROOT/'.tmp'/'nvidia_embedding_abstention_eval.json'

def main():
    mod=runpy.run_path(str(HYBRID),run_name='abstention_helpers')
    con=sqlite3.connect(f'file:{SOURCE.as_posix()}?mode=ro',uri=True)
    negatives=json.loads(NEG.read_text(encoding='utf-8'))['negative_results']
    neg_rows=[]
    for x in negatives:
        fts,lane=mod['fts_search'](con,x['query'])
        neg_rows.append({'id':x['id'],'fts_count':len(fts),'fts_lane':lane if fts else 'none','vector_nearest_distance':x['nearest_distance'],'vector_top1':x['nearest_uri'],'vector_returned':bool(x['top5']),'fts_and_vector_agree':bool(fts) and x['nearest_uri'] in fts,'fts_vector_top3_overlap':len(set(fts) & {z['uri'] for z in x['top5'][:3]}),'fts_vector_top5_overlap':len(set(fts) & {z['uri'] for z in x['top5'][:5]})})
    pos_groups=[]
    for bench_path,report_path in POS_REPORTS:
        if not bench_path.exists() or not report_path.exists(): continue
        bench=json.loads(bench_path.read_text(encoding='utf-8'))
        report=json.loads(report_path.read_text(encoding='utf-8'))
        vector_cases={x['id']:x for x in report.get('cases',[])}
        # Different report layouts: fresh/second reports have per-lane sections.
        if not vector_cases and 'vector' in report:
            vector_cases={x['id']:x for x in report['vector'].get('cases',[])}
        if not vector_cases and 'vector_current' in report:
            vector_cases={x['id']:x for x in report['vector_current'].get('cases',[])}
        rows=[]
        for case in bench['cases']:
            fts,lane=mod['fts_search'](con,case['query'])
            vcase=vector_cases.get(case['id'],{})
            top=vcase.get('top10',[])
            if top and isinstance(top[0],dict): vector_uris=[z['uri'] for z in top]
            else: vector_uris=top
            expected=case['expected_uri']
            rows.append({'id':case['id'],'expected_uri':expected,'fts_rank':fts.index(expected)+1 if expected in fts else None,'vector_rank':vector_uris.index(expected)+1 if expected in vector_uris else None,'fts_lane':lane if fts else 'none','fts_hit':expected in fts,'vector_hit':expected in vector_uris,'both_hit':expected in fts and expected in vector_uris})
        pos_groups.append({'benchmark':bench_path.name,'count':len(rows),'fts_recall_at_10':round(sum(r['fts_hit'] for r in rows)/len(rows),4),'vector_recall_at_10':round(sum(r['vector_hit'] for r in rows)/len(rows),4),'agreement_recall_at_10':round(sum(r['both_hit'] for r in rows)/len(rows),4),'cases':rows})
    con.close()
    report={'created_at':time.strftime('%Y-%m-%dT%H:%M:%S'),'status':'diagnostic_only_no_threshold_or_production_policy','positive_groups':pos_groups,'negative_count':len(neg_rows),'negative_fts_nonempty':sum(x['fts_count']>0 for x in neg_rows),'negative_fts_and_vector_top1_agree':sum(x['fts_and_vector_agree'] for x in neg_rows),'negative_fts_vector_top3_overlap':sum(x['fts_vector_top3_overlap']>0 for x in neg_rows),'negative_fts_vector_top5_overlap':sum(x['fts_vector_top5_overlap']>0 for x in neg_rows),'negative_results':neg_rows,'interpretation':'Agreement is a diagnostic signal, not proof of relevance. Synthetic OOD negatives and single-target positives do not justify a production reject threshold.'}
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    for g in pos_groups: print('POSITIVE',g['benchmark'],'FTS',g['fts_recall_at_10'],'VECTOR',g['vector_recall_at_10'],'BOTH',g['agreement_recall_at_10'])
    print('NEGATIVE_FTS_NONEMPTY',report['negative_fts_nonempty'],'/',len(neg_rows))
    print('NEGATIVE_BOTH_AGREE_TOP1',report['negative_fts_and_vector_top1_agree'],'/',len(neg_rows))
    print('NEGATIVE_ANY_OVERLAP_TOP3',report['negative_fts_vector_top3_overlap'],'/',len(neg_rows))
    print('NEGATIVE_ANY_OVERLAP_TOP5',report['negative_fts_vector_top5_overlap'],'/',len(neg_rows))
    print('REPORT',OUT.name)
if __name__=='__main__': main()
