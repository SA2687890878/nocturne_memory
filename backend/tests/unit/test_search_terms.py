from db.search_terms import (
    build_document_search_terms,
    expand_query_terms,
    expand_query_alternatives,
)


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



def test_query_phrase_aliases_are_conservative_and_do_not_rewrite_original_terms():
    query = "上次开发任务怎么找回来"

    assert expand_query_alternatives(query) == ["恢复任务"]
    assert expand_query_alternatives("我常用哪些开发技术") == []
    assert expand_query_alternatives("交接给下一个会话要留下什么") == ["交接保留"]
    assert expand_query_alternatives("恢复之前开发进度需要先看什么") == ["恢复任务"]
    assert expand_query_alternatives("切换会话前应该交代哪些信息") == ["交接保留"]
    assert expand_query_alternatives("自动化测试用例应该怎么设计") == ["用例设计"]
    assert expand_query_alternatives("把之前那个开发任务接着做，第一步去哪里找") == ["恢复任务"]
    assert expand_query_alternatives("Mock 返回值不够了测试应当怎么报错") == ["期望耗尽"]
    assert expand_query_alternatives("回答尽量短一点，列清楚重点") == ["回复简洁精准"]
    assert expand_query_alternatives("Nocturne 里哪些记忆不应该自动清理") == ["自动删除"]
    assert expand_query_alternatives("配置调整后怎样证明新配置确实加载了") == ["配置变更 同源解析"]
    assert expand_query_terms(query) == "上次 开发 任务 怎么 找 回来"



def test_partial_match_coverage_requires_multiple_query_terms():
    from db.search import MIN_PARTIAL_MATCH_COVERAGE, _partial_match_coverage

    query = "alpha beta gamma delta epsilon"
    relevant_terms, relevant_coverage = _partial_match_coverage(
        query, {"snippet": "alpha beta gamma"}
    )
    noise_terms, noise_coverage = _partial_match_coverage(
        query, {"snippet": "alpha"}
    )

    assert MIN_PARTIAL_MATCH_COVERAGE == 0.26
    assert relevant_terms == ["alpha", "beta", "gamma"]
    assert relevant_coverage == 0.6
    assert noise_terms == ["alpha"]
    assert noise_coverage == 0.2
    assert relevant_coverage >= MIN_PARTIAL_MATCH_COVERAGE
    assert noise_coverage < MIN_PARTIAL_MATCH_COVERAGE
