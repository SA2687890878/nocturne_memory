"""Offline-isolated evaluation of NVIDIA embeddings against Nocturne's real read-only memory corpus.

Run from repository root:
  .venv\\Scripts\\python.exe scripts\\experiments\\nvidia_embedding_real_memory_eval.py

The source memory DB is opened read-only. All vectors/results go to .tmp only.
Memory text and benchmark queries are sent to the configured NVIDIA embedding API.
No production search configuration or database is modified.
"""
from __future__ import annotations
import asyncio, json, math, sqlite3, sys, time, hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE_DB = Path(r"E:\\myPrivateSpace\\记忆系统数据库\\work\\work-memory.db")
BENCHMARK = ROOT / "docs" / "project" / "v3.2-independent-evaluation.json"
OUT_DIR = ROOT / ".tmp"
OUT_DB = OUT_DIR / "nvidia_embedding_real_memory_eval.db"
CACHE_DB = OUT_DIR / "nvidia_embedding_embedding_cache.db"
OUT_JSON = OUT_DIR / "nvidia_embedding_real_memory_eval.json"
sys.path.insert(0, str(ROOT / "backend"))
import sqlite_vec
from embedding import embed_texts

BATCH_SIZE = 12
TOP_K = 10

def load_source():
    uri = f"file:{SOURCE_DB.as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute("""
        SELECT sd.memory_id, sd.uri, sd.namespace, sd.domain, sd.path,
               sd.summary_content, sd.search_terms, sd.content,
               n.lifecycle_status, m.deprecated
        FROM search_documents sd
        JOIN memories m ON m.id = sd.memory_id
        JOIN nodes n ON n.uuid = sd.node_uuid
        WHERE COALESCE(n.lifecycle_status, 'unspecified') <> 'obsolete'
          AND COALESCE(m.deprecated, 0) = 0
        ORDER BY sd.uri
    """).fetchall()
    con.close()
    docs = []
    for row in rows:
        # Preserve URI/path as retrieval cues; include summary, terms and full body.
        parts = [
            f"URI: {row['uri']}", f"Path: {row['path']}",
            f"Domain: {row['domain']}", f"Namespace: {row['namespace']}",
            f"Summary: {row['summary_content'] or ''}",
            f"Keywords: {row['search_terms'] or ''}",
            f"Memory: {row['content'] or ''}",
        ]
        docs.append({"memory_id": row["memory_id"], "uri": row["uri"],
                     "text": "\n".join(parts)})
    return docs

async def embed_batched(texts, input_type):
    # Persistent local cache avoids repeat API calls/cost for unchanged text.
    CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
    cache = sqlite3.connect(CACHE_DB)
    cache.execute("CREATE TABLE IF NOT EXISTS embeddings (cache_key TEXT PRIMARY KEY, input_type TEXT NOT NULL, text_hash TEXT NOT NULL, vector_json TEXT NOT NULL, dimensions INTEGER NOT NULL)")
    keys = [hashlib.sha256((input_type + "\0" + text).encode("utf-8")).hexdigest() for text in texts]
    found = {}
    for key in set(keys):
        row = cache.execute("SELECT vector_json FROM embeddings WHERE cache_key=?", (key,)).fetchone()
        if row:
            found[key] = json.loads(row[0])
    missing_indices = [i for i,key in enumerate(keys) if key not in found]
    for start in range(0, len(missing_indices), BATCH_SIZE):
        indices = missing_indices[start:start+BATCH_SIZE]
        batch = [texts[i] for i in indices]
        batch_vectors = await embed_texts(batch, input_type=input_type)
        for i, vector in zip(indices, batch_vectors):
            key = keys[i]
            found[key] = vector
            cache.execute("INSERT OR REPLACE INTO embeddings(cache_key,input_type,text_hash,vector_json,dimensions) VALUES(?,?,?,?,?)", (key,input_type,hashlib.sha256(texts[i].encode('utf-8')).hexdigest(),json.dumps(vector,separators=(',',':')),len(vector)))
        cache.commit()
        print(f"EMBED_PROGRESS {input_type} {start+len(indices)}/{len(missing_indices)} NEW; CACHE_HITS {len(texts)-len(missing_indices)}", flush=True)
    cache.close()
    return [found[key] for key in keys]

def create_index(docs, vectors):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if OUT_DB.exists(): OUT_DB.unlink()
    con = sqlite3.connect(OUT_DB)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE memory_meta (rowid INTEGER PRIMARY KEY, memory_id INTEGER NOT NULL, uri TEXT NOT NULL UNIQUE)")
    con.enable_load_extension(True)
    sqlite_vec.load(con)
    dim = len(vectors[0])
    con.execute(f"CREATE VIRTUAL TABLE memory_vectors USING vec0(embedding float[{dim}])")
    for i, (doc, vector) in enumerate(zip(docs, vectors), 1):
        con.execute("INSERT INTO memory_meta(rowid,memory_id,uri) VALUES(?,?,?)", (i,doc['memory_id'],doc['uri']))
        con.execute("INSERT INTO memory_vectors(rowid,embedding) VALUES(?,?)", (i,sqlite_vec.serialize_float32(vector)))
    con.commit()
    return con, dim

def rank_query(con, vector):
    rows = con.execute("""
        SELECT m.uri, v.distance
        FROM memory_vectors v JOIN memory_meta m ON m.rowid=v.rowid
        WHERE v.embedding MATCH ? AND k=? ORDER BY v.distance
    """, (sqlite_vec.serialize_float32(vector), TOP_K)).fetchall()
    return [{"uri": r[0], "distance": float(r[1])} for r in rows]

def metrics(cases, rankings):
    out = {}
    for k in (1,3,5,10):
        hits = sum(any(x['uri']==c['expected_uri'] for x in rankings[c['id']][:k]) for c in cases)
        out[f"recall_at_{k}"] = round(hits/len(cases),4)
    rr=[]
    for c in cases:
        rank = next((i for i,x in enumerate(rankings[c['id']],1) if x['uri']==c['expected_uri']),None)
        rr.append(1/rank if rank else 0)
    out['mrr'] = round(sum(rr)/len(rr),4)
    return out

async def main():
    started=time.perf_counter()
    if not SOURCE_DB.exists(): raise FileNotFoundError(f"Source DB not found: {SOURCE_DB}")
    benchmark=json.loads(BENCHMARK.read_text(encoding='utf-8'))
    cases=benchmark['cases']
    docs=load_source()
    if not docs: raise RuntimeError('No eligible memory documents found')
    expected={c['expected_uri'] for c in cases}
    missing=expected-{d['uri'] for d in docs}
    if missing: raise RuntimeError(f"Benchmark targets absent from eligible corpus: {len(missing)}")
    print(f"SOURCE_DOCS {len(docs)} | TEXT_CHARS {sum(len(d['text']) for d in docs)} | QUERIES {len(cases)}",flush=True)
    doc_vectors=await embed_batched([d['text'] for d in docs], 'passage')
    query_vectors=await embed_batched([c['query'] for c in cases], 'query')
    con,dim=create_index(docs,doc_vectors)
    rankings={c['id']:rank_query(con,v) for c,v in zip(cases,query_vectors)}
    report={
      'evaluated_at':time.strftime('%Y-%m-%dT%H:%M:%S'),
      'provider':'NVIDIA', 'model':'nvidia/nemotron-3-embed-1b', 'dimensions':dim,
      'source':'work-memory.db opened read-only', 'eligible_document_count':len(docs),
      'source_text_characters':sum(len(d['text']) for d in docs),
      'benchmark':'v3.2-independent-evaluation.json (frozen; not tuned on this run)',
      'top_k':TOP_K, 'metrics':metrics(cases,rankings),
      'historical_fts_snapshot':{'recall_at_10':0.5,'mrr':0.3833,'note':'Historical pre-alias diagnostic only; do not compare with current implementation.'},
      'cases':[]
    }
    for c in cases:
        ranked=rankings[c['id']]
        rank=next((i for i,x in enumerate(ranked,1) if x['uri']==c['expected_uri']),None)
        report['cases'].append({'id':c['id'],'expected_uri':c['expected_uri'],'rank':rank,'top10':ranked})
    report['elapsed_seconds']=round(time.perf_counter()-started,2)
    OUT_JSON.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    con.close()
    print('RESULT_METRICS',json.dumps(report['metrics'],ensure_ascii=False),flush=True)
    print('DIMENSIONS',dim,'| DB',OUT_DB.name,'| REPORT',OUT_JSON.name,'| ELAPSED',report['elapsed_seconds'],flush=True)
    for item in report['cases']:
        print('CASE',item['id'],'RANK',item['rank'],'TARGET',item['expected_uri'],flush=True)

if __name__=='__main__': asyncio.run(main())
