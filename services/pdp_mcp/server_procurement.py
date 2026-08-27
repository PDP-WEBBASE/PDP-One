import promotion_control_v3_hardening  # noqa: F401 - applies bounded V3 runtime hardening before tool registration
import promotion_control_v3_short_lane  # noqa: F401 - applies DEC-051 short critical lane semantics

from automation_tools import register_automation_tools
from health_tools import register_health_route
from procurement_tools import register_procurement_tools
from server import api, mcp

register_procurement_tools(mcp, api)
register_automation_tools(mcp, api)
register_health_route(mcp)

# Keep the v1 Streamable HTTP session state, but make each POST response a
# short-lived application/json response instead of a request-scoped SSE
# stream. In mcp==1.28.1 the session manager is created lazily by
# streamable_http_app(), so changing this setting before run() is effective.
# Do not enable stateless_http here; the guarded PDP One transport remains
# stateful and the stable v1 line has known disconnect edge cases in stateless
# mode.
mcp.settings.json_response = True
mcp.settings.stateless_http = False


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
