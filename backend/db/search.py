# pyright: reportArgumentType=false, reportAttributeAccessIssue=false, reportCallIssue=false, reportOperatorIssue=false

"""
FTS Search Indexer and Query Engine for Nocturne Memory System.

Maintains derived search rows (search_documents / search_documents_fts)
and provides full-text search across the memory graph.
"""

from typing import Optional, Dict, Any, List, TYPE_CHECKING

from sqlalchemy import select, delete, text, or_
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    Memory,
    Edge,
    Path,
    GlossaryKeyword,
    SearchDocument,
    escape_like_literal,
)
from .search_terms import (
    build_document_search_terms,
    expand_query_terms,
    expand_query_alternatives,
)


MIN_PARTIAL_MATCH_COVERAGE = 0.26
MAX_PARTIAL_FALLBACK_RESULTS = 3


def _partial_match_coverage(query: str, row: Dict[str, Any]) -> tuple[List[str], float]:
    tokens = list(dict.fromkeys(expand_query_terms(query).split()))
    searchable = " ".join(
        str(row.get(field) or "")
        for field in ("path", "uri", "summary_content", "snippet", "disclosure")
    ).lower()
    matched_terms = [token for token in tokens if token.lower() in searchable]
    coverage = round(len(matched_terms) / max(len(tokens), 1), 3)
    return matched_terms, coverage

if TYPE_CHECKING:
    from .database import DatabaseManager


class SearchIndexer:
    """FTS index maintenance and query engine.

    Manages the derived search_documents table, keeping it in sync with
    the live graph state.  Supports both SQLite FTS5 and PostgreSQL
    tsvector backends.
    """

    def __init__(self, db: "DatabaseManager"):
        self._session = db.session
        self._optional_session = db._optional_session
        self.db_type = db.db_type

    # -----------------------------------------------------------------
    # Query helpers (stateless)
    # -----------------------------------------------------------------

    @staticmethod
    def _to_sqlite_match_query(query: str, operator: str = "AND") -> str:
        """Convert free text into a safe FTS5 expression.

        AND is preferred for precision. OR is used only as a fallback when
        the strict query returns no candidates, avoiding empty results for
        natural-language requests that contain extra descriptive words.
        """
        normalized = expand_query_terms(query)
        tokens = [token.replace('"', '""') for token in normalized.split() if token]
        if not tokens:
            raw = query.strip().replace('"', '""')
            return f'"{raw}"' if raw else ""
        joiner = " OR " if operator.upper() == "OR" else " AND "
        return joiner.join(f'"{token}"' for token in tokens)

    @staticmethod
    def _format_search_snippet(content: str, query: str) -> str:
        """Build a short content snippet around the first literal hit or token hit."""
        if not content:
            return ""

        content_lower = content.lower()
        query_lower = query.lower()

        pos = content_lower.find(query_lower)
        match_len = len(query)

        if pos < 0:
            tokens = expand_query_terms(query).split()
            for token in tokens:
                if not token:
                    continue
                pos = content_lower.find(token.lower())
                if pos >= 0:
                    match_len = len(token)
                    break

        if pos < 0:
            fallback = content[:80]
            return fallback + ("..." if len(content) > 80 else "")

        start = max(0, pos - 30)
        end = min(len(content), pos + match_len + 30)
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(content) else ""
        return prefix + content[start:end] + suffix

    # -----------------------------------------------------------------
    # Index maintenance
    # -----------------------------------------------------------------

    async def _build_search_documents_for_node(
        self, session: AsyncSession, node_uuid: str, *, namespace: str = "", search_all_namespaces: bool = False
    ) -> List[Dict[str, Any]]:
        """Materialize search rows for every reachable path of a node.

        When search_all_namespaces is True, builds for ALL namespaces.
        Otherwise only builds docs for paths in the specified namespace.
        """
        memory = (
            await session.execute(
                select(Memory)
                .where(Memory.node_uuid == node_uuid, Memory.deprecated == False)
                .limit(1)
            )
        ).scalar_one_or_none()
        if not memory:
            return []

        path_stmt = (
            select(Path.namespace, Path.domain, Path.path, Edge.priority, Edge.disclosure)
            .select_from(Path)
            .join(Edge, Path.edge_id == Edge.id)
            .where(Path.node_uuid == node_uuid)
        )
        if not search_all_namespaces:
            path_stmt = path_stmt.where(Path.namespace == namespace)
        path_stmt = path_stmt.order_by(Path.domain, Path.path)
        path_rows = (await session.execute(path_stmt)).all()
        if not path_rows:
            return []

        keyword_stmt = select(GlossaryKeyword.keyword, GlossaryKeyword.namespace).where(
            GlossaryKeyword.node_uuid == node_uuid
        )
        if not search_all_namespaces:
            keyword_stmt = keyword_stmt.where(GlossaryKeyword.namespace == namespace)

        keyword_rows = await session.execute(keyword_stmt)
        
        from collections import defaultdict
        keywords_by_ns = defaultdict(list)
        for kw, ns in keyword_rows:
            if kw:
                keywords_by_ns[ns].append(kw)

        documents = []
        for row in path_rows:
            uri = f"{row.domain}://{row.path}"
            ns_keywords = keywords_by_ns.get(row.namespace, [])
            glossary_text = " ".join(sorted(ns_keywords))
            documents.append(
                {
                    "namespace": row.namespace,
                    "domain": row.domain,
                    "path": row.path,
                    "node_uuid": node_uuid,
                    "memory_id": memory.id,
                    "uri": uri,
                    "summary_content": memory.summary_content,
                    "content": memory.content,
                    "disclosure": row.disclosure,
                    "search_terms": build_document_search_terms(
                        row.path,
                        uri,
                        memory.content,
                        row.disclosure,
                        glossary_text,
                    ),
                    "priority": row.priority,
                }
            )
        return documents

    async def _delete_search_documents_for_node(
        self, session: AsyncSession, node_uuid: str, *, namespace: str = "", search_all_namespaces: bool = False
    ) -> None:
        """Remove derived search rows for a node.

        When search_all_namespaces is True, removes ALL namespaces.
        Otherwise only removes docs in the specified namespace.
        """
        if not search_all_namespaces:
            if self.db_type == "sqlite":
                await session.execute(
                    text(
                        "DELETE FROM search_documents_fts "
                        "WHERE node_uuid = :node_uuid AND namespace = :namespace"
                    ),
                    {"node_uuid": node_uuid, "namespace": namespace},
                )
            await session.execute(
                delete(SearchDocument).where(
                    SearchDocument.node_uuid == node_uuid,
                    SearchDocument.namespace == namespace,
                )
            )
        else:
            if self.db_type == "sqlite":
                await session.execute(
                    text("DELETE FROM search_documents_fts WHERE node_uuid = :node_uuid"),
                    {"node_uuid": node_uuid},
                )
            await session.execute(
                delete(SearchDocument).where(SearchDocument.node_uuid == node_uuid)
            )

    async def _insert_search_documents(
        self, session: AsyncSession, documents: List[Dict[str, Any]]
    ) -> None:
        """Insert fresh derived search rows for one node."""
        if not documents:
            return

        session.add_all(SearchDocument(**doc) for doc in documents)
        await session.flush()

        if self.db_type != "sqlite":
            return

        for doc in documents:
            await session.execute(
                text(
                    """
                    INSERT INTO search_documents_fts (
                        namespace, domain, path, node_uuid, uri, summary_content, content, disclosure, search_terms
                    ) VALUES (
                        :namespace, :domain, :path, :node_uuid, :uri, coalesce(:summary_content, ''), :content, coalesce(:disclosure, ''), :search_terms
                    )
                    """
                ),
                doc,
            )

    async def refresh_search_documents_for_node(
        self, node_uuid: str, session: Optional[AsyncSession] = None, namespace: str = "", refresh_all_namespaces: bool = False
    ) -> None:
        """Rebuild derived search rows for one node in the given namespace (defaults to current)."""
        async with self._optional_session(session) as session:
            documents = await self._build_search_documents_for_node(
                session, node_uuid, namespace=namespace, search_all_namespaces=refresh_all_namespaces
            )
            await self._delete_search_documents_for_node(
                session, node_uuid, namespace=namespace, search_all_namespaces=refresh_all_namespaces
            )
            await self._insert_search_documents(session, documents)

    async def get_node_uuids_for_prefix(
        self, session: AsyncSession, domain: str, base_path: str, namespace: str = ""
    ) -> List[str]:
        """Collect unique node UUIDs for a path and all descendants."""
        safe = escape_like_literal(base_path)
        result = await session.execute(
            select(Path.node_uuid)
            .where(Path.namespace == namespace)
            .where(Path.domain == domain)
            .where(
                or_(
                    Path.path == base_path,
                    Path.path.like(f"{safe}/%", escape="\\"),
                )
            )
            .distinct()
        )
        return [row[0] for row in result.all()]

    async def rebuild_all_search_documents(
        self, session: Optional[AsyncSession] = None
    ) -> None:
        """Fully rebuild the derived search index from live graph state (all namespaces)."""
        async with self._optional_session(session) as session:
            if self.db_type == "sqlite":
                await session.execute(text("DELETE FROM search_documents_fts"))

            await session.execute(delete(SearchDocument))

            result = await session.execute(
                select(Path.node_uuid).distinct()
            )
            for (node_uuid,) in result.all():
                documents = await self._build_search_documents_for_node(
                    session, node_uuid, search_all_namespaces=True
                )
                await self._insert_search_documents(session, documents)

    # -----------------------------------------------------------------
    # Public search API
    # -----------------------------------------------------------------

    async def search(
        self,
        query: str,
        limit: int = 10,
        domain: Optional[str] = None,
        namespace: str = "",
        include_obsolete: bool = False,
        include_partial: bool = False,
        include_snippets: bool = True,
    ) -> List[Dict[str, Any]]:
        """Search memories by path and content using the derived FTS index.

        Obsolete nodes are excluded by default before ranking, de-duplication
        and LIMIT, so their slots go to still-valid memories.
        Snippets remain opt-in at the MCP boundary. Partial matching still
        computes its bounded evidence internally to preserve coverage/ranking.
        """
        async with self._session() as session:
            candidate_limit = max(limit * 5, 50)
            params: Dict[str, Any] = {
                "candidate_limit": candidate_limit,
                "namespace": namespace,
            }
            status_clause = "" if include_obsolete else "AND n.lifecycle_status != 'obsolete'"
            domain_clause = ""
            if domain is not None:
                params["domain"] = domain
                domain_clause = "AND sd.domain = :domain"

            partial_rows = []
            synonym_rows = []
            used_relaxed_fallback = False
            if self.db_type == "sqlite":
                match_query = self._to_sqlite_match_query(query)
                if not match_query:
                    return []

                params["match_query"] = match_query
                snippet_projection = "''"
                if include_snippets or include_partial:
                    snippet_projection = """CASE
                            WHEN snippet(search_documents_fts, 6, '', '', ' … ', 24) != ''
                            THEN snippet(search_documents_fts, 6, '', '', ' … ', 24)
                            ELSE substr(sd.content, 1, 240)
                        END"""
                search_stmt = text(
                    f"""
                    SELECT
                        sd.domain,
                        sd.path,
                        sd.node_uuid,
                        sd.uri,
                        sd.priority,
                        sd.memory_id,
                        sd.summary_content,
                        {snippet_projection} AS snippet,
                        sd.disclosure,
                        bm25(search_documents_fts, 0.0, 0.0, 2.5, 0.0, 2.0, 2.5, 1.0, 1.0, 0.75) AS score
                    FROM search_documents AS sd
                    JOIN nodes AS n ON n.uuid = sd.node_uuid
                    JOIN search_documents_fts
                      ON search_documents_fts.namespace = sd.namespace
                     AND search_documents_fts.domain = sd.domain
                     AND search_documents_fts.path = sd.path
                    WHERE search_documents_fts MATCH :match_query
                      AND sd.namespace = :namespace
                      {domain_clause}
                      {status_clause}
                    ORDER BY score ASC, sd.priority ASC, length(sd.path) ASC
                    LIMIT :candidate_limit
                    """
                )
                result = await session.execute(search_stmt, params)
                rows = [dict(row) for row in result.mappings().all()]

                # Evaluate curated phrase aliases even when the original query
                # has broad strict hits. Generic shared words can otherwise mask
                # the intended memory. Keep original strict hits first; aliases
                # are appended only when they refer to a different Node.
                strict_positions = {
                    row["node_uuid"]: index for index, row in enumerate(rows)
                }
                seen_synonym_nodes = set()
                promoted_synonym_nodes = set()
                for alternative in expand_query_alternatives(query):
                    alternative_match = self._to_sqlite_match_query(alternative)
                    if not alternative_match:
                        continue
                    alternative_params = {**params, "match_query": alternative_match}
                    alternative_result = await session.execute(search_stmt, alternative_params)
                    for row in alternative_result.mappings().all():
                        node_uuid = row["node_uuid"]
                        if node_uuid in seen_synonym_nodes:
                            continue
                        seen_synonym_nodes.add(node_uuid)
                        strict_position = strict_positions.get(node_uuid)
                        if strict_position == 0:
                            # Never displace the best original-query hit.
                            continue
                        if strict_position is not None:
                            # The alias target already matched the broad strict
                            # query, but ranked below the first result. Promote
                            # it into the curated lane instead of deduplicating
                            # it away behind dozens of generic matches.
                            promoted_synonym_nodes.add(node_uuid)
                        synonym_rows.append(dict(row))

                if promoted_synonym_nodes:
                    rows = [
                        row for row in rows
                        if row["node_uuid"] not in promoted_synonym_nodes
                    ]

                if not rows and synonym_rows:
                    # A curated AND alternative is a precise recovery; do not
                    # dilute it with broad OR candidates.
                    pass
                elif not rows and include_partial:
                    # OR fallback is a second-stage disclosure. The default
                    # strict pass must stay empty rather than silently returning
                    # weak candidates; callers explicitly opt in after review.
                    params["match_query"] = self._to_sqlite_match_query(query, operator="OR")
                    result = await session.execute(search_stmt, params)
                    rows = [dict(row) for row in result.mappings().all()]
                    rows = [
                        row for row in rows
                        if _partial_match_coverage(query, row)[1] >= MIN_PARTIAL_MATCH_COVERAGE
                    ][:min(limit, MAX_PARTIAL_FALLBACK_RESULTS)]
                    used_relaxed_fallback = bool(rows)
                elif include_partial:
                    # Optional diagnostic lane; strict and curated alias hits
                    # remain ahead of partial candidates.
                    params["match_query"] = self._to_sqlite_match_query(query, operator="OR")
                    result = await session.execute(search_stmt, params)
                    partial_rows = [
                        dict(row) for row in result.mappings().all()
                        if row["node_uuid"] not in seen_synonym_nodes
                        and _partial_match_coverage(query, row)[1] >= MIN_PARTIAL_MATCH_COVERAGE
                    ][:min(limit, 5)]
            else:
                normalized = expand_query_terms(query)
                if not normalized:
                    return []

                params["ts_query"] = normalized
                snippet_projection = "''"
                if include_snippets:
                    snippet_projection = """ts_headline(
                                'simple', coalesce(sd.content, ''),
                                websearch_to_tsquery('simple', :ts_query),
                                'MaxFragments=1, MinWords=8, MaxWords=24, ShortWord=2'
                            )"""
                result = await session.execute(
                    text(
                        f"""
                        SELECT
                            sd.domain,
                            sd.path,
                            sd.node_uuid,
                            sd.uri,
                            sd.priority,
                            sd.memory_id,
                            sd.summary_content,
                            {snippet_projection} AS snippet,
                            sd.disclosure,
                            ts_rank_cd(
                                to_tsvector(
                                    'simple',
                                    coalesce(sd.path, '') || ' ' ||
                                    coalesce(sd.uri, '') || ' ' ||
                                    coalesce(sd.summary_content, '') || ' ' ||
                                    coalesce(sd.content, '') || ' ' ||
                                    coalesce(sd.disclosure, '') || ' ' ||
                                    coalesce(sd.search_terms, '')
                                ),
                                websearch_to_tsquery('simple', :ts_query)
                            ) AS score
                        FROM search_documents AS sd
                        JOIN nodes AS n ON n.uuid = sd.node_uuid
                        WHERE sd.namespace = :namespace
                          {status_clause}
                          AND to_tsvector(
                                'simple',
                                coalesce(sd.path, '') || ' ' ||
                                coalesce(sd.uri, '') || ' ' ||
                                coalesce(sd.summary_content, '') || ' ' ||
                                 coalesce(sd.content, '') || ' ' ||
                                coalesce(sd.disclosure, '') || ' ' ||
                                coalesce(sd.search_terms, '')
                              ) @@ websearch_to_tsquery('simple', :ts_query)
                          {domain_clause}
                        ORDER BY score DESC, sd.priority ASC, char_length(sd.path) ASC
                        LIMIT :candidate_limit
                        """
                    ),
                    params,
                )
                rows = result.mappings().all()

            matches = []
            matches_by_node = {}

            strict_or_fallback_rows = [
                (row, "partial" if used_relaxed_fallback else "strict") for row in rows
            ]
            # Preserve the strongest original-query result at rank 1, then
            # surface curated phrase-alias hits before weaker generic strict
            # matches. This prevents broad shared words from consuming Top10.
            if synonym_rows and not used_relaxed_fallback and strict_or_fallback_rows:
                combined_rows = strict_or_fallback_rows[:1]
                combined_rows.extend((row, "strict") for row in synonym_rows)
                combined_rows.extend(strict_or_fallback_rows[1:])
            else:
                combined_rows = strict_or_fallback_rows
                combined_rows.extend((row, "strict") for row in synonym_rows)
            combined_rows.extend((row, "partial") for row in partial_rows)
            for row, match_type in combined_rows:
                node_uuid = row["node_uuid"]
                entry = {
                    "domain": row["domain"],
                    "path": row["path"],
                    "uri": row["uri"],
                    "priority": row["priority"],
                    "disclosure": row["disclosure"],
                }
                existing = matches_by_node.get(node_uuid)
                if existing is not None:
                    # Keep one content payload per entity while retaining each
                    # matching URI entry and its actual edge metadata.
                    existing["aliases"].append(entry)
                    continue
                if len(matches) >= limit:
                    continue

                summary = row["summary_content"]
                match = {
                    **entry,
                    "name": row["path"].rsplit("/", 1)[-1],
                    "memory_id": row["memory_id"],
                    "summary": summary or None,
                    "summary_status": "VALID" if summary else "MISSING",
                    "expandable": True,
                    "snippet": (row["snippet"] or "") if include_snippets else "",
                    "aliases": [],
                }
                # Always expose relaxed-fallback provenance. Otherwise the
                # default MCP response makes weak OR/partial candidates look
                # indistinguishable from strict hits to the calling agent.
                if include_partial or match_type == "partial":
                    match["match_type"] = match_type
                    if match_type == "partial":
                        matched_terms, coverage = _partial_match_coverage(query, row)
                        match["matched_terms"] = matched_terms
                        match["match_coverage"] = coverage
                matches_by_node[node_uuid] = match
                matches.append(match)

            return matches
