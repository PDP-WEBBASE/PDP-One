from server_core import mcp
from route_diagnostics_tools import register_route_diagnostics_tools

register_route_diagnostics_tools(mcp)

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
