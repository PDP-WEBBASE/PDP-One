from typing import Any, Awaitable, Callable

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

ApiCallable = Callable[..., Awaitable[Any]]


def register_interaction_tools(mcp: FastMCP, api: ApiCallable) -> None:
    @mcp.tool(
        description=(
            "Read the runtime PDP One interaction capability registry. Use this before claiming that a procurement read or write action is supported."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False, idempotentHint=True),
    )
    async def get_pdp_one_interaction_capabilities() -> dict:
        return await api("GET", "procurement/interaction/capabilities/")

    @mcp.tool(
        description=(
            "Query real PDP One tenders/inquiries with server-side workflow filters and bounded pagination. "
            "This is read-only and does not require PDPONE WEB. Use exact ISO-8601 deadline bounds for questions such as items due today."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False, idempotentHint=True),
    )
    async def query_procurement_notices(
        notice_type: str = "",
        workflow: str = "recent",
        search: str = "",
        province: str = "",
        source_name: str = "",
        responsible: str = "",
        deadline_from: str = "",
        deadline_to: str = "",
        published_from: str = "",
        published_to: str = "",
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        if notice_type and notice_type not in {"tender", "inquiry"}:
            raise ValueError("notice_type must be tender or inquiry")
        if workflow not in {"recent", "recommended", "selected", "submitted", "results"}:
            raise ValueError("unsupported procurement workflow")
        params = {
            "workflow": workflow,
            "page": max(1, int(page)),
            "page_size": min(max(1, int(page_size)), 100),
        }
        optional = {
            "notice_type": notice_type,
            "search": search,
            "province": province,
            "source_name": source_name,
            "responsible": responsible,
            "deadline_from": deadline_from,
            "deadline_to": deadline_to,
            "published_from": published_from,
            "published_to": published_to,
        }
        params.update({key: value for key, value in optional.items() if str(value or "").strip()})
        return await api("GET", "procurement/interaction/query/notices/", params=params)

    @mcp.tool(
        description="Read the lightweight procurement domain revision without loading notice data.",
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False, idempotentHint=True),
    )
    async def get_procurement_domain_revision() -> dict:
        return await api("GET", "procurement/interaction/revision/")

    @mcp.tool(
        description=(
            "Read bounded procurement change-journal entries newer than a known revision. "
            "Use this for targeted synchronization; it never changes business data."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False, idempotentHint=True),
    )
    async def get_procurement_changes(since: int, limit: int = 100) -> dict:
        return await api(
            "GET",
            "procurement/interaction/changes/",
            params={"since": max(0, int(since)), "limit": min(max(1, int(limit)), 500)},
        )

    @mcp.tool(
        description=(
            "Arm PDPONE WEB write mode for this authenticated conversation scope. "
            "Call this ONLY after the user explicitly enters PDPONE WEB. The returned lease is short-lived and required for business mutations."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=False),
    )
    async def arm_pdpone_web_write(conversation_key: str, ttl_minutes: int = 60) -> dict:
        return await api(
            "POST",
            "procurement/interaction/write/arm/",
            json={"conversation_key": conversation_key, "ttl_minutes": min(max(5, int(ttl_minutes)), 120)},
        )

    @mcp.tool(
        description=(
            "Disarm PDPONE WEB write mode for this conversation. Call when the user enters PDPONE WEB END or write access is no longer needed."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=True),
    )
    async def disarm_pdpone_web_write(conversation_key: str) -> dict:
        return await api(
            "POST",
            "procurement/interaction/write/disarm/",
            json={"conversation_key": conversation_key},
        )

    @mcp.tool(
        description=(
            "Create a server-side pending select action when the user's intended notice is ambiguous. "
            "Requires PDPONE WEB but performs no business mutation. Present the returned candidates to the user and wait for explicit confirmation."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=False),
    )
    async def prepare_procurement_select_confirmation(
        candidate_notice_ids: list[str],
        conversation_key: str,
        lease_id: str,
        requested_text: str = "",
    ) -> dict:
        return await api(
            "POST",
            "procurement/interaction/pending/select/",
            json={
                "candidate_notice_ids": candidate_notice_ids,
                "conversation_key": conversation_key,
                "lease_id": lease_id,
                "requested_text": requested_text,
            },
        )

    @mcp.tool(
        description=(
            "Consume one pending ambiguous select action after the user explicitly confirms one returned candidate. "
            "Requires the same PDPONE WEB lease and conversation, validates candidate membership, and verifies the write after execution."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=True),
    )
    async def confirm_procurement_select(
        pending_action_id: str,
        notice_id: str,
        conversation_key: str,
        lease_id: str,
    ) -> dict:
        result = await api(
            "POST",
            "procurement/interaction/pending/select/confirm/",
            json={
                "pending_action_id": pending_action_id,
                "notice_id": notice_id,
                "conversation_key": conversation_key,
                "lease_id": lease_id,
            },
        )
        if not result.get("verified"):
            raise RuntimeError("PDP One confirmed write did not pass read-after-write verification")
        return result

    @mcp.tool(
        description=(
            "Select one exact procurement notice by UUID. Requires an active PDPONE WEB server-side lease for the same conversation. "
            "Do not guess notice identity: if the user's target is ambiguous, use prepare_procurement_select_confirmation and ask the user first. "
            "The command is idempotent, audited, emits a change revision/outbox event, and reports read-after-write verification."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False, idempotentHint=True),
    )
    async def select_procurement_notice(
        notice_id: str,
        conversation_key: str,
        lease_id: str,
    ) -> dict:
        result = await api(
            "POST",
            "procurement/interaction/commands/select-notice/",
            json={
                "notice_id": notice_id,
                "conversation_key": conversation_key,
                "lease_id": lease_id,
            },
        )
        if not result.get("verified"):
            raise RuntimeError("PDP One write completed without successful read-after-write verification")
        return result
