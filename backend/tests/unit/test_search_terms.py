from db.search_terms import build_document_search_terms, expand_query_terms


def test_expand_query_terms_normalizes_paths_and_cjk_content():
    expanded = expand_query_terms("project://nocturne_memory/architecture GraphService 记忆")

    assert "project" in expanded
    assert "nocturne_memory" in expanded
    assert "architecture" in expanded
    assert "GraphService" in expanded
    assert "记忆" in expanded


def test_build_document_search_terms_includes_path_uri_glossary_and_disclosure():
    terms = build_document_search_terms(
        path="project/nocturne_memory",
        uri="project://nocturne_memory",
        content="GraphService coordinates glossary triggers",
        disclosure="当讨论架构时",
        glossary_text="Salem 豆辞典",
    )

    assert "GraphService" in terms
    assert "project" in terms
    assert "nocturne_memory" in terms
    assert "Salem" in terms
    assert "豆辞典" in terms
    assert "架构" in terms


def test_glossary_indexing_does_not_change_query_segmentation():
    keyword = "多项目工作区"
    before = expand_query_terms(keyword)

    terms = build_document_search_terms("target", "core://target", "", None, keyword)

    assert expand_query_terms(keyword) == before
    assert set(before.split()) <= set(terms.split())


def test_glossary_index_is_searchable_from_a_fresh_process():
    import json
    import sqlite3
    import subprocess
    import sys
    from pathlib import Path

    keyword = "多项目工作区"
    terms = build_document_search_terms("target", "core://target", "", None, keyword)
    code = (
        "import json; from db.search_terms import expand_query_terms; "
        f"print(json.dumps(expand_query_terms({keyword!r}).split()))"
    )
    cold_tokens = json.loads(subprocess.check_output(
        [sys.executable, "-B", "-X", "utf8", "-c", code],
        cwd=Path(__file__).resolve().parents[2],
        text=True,
        encoding="utf-8",
    ))
    match_query = " AND ".join(f'"{token}"' for token in cold_tokens)
    with sqlite3.connect(":memory:") as con:
        con.execute("CREATE VIRTUAL TABLE docs USING fts5(search_terms)")
        con.execute("INSERT INTO docs(search_terms) VALUES (?)", (terms,))
        assert con.execute(
            "SELECT count(*) FROM docs WHERE docs MATCH ?", (match_query,)
        ).fetchone()[0] == 1
