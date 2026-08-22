from route_health_probe import heartbeat_snapshot, probe_mcp_route_chain


async def test_route_probe_is_non_destructive():
    result = await probe_mcp_route_chain()
    assert result.checks["session_handshake"] == "not_attempted"


def test_heartbeat_does_not_create_session_or_database_load():
    snapshot = heartbeat_snapshot()
    assert snapshot["creates_session"] is False
    assert snapshot["database_access"] is False
