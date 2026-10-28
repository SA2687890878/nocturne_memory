import pytest
from sqlalchemy import func, select

from db import get_db_manager
from db.models import Memory, Node
from db.snapshot import get_changeset_store


async def seed(graph, status="active"):
    return await graph.create_memory("", "Original content", 2, title="life", disclosure="When testing lifecycle", lifecycle_status=status)


async def access_time(node_uuid):
    async with get_db_manager().session() as session:
        return await session.scalar(select(Node.last_accessed_at).where(Node.uuid == node_uuid))


@pytest.mark.parametrize("status", ["active", "completed", "obsolete", "unspecified"])
async def test_status_only_write_shared_by_alias_without_new_version(graph_service, status):
    created = await seed(graph_service)
    await graph_service.add_path("mirror", "life", priority=3, disclosure="When mirroring")
    result = await graph_service.update_memory("mirror", lifecycle_status=status)
    original = await graph_service.get_memory_by_path("life")
    alias = await graph_service.get_memory_by_path("mirror")
    assert original["lifecycle_status"] == alias["lifecycle_status"] == status
    assert result["old_memory_id"] == result["new_memory_id"] == created["id"]
    async with get_db_manager().session() as session:
        assert await session.scalar(select(func.count()).select_from(Memory).where(Memory.node_uuid == created["node_uuid"])) == 1
    if status == "active":
        assert result["rows_before"] == result["rows_after"] == {}


@pytest.mark.parametrize("status", [None, "", "invalid"])
async def test_graph_create_rejects_invalid_status_without_creating_node(graph_service, status):
    with pytest.raises(ValueError, match="lifecycle_status"):
        await seed(graph_service, status)
    assert await graph_service.get_memory_by_path("life") is None


async def test_mcp_create_default_and_explicit_null(mcp_module, graph_service):
    result = await mcp_module.create_memory("core://", "Default", 2, disclosure="When testing", title="default")
    assert "Success" in result
    assert (await graph_service.get_memory_by_path("default"))["lifecycle_status"] == "unspecified"
    invalid = await mcp_module.create_memory("core://", "Null", 2, disclosure="When testing", title="invalid", lifecycle_status=None)
    assert "Error" in invalid
    assert await graph_service.get_memory_by_path("invalid") is None


async def test_rest_create_default_and_null(api_client, graph_service):
    body = {"parent_path": "", "content": "Default", "priority": 2, "disclosure": "When testing", "title": "default"}
    response = await api_client.post("/browse/node", json=body)
    assert response.status_code == 200
    assert (await graph_service.get_memory_by_path("default"))["lifecycle_status"] == "unspecified"
    body.update(title="invalid", lifecycle_status=None)
    assert (await api_client.post("/browse/node", json=body)).status_code == 422
    assert await graph_service.get_memory_by_path("invalid") is None


async def test_rest_status_nav_only_and_null_update(api_client, graph_service):
    created = await seed(graph_service)
    params = {"path": "life", "domain": "core"}
    updated = await api_client.put("/browse/node", params=params, json={"lifecycle_status": "completed"})
    assert updated.status_code == 200
    assert updated.json()["memory_id"] == created["id"]
    view = await api_client.get("/browse/node", params={**params, "nav_only": True})
    assert view.json()["node"]["lifecycle_status"] == "completed"
    assert (await api_client.put("/browse/node", params=params, json={"priority": 3, "lifecycle_status": None})).status_code == 200
    assert (await graph_service.get_memory_by_path("life"))["lifecycle_status"] == "completed"
    assert (await api_client.put("/browse/node", params=params, json={"lifecycle_status": ""})).status_code == 422
    assert get_changeset_store().get_change_count() == 0


async def test_pure_state_diff_and_approve(api_client, graph_service, mcp_module):
    created = await seed(graph_service)
    assert "Success" in await mcp_module.update_memory("core://life", lifecycle_status="obsolete")
    group = created["node_uuid"]
    diff = (await api_client.get(f"/review/groups/{group}/diff")).json()
    assert diff["before_meta"]["lifecycle_status"] == "active"
    assert diff["current_meta"]["lifecycle_status"] == "obsolete"
    assert diff["before_content"] == diff["current_content"] == "Original content"
    assert diff["has_changes"] is True
    assert (await api_client.delete(f"/review/groups/{group}")).status_code == 200
    assert get_changeset_store().get_change_count() == 0
    assert (await graph_service.get_memory_by_path("life"))["lifecycle_status"] == "obsolete"


async def test_state_read_reset_is_zero_net_change(graph_service, mcp_module):
    created = await seed(graph_service)
    await mcp_module.update_memory("core://life", lifecycle_status="obsolete")
    await graph_service.log_access(created["node_uuid"], "")
    assert await access_time(created["node_uuid"]) is not None
    await mcp_module.update_memory("core://life", lifecycle_status="active")
    assert get_changeset_store().get_change_count() == 0


async def test_state_rollback_preserves_committed_access_time(api_client, graph_service, mcp_module):
    created = await seed(graph_service)
    await mcp_module.update_memory("core://life", lifecycle_status="obsolete")
    await graph_service.log_access(created["node_uuid"], "")
    accessed = await access_time(created["node_uuid"])
    response = await api_client.post(f"/review/groups/{created['node_uuid']}/rollback")
    assert response.json()["success"] is True
    assert (await graph_service.get_memory_by_path("life"))["lifecycle_status"] == "active"
    assert await access_time(created["node_uuid"]) == accessed
    assert get_changeset_store().get_change_count() == 0


async def test_human_status_conflict_keeps_whole_group(api_client, graph_service, mcp_module):
    created = await seed(graph_service)
    await mcp_module.update_memory("core://life", lifecycle_status="obsolete", append=" pending", priority=5)
    await graph_service.update_memory("life", lifecycle_status="completed")
    before = get_changeset_store().get_snapshot_view()
    response = await api_client.post(f"/review/groups/{created['node_uuid']}/rollback")
    assert response.json()["success"] is False
    assert "conflict" in response.json()["message"].lower()
    current = await graph_service.get_memory_by_path("life")
    assert current["lifecycle_status"] == "completed"
    assert current["content"] == "Original content pending"
    assert current["priority"] == 5
    assert get_changeset_store().get_snapshot_view() == before


async def test_already_restored_status_rolls_back_other_group_changes(api_client, graph_service, mcp_module):
    created = await seed(graph_service)
    await mcp_module.update_memory("core://life", lifecycle_status="obsolete", append=" pending")
    await graph_service.update_memory("life", lifecycle_status="active")
    response = await api_client.post(f"/review/groups/{created['node_uuid']}/rollback")
    assert response.json()["success"] is True
    assert (await graph_service.get_memory_by_path("life"))["content"] == "Original content"


async def test_content_version_restore_preserves_node_status(graph_service):
    created = await seed(graph_service)
    await graph_service.update_memory("life", content="New content", lifecycle_status="completed")
    await graph_service.rollback_to_memory(created["id"])
    current = await graph_service.get_memory_by_path("life")
    assert current["content"] == "Original content"
    assert current["lifecycle_status"] == "completed"


async def test_legacy_snapshot_without_status_does_not_restore_it(api_client, graph_service):
    created = await seed(graph_service, "completed")
    store = get_changeset_store()
    store.record("nodes", {"uuid": created["node_uuid"], "last_accessed_at": None}, {"uuid": created["node_uuid"], "last_accessed_at": None, "created_at": "changed"})
    response = await api_client.post(f"/review/groups/{created['node_uuid']}/rollback")
    assert response.json()["success"] is True
    assert (await graph_service.get_memory_by_path("life"))["lifecycle_status"] == "completed"


async def test_registered_tools_expose_lifecycle_contract(mcp_module):
    tools = {tool.name: tool.inputSchema for tool in await mcp_module.mcp.list_tools()}
    assert tools["create_memory"]["properties"]["lifecycle_status"]["default"] == "unspecified"
    assert tools["search_memory"]["properties"]["include_obsolete"]["default"] is False
    assert "lifecycle_status" in tools["update_memory"]["properties"]

@pytest.mark.parametrize("nav_only", [False, True])
async def test_browse_children_return_lifecycle_status(api_client, graph_service, nav_only):
    await seed(graph_service, "completed")
    response = await api_client.get("/browse/node", params={"path": "", "domain": "core", "nav_only": nav_only})
    assert response.status_code == 200
    child = next(child for child in response.json()["children"] if child["path"] == "life")
    assert child["lifecycle_status"] == "completed"


async def test_conditional_status_update_miss_retains_group(api_client, graph_service, mcp_module, monkeypatch):
    from types import SimpleNamespace
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql.dml import Update

    created = await seed(graph_service)
    await mcp_module.update_memory("core://life", lifecycle_status="obsolete", append=" pending")
    before = get_changeset_store().get_snapshot_view()
    execute = AsyncSession.execute

    async def lose_race(session, statement, *args, **kwargs):
        if isinstance(statement, Update) and statement.table.name == "nodes":
            return SimpleNamespace(rowcount=0)
        return await execute(session, statement, *args, **kwargs)

    monkeypatch.setattr(AsyncSession, "execute", lose_race)
    response = await api_client.post(f"/review/groups/{created['node_uuid']}/rollback")
    assert response.json()["success"] is False
    assert "concurrently" in response.json()["message"]
    assert get_changeset_store().get_snapshot_view() == before
    current = await graph_service.get_memory_by_path("life")
    assert current["lifecycle_status"] == "obsolete"
    assert current["content"] == "Original content pending"

