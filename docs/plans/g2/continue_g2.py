from __future__ import annotations
import argparse, asyncio, hashlib, json, os, re, runpy, sqlite3, sys
from contextlib import asynccontextmanager, closing
from datetime import timedelta
from pathlib import Path
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
x = runpy.run_path(str(HERE / 'run_trial.py'))
PLAN = HERE / 'keyword-continuation.json'
RECEIPT = HERE / 'keyword-receipt.json'
BATCH = 'g2-keywords-20261023-v1'
need, load, put, digest = (x[k] for k in ('need', 'load', 'put', 'digest'))

def validate(plan, m):
    need(plan['batchId'] == BATCH and plan['g3Allowed'] is False, 'G2-only batch required')
    need(plan['databaseUrl'] == x['pinned_url']() and plan['namespace'] == '', 'Pinned target mismatch')
    need(plan['baseInputSha256'] == digest(x['INPUT']), 'Base import input changed')
    need(plan['controllerSha256'] == digest(HERE / 'run_trial.py'), 'Controller changed')
    need(plan['scriptSha256'] == digest(__file__), 'Continuation script changed')
    need(plan['authorization']['userRequest'] == '/ponytail 按计划继续推动记忆系统', 'Continuation authorization missing')
    nodes = {n['uri']: n for n in m['nodes']}
    pairs = set()
    for b in plan['bindings']:
        word, source, target = b['keyword'], b['sourceUri'], b['targetUri']
        need(word.strip() == word and len(word) >= 4, 'Specific nonempty keyword required')
        need(source in nodes and target in nodes and source != target, 'Real cross-node path required')
        hits = [uri for uri, n in nodes.items() if word in n['content']]
        need(hits == [source] and len(hits) / len(nodes) < .05, 'Existing literal hit/frequency policy failed')
        need((word, target) not in pairs, 'Duplicate binding')
        pairs.add((word, target))
    need(len(pairs) == 8 and len({w for w, _ in pairs}) == 8, 'Unexpected binding set')
    return nodes

def rows(path=None):
    with closing(x['ro'](path or x['TARGET'])) as con:
        return sorted(con.execute("SELECT g.keyword,p.domain||'://'||p.path FROM glossary_keywords g JOIN paths p ON p.node_uuid=g.node_uuid AND p.namespace=g.namespace ORDER BY 1,2").fetchall())

def verify(plan, m, path=None):
    x['verify_nodes'](m, path or x['TARGET'])
    need(rows(path) == sorted((b['keyword'], b['targetUri']) for b in plan['bindings']), 'Glossary rows mismatch')
    with closing(x['ro'](path or x['TARGET'])) as con:
        need(con.execute('SELECT count(*) FROM glossary_keywords').fetchone()[0] == 8, 'Extra namespace/binding')
        presets = con.execute('SELECT name,is_active,boot_uris FROM presets').fetchall()
        need(len(presets) == 1 and presets[0][0:2] == ('work', 1) and json.loads(presets[0][2]) == {'': m['bootUris']}, 'Boot preset changed')

def links(text):
    if 'GLOSSARY (keywords detected in this content)' not in text:
        return set()
    section = text.split('GLOSSARY (keywords detected in this content)', 1)[1].split('CHILD MEMORIES', 1)[0]
    return set(re.findall(r'-> (core://[A-Za-z0-9_/-]+)', section))

@asynccontextmanager
async def client(receipt, plan, readonly=True):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    params = StdioServerParameters(command=sys.executable, args=[str(HERE / 'run_trial.py'), '--server'], cwd=str(x['BACKEND']), env=x['pins']())
    async def call(session, name, args):
        if name == 'manage_triggers':
            need(not readonly and set(args) == {'uri', 'add'} and len(args['add']) == 1, 'Only approved additions allowed')
            need((args['add'][0], args['uri']) in {(b['keyword'], b['targetUri']) for b in plan['bindings']}, 'Unapproved keyword write')
        elif name == 'read_memory':
            need(set(args) == {'uri'} and args['uri'] in {n['uri'] for n in load(x['INPUT'])['nodes']} | {'system://boot', 'system://glossary'}, 'Read outside approved nodes')
        elif name == 'search_memory':
            need(set(args) == {'query', 'domain', 'limit'} and args['domain'] == 'core' and 1 <= args['limit'] <= 20 and 0 < len(args['query']) <= 64, 'Invalid bounded search')
        else:
            raise RuntimeError('Tool outside continuation allowlist')
        result = await session.call_tool(name, args, read_timeout_seconds=timedelta(seconds=60))
        text = '\n'.join(getattr(c, 'text', '') for c in result.content)
        need(not getattr(result, 'isError', False) and not text.lstrip().startswith('Error:'), 'MCP call failed: ' + name + ' ' + text[:200])
        receipt.setdefault('calls', []).append({'tool': name, 'arguments': args, 'resultSha256': hashlib.sha256(text.encode()).hexdigest(), 'utf8Bytes': len(text.encode())})
        return text
    with (x['BACKUPS'] / BATCH / 'mcp-stderr.log').open('a', encoding='utf-8') as log:
        async with stdio_client(params, errlog=log) as (rd, wr):
            async with ClientSession(rd, wr) as session:
                await session.initialize()
                names = {t.name for t in (await session.list_tools()).tools}
                need({'read_memory', 'search_memory', 'manage_triggers'} <= names, 'Native tools missing')
                yield lambda name, args: call(session, name, args)

async def matrix(plan, nodes, call, receipt):
    positive = negative = 0
    views = {}
    for uri, n in nodes.items():
        text = await call('read_memory', {'uri': uri})
        need(n['content'] in text, 'Body changed: ' + uri)
        expected = {b['targetUri'] for b in plan['bindings'] if b['keyword'] in n['content'] and b['targetUri'] != uri}
        need(links(text) == expected, 'Native links mismatch: ' + uri)
        for b in plan['bindings']:
            if b['targetUri'] in expected and b['keyword'] in n['content']:
                positive += 1
            else:
                negative += 1
        for b in plan['bindings']:
            if b['targetUri'] == uri:
                header = next(line for line in text.splitlines() if line.startswith('Keywords:'))
                need(b['keyword'] in header, 'Target Keywords missing: ' + uri)
        views[uri] = {'sha256': hashlib.sha256(text.encode()).hexdigest(), 'glossaryUris': sorted(expected), 'utf8Bytes': len(text.encode())}
    need(positive == 8 and negative == 256, 'Incomplete keyword matrix')
    receipt['nativeReadMatrix'] = {'status': 'PASS', 'sourceNodes': 33, 'positivePairs': positive, 'negativePairs': negative, 'views': views}
    for b in plan['bindings']:
        found = await call('search_memory', {'query': b['keyword'], 'domain': 'core', 'limit': 10})
        need(b['targetUri'] in found, 'Keyword-index target missing: ' + b['keyword'])
    receipt['keywordSearch'] = {'status': 'PASS', 'targetHits': 8}
    boot = await call('read_memory', {'uri': 'system://boot'})
    need('# Loaded: 2/2' in boot and 'Failed to load' not in boot and len(boot.encode()) <= 8192, 'Boot failed/bloated')
    receipt['boot'] = {'status': 'PASS', 'loaded': '2/2', 'utf8Bytes': len(boot.encode())}
    glossary = await call('read_memory', {'uri': 'system://glossary'})
    need(all(b['keyword'] in glossary and b['targetUri'] in glossary for b in plan['bindings']), 'Glossary index incomplete')

async def execute(plan, m, nodes):
    need(not RECEIPT.exists(), 'Receipt already exists; inspect before retry')
    need(rows() == [], 'Expected original empty glossary; no automatic overwrite')
    x['verify_nodes'](m)
    before_config = digest(x['ROOT'] / 'config.json')
    backup = x['BACKUPS'] / BATCH
    need(not backup.exists(), 'Backup batch occupied; inspect before retry')
    backup.mkdir()
    r = {'batchId': BATCH, 'startedAt': x['now'](), 'status': 'running', 'g2OverallStatus': 'not_accepted', 'databaseUrl': x['pinned_url'](), 'namespace': '', 'g3Performed': False, 'oldDatabaseOpened': False, 'planSha256': digest(PLAN), 'scriptSha256': digest(__file__), 'calls': [], 'uncovered': ['Daily-connection/G3 cutover', 'Long-term WAL recreation ACL', 'Natural-language routing evaluation is separate']}
    guard = sqlite3.connect(str(x['TARGET']))
    guard.execute('SELECT count(*) FROM sqlite_master').fetchone()
    os.environ.update(x['pins']())
    try:
        r['aclBefore'] = x['protect']()
        r['beforeBackup'] = x['backup_db'](x['TARGET'], backup / 'before-keywords.sqlite')
        snap = x['SNAP'] / hashlib.sha1(x['pinned_url']().encode()).hexdigest()[:12] / 'changeset.json'
        need(snap.is_file(), 'Owned new-database snapshot missing')
        dest = backup / 'before-changeset.json'
        need(not dest.exists(), 'Snapshot backup occupied')
        dest.write_bytes(snap.read_bytes())
        r['snapshotBeforeSha256'] = digest(dest)
        put(RECEIPT, r)
        async with client(r, plan, readonly=False) as call:
            for uri in sorted({b['sourceUri'] for b in plan['bindings']} | {b['targetUri'] for b in plan['bindings']}):
                text = await call('read_memory', {'uri': uri})
                need(not links(text) and 'Keywords: (none)' in text, 'Unexpected prior keyword state')
            r['redBeforeBinding'] = {'status': 'EXPECTED_RED', 'missingCrossLinks': 8, 'scope': 'Real native reads before additions; no source rollback/deletion'}
            for b in plan['bindings']:
                text = await call('manage_triggers', {'uri': b['targetUri'], 'add': [b['keyword']]})
                need('Added: ' + b['keyword'] in text, 'Native add was not confirmed')
                r.setdefault('added', []).append(b)
                put(RECEIPT, r)
            verify(plan, m)
            await matrix(plan, nodes, call, r)
            for b in plan['bindings']:
                text = await call('manage_triggers', {'uri': b['targetUri'], 'add': [b['keyword']]})
                need('Already existed (skipped): ' + b['keyword'] in text, 'Duplicate add did not skip')
            verify(plan, m)
            r['idempotentAdd'] = {'status': 'PASS', 'repeatedCalls': 8, 'finalBindings': 8, 'newBusinessNodes': 0}
        async with client(r, plan) as call:
            text = await call('read_memory', {'uri': 'core://agent/delivery/testing'})
            need('core://agent/verification/test-design' in links(text), 'Restart lost cross-link')
        r['restart'] = {'status': 'PASS', 'scope': 'Fresh isolated stdio process; daily connector unchanged'}
        r['audit'] = x['audit_new'](m)
        r['checkpoint'] = list(guard.execute('PRAGMA wal_checkpoint(FULL)').fetchone())
        need(r['checkpoint'][0] == 0, 'Checkpoint busy')
        r['afterBackup'] = x['backup_db'](x['TARGET'], backup / 'after-keywords.sqlite')
        r['restoreCopy'] = x['backup_db'](backup / 'after-keywords.sqlite', backup / 'restore-validation.sqlite')
        for p in [x['TARGET'], backup / 'after-keywords.sqlite', backup / 'restore-validation.sqlite']:
            verify(plan, m, p)
        r['snapshotAfterSha256'] = digest(snap)
        r['aclAfter'] = x['protect']()
        need(digest(x['ROOT'] / 'config.json') == before_config, 'Daily runtime config changed')
        need(r['aclBefore']['parentAclSha256'] == r['aclAfter']['parentAclSha256'], 'Existing parent ACL changed')
        r['status'] = 'PASS'
    except BaseException as e:
        r['status'] = 'FAILED'
        r['errorType'] = type(e).__name__
        r['error'] = str(e)[:600]
        raise
    finally:
        guard.close()
        r['completedAt'] = x['now']()
        put(RECEIPT, r)
    print(json.dumps({'status': r['status'], 'bindings': len(rows()), 'nativeMatrix': {'positive': 8, 'negative': 256}, 'auditBlockers': r['audit']['blockers'], 'g2OverallStatus': r['g2OverallStatus']}, ensure_ascii=True))

async def probe(plan, m, nodes, request_path):
    p = Path(request_path).resolve()
    need(p in {HERE / 'routing-requests-a.json', HERE / 'routing-requests-b.json'}, 'Only assigned evaluation requests accepted')
    requests = load(p)
    out = p.with_name(p.name.replace('requests', 'fetch'))
    need(not out.exists(), 'Fetch evidence already exists; inspect instead of overwrite')
    need(1 <= len(requests['cases']) <= 100, 'Invalid evaluation batch')
    r = {'scope': 'Actual isolated MCP reads requested by blind agent; not daily-session E2E', 'requestSha256': digest(p), 'calls': [], 'cases': []}
    os.environ.update(x['pins']())
    guard = sqlite3.connect(str(x['TARGET']))
    guard.execute('SELECT count(*) FROM sqlite_master').fetchone()
    try:
        x['protect']()
        verify(plan, m)
        async with client(r, plan) as call:
            cache = {}
            for c in requests['cases']:
                need(set(c) == {'caseKey', 'readUris'} and len(c['readUris']) <= 12 and len(set(c['readUris'])) == len(c['readUris']), 'Invalid case request')
                item = {'caseKey': c['caseKey'], 'reads': []}
                for uri in c['readUris']:
                    need(uri in nodes, 'Unknown candidate URI')
                    # shortcut: reuse exact native read within this batch; do not claim per-case cold-start token cost.
                    if uri not in cache:
                        cache[uri] = await call('read_memory', {'uri': uri})
                    item['reads'].append({'uri': uri, 'text': cache[uri]})
                r['cases'].append(item)
        verify(plan, m)
        x['protect']()
        r['status'] = 'PASS'
    finally:
        guard.close()
        put(out, r)
    print(json.dumps({'status': r.get('status', 'FAILED'), 'cases': len(r['cases']), 'nativeCalls': len(r['calls']), 'output': str(out)}, ensure_ascii=True))

def self_test(plan, m):
    validate(plan, m)
    bads = []
    for field, value in [('databaseUrl', 'sqlite+aiosqlite:///wrong.db'), ('namespace', 'other'), ('g3Allowed', True)]:
        q = json.loads(json.dumps(plan)); q[field] = value; bads.append(q)
    for field, value in [('keyword', '状态'), ('keyword', 'does_not_exist_8aa1'), ('sourceUri', 'core://missing'), ('targetUri', 'core://missing')]:
        q = json.loads(json.dumps(plan)); q['bindings'][0][field] = value; bads.append(q)
    q = json.loads(json.dumps(plan)); q['bindings'][0]['targetUri'] = q['bindings'][0]['sourceUri']; bads.append(q)
    for q in bads:
        try:
            validate(q, m)
        except (RuntimeError, KeyError):
            continue
        raise RuntimeError('Negative boundary accepted')
    need(links('GLOSSARY (keywords detected in this content)\n- @x -> core://agent/verification\nCHILD MEMORIES\ncore://other') == {'core://agent/verification'}, 'Glossary parser swallowed child metadata')
    need(not links('MEMORY: core://agent\nbody mentions core://other'), 'Body URI mistaken for link')
    print(json.dumps({'selfTest': 'PASS', 'negativeGuards': len(bads), 'parserAssertions': 2, 'filesystemWrites': 0}))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--self-test', action='store_true')
    mode.add_argument('--run', action='store_true')
    mode.add_argument('--probe')
    args = parser.parse_args()
    m = load(x['INPUT']); x['validate_input'](m)
    plan = load(PLAN); nodes = validate(plan, m)
    if args.self_test:
        self_test(plan, m)
    elif args.run:
        asyncio.run(execute(plan, m, nodes))
    else:
        asyncio.run(probe(plan, m, nodes, args.probe))
