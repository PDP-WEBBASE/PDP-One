from starlette.requests import Request
from starlette.responses import JSONResponse


def register_health_route(mcp) -> None:
    @mcp.custom_route("/healthz", methods=["GET"], include_in_schema=False)
    async def mcp_healthz(_request: Request) -> JSONResponse:
        return JSONResponse(
            {
                "status": "ok",
                "service": "pdp-one-mcp",
                "transport": "streamable-http",
            }
        )
