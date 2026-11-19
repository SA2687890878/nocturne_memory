# pyright: reportMissingImports=false

"""
MCP Server for Nocturne Memory System (SQLite Backend)

This module provides the MCP (Model Context Protocol) interface for
the AI agent to interact with the SQLite-based memory system.

URI-based addressing with domain prefixes:
- core://agent              - AI's identity/memories
- writer://chapter_1             - Story/script drafts
- game://magic_system            - Game setting documents

Multiple paths can point to the same memory (aliases).
"""

import asyncio
import os
import re
import shutil
import subprocess
import sys
import webbrowser
from typing import Any, Dict, List, Optional, Tuple, Annotated
from pydantic import Field
import config as _cfg

# Ensure we can import from backend modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from mcp.server.fastmcp import FastMCP
    IS_MCP_V2 = False
except ImportError:
    from mcp.server.mcpserver import MCPServer as FastMCP
    IS_MCP_V2 = True

from mcp.server.transport_security import TransportSecuritySettings
from db import (
    get_db_manager, get_graph_service, get_glossary_service,
    get_search_indexer, close_db,
)
from db.namespace import get_namespace
from db.snapshot import get_changeset_store
from db.models import LifecycleStatus
from text_patch import (
    normalize_with_positions,
    find_valid_matches,
    try_normalized_patch,
    normalize_literal_newlines,
    format_normalization_preview,
)
from system_views import (
    fetch_and_format_memory,
    generate_boot_memory_view,
    generate_memory_index_view,
    generate_recent_memories_view,
    generate_glossary_index_view,
    generate_diagnostic_view,
    _estimate_context_tokens,
    _truncate_utf8_to_token_budget,
)
import contextlib
from locales import t



from web_app import FRONTEND_DIR, build_web_app
from frontend_builder import get_frontend_builder
from semantic_search import search_semantic_memories
from system_diagnostics import diagnose_memory_database
from semantic_sync import sync_configured_vector_index


@contextlib.asynccontextmanager
async def lifespan(server: FastMCP):
    """Manage database connection lifecycle within the MCP event loop."""
    web_server = None
    web_task = None
    try:
        _cfg.ensure_config_exists()

        db_manager = get_db_manager()
        if os.environ.get("SKIP_DB_INIT", "").lower() not in ("true", "1", "yes"):
            await db_manager.init_db()

        # Auto-promote config.json boot_uris into presets table on first run
        from db import get_preset_service
        preset_service = get_preset_service()
        await preset_service.auto_promote_from_config()

        # The combined HTTP service owns the UI build. MCP-only clients should
        # not start a second npm installer/build process.
        if not os.environ.get("NOCTURNE_NO_UI"):
            get_frontend_builder().ensure_built_background()

        # In stdio mode, spin up an embedded HTTP server for the admin UI.
        # run_sse.py sets _NOCTURNE_SSE_MODE to prevent a duplicate.
        if not os.environ.get("_NOCTURNE_SSE_MODE") and not os.environ.get("NOCTURNE_NO_UI"):
            import uvicorn
            from auth import enforce_network_auth

            port = int(_cfg.get("web_port"))
            web_host = _cfg.get("host")
            enforce_network_auth(host=web_host)
            @contextlib.asynccontextmanager
            async def embedded_lifespan(app):
                # The parent process (FastMCP lifespan) already owns DB init & close.
                # The embedded admin UI should not manage the database connection lifecycle.
                yield

            config = uvicorn.Config(
                build_web_app(lifespan=embedded_lifespan), host=web_host, port=port, log_level="warning",
            )
            web_server = uvicorn.Server(config)
            
            async def _serve_ui():
                try:
                    await web_server.serve()
                except Exception:
                    # Ignore the raw error message (usually OSError for address in use)
                    # and print a user-friendly explanation.
                    print(t("startup.port_in_use").format(port=port), file=sys.stderr)
                except SystemExit:
                    print(t("startup.port_in_use").format(port=port), file=sys.stderr)

            web_task = asyncio.create_task(_serve_ui())
            ui = f"http://localhost:{port}/"
            api_docs = f"http://localhost:{port}/api/docs"
            
            print(f"Admin UI:  {ui}", file=sys.stderr)
            print(f"REST API:  {api_docs}", file=sys.stderr)

            auto_open = _cfg.get("auto_open_browser")
            if auto_open:
                async def _open_browser():
                    while not getattr(web_server, "started", False):
                        if web_task.done():
                            return
                        await asyncio.sleep(0.1)
                    webbrowser.open(ui)
                asyncio.create_task(_open_browser())

        yield
    finally:
        if web_server:
            web_server.should_exit = True
        if web_task:
            await web_task
        await close_db()


sec_settings = TransportSecuritySettings(
    enable_dns_rebinding_protection=False  # safe when behind a trusted reverse proxy
)

# Initialize FastMCP server with the lifespan hook
if IS_MCP_V2:
    mcp = FastMCP(
        "Nocturne Memory Interface",
        lifespan=lifespan,
    )
else:
    mcp = FastMCP(
        "Nocturne Memory Interface",
        lifespan=lifespan,
        transport_security=sec_settings,
    )

# =============================================================================
# Domain Configuration
# =============================================================================
# Valid domains (protocol prefixes)
# =============================================================================

def get_valid_domains() -> list[str]:
    raw = _cfg.get("valid_domains")
    domains = raw if isinstance(raw, list) else [
        d.strip() for d in str(raw).split(",") if d.strip()
    ]
    if "system" not in domains:
        domains.append("system")
    return domains

DEFAULT_DOMAIN = "core"
PUBLIC_READONLY_MCP = bool(_cfg.get("public_readonly_mcp"))



# =============================================================================
# URI Parsing
# =============================================================================

# Regex pattern for URI: domain://path
_URI_PATTERN = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_]*)://(.*)$")


def parse_uri(uri: str) -> Tuple[str, str]:
    """
    Parse a memory URI into (domain, path).

    Supported formats:
    - "core://agent"          -> ("core", "agent")
    - "writer://chapter_1"         -> ("writer", "chapter_1")
    - "nocturne"              -> ("core", "nocturne")  [legacy fallback]

    Args:
        uri: The URI to parse

    Returns:
        Tuple of (domain, path)

    Raises:
        ValueError: If the URI format is invalid or domain is unknown
    """
    uri = uri.strip()

    match = _URI_PATTERN.match(uri)
    if match:
        domain = match.group(1).lower()
        path = match.group(2).strip("/")

        valid = get_valid_domains()
        if domain not in valid:
            raise ValueError(
                f"Unknown domain '{domain}'. Valid domains: {', '.join(valid)}"
            )

        return (domain, path)

    # Legacy fallback: bare path without protocol
    # Assume default domain (core)
    path = uri.strip("/")
    return (DEFAULT_DOMAIN, path)


def make_uri(domain: str, path: str) -> str:
    """
    Create a URI from domain and path.

    Args:
        domain: The domain (e.g., "core", "writer")
        path: The path (e.g., "nocturne")

    Returns:
        Full URI (e.g., "core://agent")
    """
    return f"{domain}://{path}"


# =============================================================================
# Changeset Helpers — before/after state capture with overwrite semantics
# =============================================================================


def _record_rows(
    before_state: Dict[str, List[Dict[str, Any]]],
    after_state: Dict[str, List[Dict[str, Any]]],
):
    """
    Feed row-level before/after states into the ChangesetStore.

    Overwrite semantics are handled by the store:
    - First touch of a PK: stores both before and after.
    - Subsequent touches: overwrites after only; before is frozen.

    Changes are written to the namespace-specific store so that each agent's
    review queue remains isolated.
    """
    store = get_changeset_store()
    store.record_many(before_state, after_state)


def write_tool():
    """Conditionally register mutating tools for public read-only deployments."""

    def decorator(func):
        if PUBLIC_READONLY_MCP:
            return func
        return mcp.tool()(func)

    return decorator




# =============================================================================
# MCP Tools
# =============================================================================


@mcp.tool()
async def read_memory(uri: str) -> str:
    '按 URI 读取记忆正文或系统视图。需要原文、代码、接口或参数时调用。\n\n同一会话中某 URI 已成功读取后，复用已读内容，不要重复读取；仅在正文已更新或明确需要最新版本时重读。父入口与专项子记忆已分别读取后，不要再次读取相同 URI。\n\n参数：uri — 记忆 URI；也支持 system://boot、system://index/<domain>、system://recent、system://glossary 等系统视图。'
    # HARDCODED SYSTEM INTERCEPTIONS
    # These bypass the database lookup to serve dynamic system content
    if uri.strip() == "system://boot":
        ns = get_namespace()
        from db import get_preset_service
        preset_service = get_preset_service()
        current_core_uris = await preset_service.get_boot_uris(ns)
        return await generate_boot_memory_view(current_core_uris)

    # system://index/<domain>
    stripped = uri.strip()
    if stripped.startswith("system://index/"):
        domain_filter = stripped[len("system://index/") :].strip("/")
        if not domain_filter:
            return "Error: index command requires a domain (e.g. system://index/core)"
        valid = get_valid_domains()
        if domain_filter not in valid:
            return f"Error: Unknown domain '{domain_filter}'. Valid domains: {', '.join(valid)}"
        return await generate_memory_index_view(domain_filter=domain_filter)
    elif stripped == "system://index":
        return "Error: index command now requires a domain (e.g. system://index/core)"

    # system://glossary
    if stripped == "system://glossary":
        return await generate_glossary_index_view()

    # system://diagnostic/<domain>
    if stripped.startswith("system://diagnostic/"):
        domain_filter = stripped[len("system://diagnostic/") :].strip("/")
        if not domain_filter:
            return "Error: diagnostic command requires a domain (e.g. system://diagnostic/core)"
        valid = get_valid_domains()
        if domain_filter not in valid:
            return f"Error: Unknown domain '{domain_filter}'. Valid domains: {', '.join(valid)}"
        return await generate_diagnostic_view(domain=domain_filter)
    elif stripped == "system://diagnostic":
        return "Error: diagnostic command now requires a domain (e.g. system://diagnostic/core)"

    # system://recent or system://recent/N
    stripped = uri.strip()
    if stripped == "system://recent" or stripped.startswith("system://recent/"):
        limit = 10  # default
        suffix = stripped[len("system://recent") :].strip("/")
        if suffix:
            try:
                limit = max(1, min(100, int(suffix)))
            except ValueError:
                return f"Error: Invalid number in URI '{uri}'. Usage: system://recent or system://recent/N (e.g. system://recent/20)"
        return await generate_recent_memories_view(limit=limit)

    # system://random/<domain> — weighted random memory selection
    if stripped.startswith("system://random/"):
        domain_filter = stripped[len("system://random/") :].strip("/")
        if not domain_filter:
            return "Error: random command requires a domain (e.g. system://random/core)"
        valid = get_valid_domains()
        if domain_filter not in valid:
            return f"Error: Unknown domain '{domain_filter}'. Valid domains: {', '.join(valid)}"

        graph = get_graph_service()
        pick = await graph.get_random_memory(namespace=get_namespace(), domain=domain_filter)
        if not pick:
            return f"No memories available for random selection in domain '{domain_filter}'."
        content = await fetch_and_format_memory(pick["uri"], track_access=True)
        meta_lines = [
            f"[Random Pick | Priority: {pick['priority']} | Last Accessed: {pick['last_accessed_at'] or 'never'}]",
        ]
        return "\n".join(meta_lines) + "\n\n" + content
    elif stripped == "system://random":
        return "Error: random command now requires a domain (e.g. system://random/core)"

    try:
        content = await fetch_and_format_memory(uri, track_access=True)
        return content
    except Exception as e:
        # Catch both ValueError (not found) and other exceptions
        return f"Error: {str(e)}"


@write_tool()
async def create_memory(
    parent_uri: Annotated[str, Field(
        description="父节点 URI，例如 core://agent。"
    )],
    content: Annotated[str, Field(
        description="要保存的记忆正文。"
    )],
    priority: Annotated[int, Field(
        ge=0,
        description="检索优先级，数值越小越优先。"
    )],
    disclosure: Annotated[str, Field(
        description="召回条件，描述何时需要使用这条记忆。"
    )],
    title: Annotated[str, Field(
        default=None,
        description="英文概念名，仅允许字母、数字、连字符和下划线。"
    )],
    lifecycle_status: LifecycleStatus = "unspecified",
) -> str:
    '在指定父节点下创建记忆。创建前先搜索，确认没有可复用的已有记忆。\n\n参数：parent_uri — 父节点 URI；content — 记忆正文；priority — 检索优先级，数值越小越优先；disclosure — 何种场景需要召回；title — 英文概念名，仅允许字母、数字、连字符和下划线；lifecycle_status — 生命周期状态，默认 unspecified。'
    graph = get_graph_service()

    try:
        if priority < 0:
            return "Error: priority must be >= 0."

        # Validate disclosure (required, non-empty)
        if not disclosure or not disclosure.strip():
            return (
                "Error: disclosure is required. Every memory must have a trigger condition "
                "describing WHEN to recall it. Omitting disclosure = unreachable memory."
            )

        # Validate title if provided
        if title:
            if not re.match(r"^[a-zA-Z0-9_-]+$", title):
                return "Error: Title must only contain alphanumeric characters, underscores, or hyphens (no spaces, slashes, or special characters)."

        # Parse parent URI
        domain, parent_path = parse_uri(parent_uri)

        result = await graph.create_memory(
            parent_path=parent_path,
            content=content,
            priority=priority,
            title=title,
            disclosure=disclosure,
            domain=domain,
            namespace=get_namespace(),
            lifecycle_status=lifecycle_status,
        )

        created_uri = result.get("uri", make_uri(domain, result["path"]))
        _record_rows(before_state={}, after_state=result.get("rows_after", {}))

        return (
            f"Success: Memory created at '{created_uri}'\n\n"
            f"[SYSTEM REMINDER]: Look around your memory network. Are there existing memories related to this one? "
            f"Would reading them trigger a need to recall this new memory? If yes, link them!\\n"
            f"- If the related memories are few and this memory's scope is narrow, use `add_alias`.\\n"
            f"- If the related memories are many and this memory's scope is broad, consider using `manage_triggers`.\\n"
            f"- (Never invent arbitrary placeholder words just to force a trigger.)\\n\\n"
            f"[HOLD ON]: Do you know what '{parent_uri}' says? "
            f"If you haven't read it this session, read_memory() it first. "
            f"Then: does this new memory conflict with ANY memory in your current context? "
            f"If yes, use memory-audit-belief-duel skill to resolve it before continuing."
        )

    except ValueError as e:
        return f"Error: {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"


@write_tool()
async def update_memory_summary(memory_id: int, summary_content: str) -> str:
    '保存指定记忆版本的 AI 摘要；传入空字符串可清除摘要。\n\n参数：memory_id — 记忆版本 ID；summary_content — 摘要正文。'
    try:
        graph = get_graph_service()
        result = await graph.update_memory_summary(memory_id, summary_content)
        _record_rows(result.get("rows_before", {}), result.get("rows_after", {}))
        return (
            f"Success: summary for Memory {memory_id} is {result['summary_status']}. "
            f"Updated at: {result.get('summary_updated_at') or 'cleared'}."
        )
    except ValueError as e:
        return f"Error: {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"


@write_tool()
async def update_memory(
    uri: str,
    old_string: Optional[str] = None,
    new_string: Optional[str] = None,
    append: Optional[str] = None,
    priority: Optional[int] = None,
    disclosure: Optional[str] = None,
    lifecycle_status: Optional[LifecycleStatus] = None,
) -> str:
    '更新记忆正文或元数据。调用前必须先读取该 URI 的完整正文；仅更新传入的字段。\n\n参数：uri — 记忆 URI；old_string/new_string — 定位并替换文本，必须同时提供；append — 追加正文，与替换模式互斥；priority、disclosure、lifecycle_status — 可选元数据。正文修改会创建新版本；仅修改状态不会创建正文版本。'
    graph = get_graph_service()

    try:
        if priority is not None and priority < 0:
            return "Error: priority must be >= 0."

        notices: List[str] = []

        # Parse URI
        domain, path = parse_uri(uri)
        full_uri = make_uri(domain, path)

        # --- Validate mutually exclusive content-editing modes ---
        content_mode_count = sum([
            old_string is not None,
            append is not None,
        ])
        if content_mode_count > 1:
            return (
                "Error: Cannot use multiple content-editing modes at once. "
                "Pick one: old_string+new_string, or append."
            )

        if old_string is not None and new_string is None:
            return 'Error: old_string provided without new_string. To delete a section, use new_string="".'

        if new_string is not None and old_string is None:
            return "Error: new_string provided without old_string."

        content = None

        if old_string is not None:
            memory = await graph.get_memory_by_path(path, domain, namespace=get_namespace())
            if not memory:
                return f"Error: Memory at '{full_uri}' not found."

            current_content = memory.get("content", "")
            matches = set()

            def find_exact(search_str):
                s_idx = 0
                while True:
                    idx = current_content.find(search_str, s_idx)
                    if idx == -1: break
                    matches.add((idx, idx + len(search_str)))
                    s_idx = idx + 1

            # 1. Exact Match
            find_exact(old_string)

            # Normalize literal \n if present (LLM serialization artifact)
            if "\\n" in old_string:
                from text_patch import normalize_literal_newlines
                norm_old = normalize_literal_newlines(old_string)
                if norm_old != old_string:
                    find_exact(norm_old)

            # 2. Block Match
            SEPARATOR = "..."
            if SEPARATOR in old_string:
                start_marker = old_string[:old_string.find(SEPARATOR)]
                end_marker = old_string[old_string.rfind(SEPARATOR) + len(SEPARATOR):]
                
                if start_marker and end_marker:
                    s_idx = 0
                    while True:
                        s_pos = current_content.find(start_marker, s_idx)
                        if s_pos == -1: break
                        
                        e_idx = s_pos + len(start_marker)
                        while True:
                            e_pos = current_content.find(end_marker, e_idx)
                            if e_pos == -1: break
                            matches.add((s_pos, e_pos + len(end_marker)))
                            if len(matches) > 5:
                                break
                            e_idx = e_pos + 1
                            
                        if len(matches) > 5:
                            break
                        s_idx = s_pos + 1

            if len(matches) == 0:
                return (
                    f"Error: Could not find any match for `old_string` in '{full_uri}'. "
                    f"Please check the text and try again."
                )

            if len(matches) > 1:
                previews = []
                for i, (s, e) in enumerate(sorted(list(matches))[:5]):
                    snippet = current_content[s:e]
                    if len(snippet) > 80:
                        snippet = snippet[:40] + "..." + snippet[-37:]
                    previews.append(f"  Match {i+1} (pos {s}-{e}): {repr(snippet)}")
                
                msg = (
                    f"Error: Ambiguous update. Found multiple (at least {len(matches)}) different matching blocks for `old_string` in '{full_uri}'. "
                    f"Please provide a longer `old_string` string to ensure a unique match.\n"
                    + "\n".join(previews)
                )
                if len(matches) > 5:
                    msg += f"\n  ... and possibly more."
                return msg

            span_start, span_end = list(matches)[0]
            matched_text = current_content[span_start:span_end]
            
            # If the match was found using the normalized old_string (because LLM passed literal \n),
            # we must also normalize new_string so we don't inject literal \n into the text.
            if "\\n" in old_string and matched_text != old_string:
                from text_patch import normalize_literal_newlines
                norm_old = normalize_literal_newlines(old_string)
                if matched_text == norm_old and "\\n" in new_string:
                    new_string = normalize_literal_newlines(new_string)
                    notices.append("[SYSTEM NOTICE]: Auto-normalized literal '\\n' in new_string to real newlines.")
                
            content = current_content[:span_start] + new_string + current_content[span_end:]

            if content == current_content:
                return (
                    f"Error: Replacement produced identical content at '{full_uri}'. "
                    f"No change was made."
                )

            if len(matched_text) > 100:
                preview = matched_text[:50] + " ... " + matched_text[-47:]
            else:
                preview = matched_text
            notices.append(f"[Matched {len(matched_text)} chars]: {repr(preview)}")

        elif append is not None:
            if not append:
                return f"Error: Empty append for '{full_uri}'. Provide non-empty text to append."
            memory = await graph.get_memory_by_path(path, domain, namespace=get_namespace())
            if not memory:
                return f"Error: Memory at '{full_uri}' not found."

            current_content = memory.get("content", "")
            content = current_content + append

        if content is None and priority is None and disclosure is None and lifecycle_status is None:
            return (
                f"Error: No update fields provided for '{full_uri}'. "
                f"Use replace mode (old + new), append mode (append), "
                f"or metadata fields (priority/disclosure/lifecycle_status)."
            )

        result = await graph.update_memory(
            path=path,
            content=content,
            priority=priority,
            disclosure=disclosure,
            lifecycle_status=lifecycle_status,
            domain=domain,
            namespace=get_namespace(),
        )

        _record_rows(
            before_state=result.get("rows_before", {}),
            after_state=result.get("rows_after", {}),
        )

        message = f"Success: Memory at '{full_uri}' updated"
        if notices:
            message += "\n\n" + "\n\n".join(notices)
        return message

    except ValueError as e:
        return f"Error: {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"


@write_tool()
async def delete_memory(uri: str) -> str:
    '删除指定 URI 路径。删除前必须读取完整正文并确认确需删除；若存在不能安全删除的子节点，工具会返回处理提示。\n\n参数：uri — 要删除的记忆 URI。'
    graph = get_graph_service()

    try:
        domain, path = parse_uri(uri)
        full_uri = make_uri(domain, path)

        memory = await graph.get_memory_by_path(path, domain, namespace=get_namespace())
        if not memory:
            return f"Error: Memory at '{full_uri}' not found."

        result = await graph.remove_path(path, domain, namespace=get_namespace())
        rows_before = result.get("rows_before", {})

        _record_rows(
            before_state=rows_before,
            after_state={},
        )

        deleted_path_count = len(rows_before.get("paths", []))
        descendant_count = max(0, deleted_path_count - 1)
        msg = f"Success: Memory '{full_uri}' deleted."
        if descendant_count > 0:
            msg += f" (Recursively removed {descendant_count} descendant path(s))"

        return msg

    except ValueError as e:
        return f"Error: {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"


@write_tool()
async def add_alias(
    new_uri: str, target_uri: str, priority: int, disclosure: str
) -> str:
    '为已有记忆创建别名 URI；别名与原记忆共享同一份正文，不会复制内容。\n\n参数：new_uri — 新别名 URI；target_uri — 已有记忆 URI；priority、disclosure — 新别名自己的检索优先级和召回条件。'
    graph = get_graph_service()

    try:
        if priority < 0:
            return "Error: priority must be >= 0."

        new_domain, new_path = parse_uri(new_uri)
        target_domain, target_path = parse_uri(target_uri)

        result = await graph.add_path(
            new_path=new_path,
            target_path=target_path,
            new_domain=new_domain,
            target_domain=target_domain,
            priority=priority,
            disclosure=disclosure,
            namespace=get_namespace(),
        )

        _record_rows(
            before_state={},
            after_state=result.get("rows_after", {}),
        )

        msg = f"Success: Alias '{result['new_uri']}' now points to same memory as '{result['target_uri']}'"

        created_paths = result.get("rows_after", {}).get("paths", [])
        if len(created_paths) > 1:
            child_paths = [
                f"{p['domain']}://{p['path']}" 
                for p in created_paths 
                if f"{p['domain']}://{p['path']}" != result['new_uri']
            ]
            if child_paths:
                msg += f"\n\nAutomatically inherited aliases for {len(child_paths)} descendant(s):\n"
                for cp in child_paths[:10]:
                    msg += f"- {cp}\n"
                if len(child_paths) > 10:
                    msg += f"... and {len(child_paths) - 10} more.\n"

        node_uuid = result.get("node_uuid")
        if node_uuid:
            all_paths = await graph.get_paths_for_node(node_uuid, namespace=get_namespace())
            new_parent_dir = "/".join(new_path.split("/")[:-1])
            siblings = []
            for p in all_paths:
                if p["domain"] == new_domain:
                    p_parent = "/".join(p["path"].split("/")[:-1])
                    if p_parent == new_parent_dir:
                        siblings.append(f"'{p['uri']}'")
            
            if len(siblings) > 1:
                msg += (
                    f"\n\n⚠ DUPLICATE SIBLING WARNING: This node now appears {len(siblings)} times "
                    f"under the same parent directory: {', '.join(siblings)}.\n"
                    f"If you are renaming/moving, delete the old path now.\n"
                    f"If not, you probably created a redundant alias — consider removing one."
                )

        new_parent_uri = make_uri(new_domain, "/".join(new_path.split("/")[:-1]))
        msg += (
            f"\n\n[HOLD ON]: Do you know what '{new_parent_uri}' says? "
            f"If you haven't read it this session, read_memory() it first. "
            f"Then: does the aliased content conflict with ANY memory in your current context? "
            f"If yes, use memory-audit-belief-duel skill to resolve it before continuing."
        )

        return msg

    except ValueError as e:
        return f"Error: {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"


@write_tool()
async def manage_triggers(
    uri: str,
    add: Optional[List[str]] = None,
    remove: Optional[List[str]] = None,
) -> str:
    '为记忆节点添加或移除触发词；触发词应已出现在记忆库正文中。\n\n参数：uri — 指向目标记忆的 URI；add — 要添加的触发词；remove — 要移除的触发词。'
    graph = get_graph_service()
    glossary = get_glossary_service()

    try:
        domain, path = parse_uri(uri)
        full_uri = make_uri(domain, path)

        memory = await graph.get_memory_by_path(path, domain, namespace=get_namespace())
        if not memory:
            return f"Error: Memory at '{full_uri}' not found."

        node_uuid = memory["node_uuid"]

        if add and remove:
            add_set = {k.strip() for k in add if k.strip()}
            remove_set = {k.strip() for k in remove if k.strip()}
            overlap = add_set.intersection(remove_set)
            if overlap:
                return f"Error: Cannot add and remove the same keywords simultaneously: {', '.join(sorted(overlap))}"

        added = []
        skipped_add = []
        removed = []
        skipped_remove = []

        before_state = {"glossary_keywords": []}
        after_state = {"glossary_keywords": []}

        if add:
            for kw in add:
                kw = kw.strip()
                if not kw:
                    continue
                try:
                    result = await glossary.add_glossary_keyword(kw, node_uuid, namespace=get_namespace())
                    added.append(kw)
                    if "rows_before" in result:
                        before_state["glossary_keywords"].extend(result["rows_before"].get("glossary_keywords", []))
                    if "rows_after" in result:
                        after_state["glossary_keywords"].extend(result["rows_after"].get("glossary_keywords", []))
                except ValueError:
                    skipped_add.append(kw)

        if remove:
            for kw in remove:
                kw = kw.strip()
                if not kw:
                    continue
                result = await glossary.remove_glossary_keyword(kw, node_uuid, namespace=get_namespace())
                if result.get("success"):
                    removed.append(kw)
                    if "rows_before" in result:
                        before_state["glossary_keywords"].extend(result["rows_before"].get("glossary_keywords", []))
                    if "rows_after" in result:
                        after_state["glossary_keywords"].extend(result["rows_after"].get("glossary_keywords", []))
                else:
                    skipped_remove.append(kw)

        if added or removed:
            from db.snapshot import get_changeset_store
            get_changeset_store().record_many(before_state, after_state)

        current = await glossary.get_glossary_for_node(node_uuid, namespace=get_namespace())

        lines = [f"Keywords for '{full_uri}':"]
        if added:
            lines.append(f"  Added: {', '.join(added)}")
        if skipped_add:
            lines.append(f"  Already existed (skipped): {', '.join(skipped_add)}")
        if removed:
            lines.append(f"  Removed: {', '.join(removed)}")
        if skipped_remove:
            lines.append(f"  Not found (skipped): {', '.join(skipped_remove)}")
        if current:
            lines.append(f"  Current: [{', '.join(current)}]")
        else:
            lines.append("  Current: (none)")

        return "\n".join(lines)

    except ValueError as e:
        return f"Error: {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"


@mcp.tool()
async def search_memory(
    query: str, domain: Optional[str] = None, limit: int = 10, include_obsolete: bool = False,
    include_partial: bool = False, token_budget: Optional[int] = None, include_snippets: bool = False,
) -> str:
    '按路径和关键词全文检索，默认只返回严格匹配与策展短语别名的元数据和摘要，不返回正文片段。首轮保持 include_partial=false、include_snippets=false；此时不会自动返回 OR/PARTIAL 兜底候选。只有首轮无结果或已确认命中词与目标主题直接相关时，才可二次显式开启 include_partial=true。严格命中也只是词法候选，必须核对 URI、标题和主题。除非用户明确要求原文片段，不要开启 include_snippets；需要正文时使用 read_memory(uri)。\n\n参数：query — 搜索词；domain — 可选域过滤；limit — 返回数量，默认 10；include_obsolete — 是否包含 obsolete 记忆，默认 false；include_partial — 是否补充部分匹配，默认 false；token_budget — 摘要预算，默认使用服务端配置；include_snippets — 是否附带正文片段，默认 false。需要语义改写召回时可另行调用 semantic_search_memory。'
    search = get_search_indexer()

    try:
        valid = get_valid_domains()
        if domain is not None and domain not in valid:
            return f"Error: Unknown domain '{domain}'. Valid domains: {', '.join(valid)}"
        if token_budget is None:
            try:
                configured_budget = _cfg.get("search_summary_token_budget")
                token_budget = 1200 if configured_budget is None else max(0, int(configured_budget))
            except (TypeError, ValueError):
                token_budget = 1200
        else:
            token_budget = int(token_budget)
            if token_budget < 0 or token_budget > 20000:
                return "Error: token_budget must be between 0 and 20000."

        results = await search.search(
            query, limit, domain, namespace=get_namespace(),
            include_obsolete=include_obsolete, include_partial=include_partial,
        )
        if not results:
            scope = f"in '{domain}'" if domain else "across all domains"
            return f"No matching memories found {scope}."

        lines = [f"Found {len(results)} matches for '{query}':", ""]
        used_summary_tokens = 0
        for item in results:
            uri = item.get("uri", make_uri(item.get("domain", DEFAULT_DOMAIN), item["path"]))
            lines.append(f"- {uri}")
            is_partial_fallback = item.get("match_type") == "partial" and not include_partial
            if item.get("match_type") == "partial":
                lines.append(
                    f"  Match: PARTIAL ({item.get('match_coverage', 0):.0%}; "
                    f"matched: {', '.join(item.get('matched_terms', []))})"
                )
            elif item.get("match_type") == "strict":
                lines.append("  Match: STRICT (all query terms)")
            lines.append(f"  Priority: {item['priority']}")
            if item.get("disclosure") and not is_partial_fallback:
                lines.append(f"  Disclosure: {item['disclosure']}")

            summary = item.get("summary")
            summary_status = item.get("summary_status", "MISSING")
            if is_partial_fallback:
                # Weak OR fallback candidates should not consume the summary
                # budget by default. The caller can explicitly request them.
                lines.append("  Summary [OMITTED]: PARTIAL fallback; verify direct relevance before expanding.")
            elif summary:
                required = _estimate_context_tokens(summary)
                remaining = max(0, token_budget - used_summary_tokens)
                if required <= remaining:
                    lines.append(f"  Summary [VALID]: {summary}")
                    used_summary_tokens += required
                elif remaining > 0:
                    delivered = _truncate_utf8_to_token_budget(summary, remaining)
                    lines.append(f"  Summary [TRUNCATED]: {delivered}... (summary budget reached)")
                    used_summary_tokens = token_budget
                else:
                    lines.append("  Summary [OMITTED]: summary token budget reached.")
            else:
                lines.append(f"  Summary [{summary_status}]: (no summary; body was not expanded)")

            if include_snippets and item.get("snippet"):
                lines.append(f"  Body snippet: {item['snippet']}")
            if item.get("expandable") and not is_partial_fallback:
                lines.append(f"  Full content: read_memory(\"{uri}\")")
            elif is_partial_fallback:
                lines.append("  Expand only after confirming this URI is directly relevant.")
            for alias in item.get("aliases", []):
                lines.append(f"  Alias: {alias['uri']} (Priority: {alias['priority']})")
                if alias.get("disclosure"):
                    lines.append(f"    Disclosure: {alias['disclosure']}")
            lines.append("")

        lines.append(f"Summary budget: {used_summary_tokens}/{token_budget} estimated tokens.")
        if not include_snippets:
            lines.append("Body snippets omitted; use include_snippets=true when needed.")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
async def semantic_search_memory(
    query: str, domain: Optional[str] = None, limit: int = 10,
) -> str:
    '按语义相似度检索候选记忆。结果只是近邻候选，不代表相关性已确认；使用前应读取正文核实。\n\n参数：query — 自然语言问题或改写表达；domain — 可选域过滤；limit — 候选数量，范围 1–50，默认 10。'
    try:
        if domain is not None and domain not in get_valid_domains():
            return f"Error: Unknown domain '{domain}'. Valid domains: {', '.join(get_valid_domains())}"
        results = await search_semantic_memories(
            query, limit=limit, namespace=get_namespace(), domain=domain
        )
        if not results:
            return "No semantic candidates found. This does not prove that no related memory exists."
        lines = [
            f"Semantic candidates for: {query}",
            "These are nearest-neighbor candidates, not verified relevance judgments.",
            "Read a candidate with read_memory(uri) before using its content.",
            "",
        ]
        for rank, item in enumerate(results, 1):
            lines.append(
                f"{rank}. {item['uri']}\n"
                f"   Candidate distance: {item['distance']:.6f} (lower is nearer; not a confidence score)\n"
                f"   Domain: {item.get('domain') or '(none)'} | Lifecycle: {item.get('lifecycle_status') or 'unspecified'}"
            )
        return "\n".join(lines)
    except Exception as exc:
        return f"Semantic search unavailable: {type(exc).__name__}: {exc}"


@mcp.tool()
def diagnose_memory_backend() -> str:
    '检查当前 MCP 进程对记忆 SQLite 数据库的读写能力；写入测试会回滚，不修改记忆数据。'
    import json
    return json.dumps(diagnose_memory_database(), ensure_ascii=False)


@mcp.tool()
async def sync_semantic_index() -> str:
    '增量同步语义索引。可能调用配置的 Embedding API；API 失败时保留原索引。'
    import json
    try:
        report = await sync_configured_vector_index()
        return json.dumps(report, ensure_ascii=False)
    except Exception as exc:
        return f"Semantic index sync failed: {type(exc).__name__}: {exc}"


# =============================================================================
# MCP Resources
# =============================================================================


if __name__ == "__main__":
    mcp.run()
