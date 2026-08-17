from automation_tools import register_automation_tools
from health_tools import register_health_route
from procurement_tools import register_procurement_tools
from server import api, mcp

register_procurement_tools(mcp, api)
register_automation_tools(mcp, api)
register_health_route(mcp)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
