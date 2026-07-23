from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class ParsedNotice:
    source_record_id: str
    source_url: str
    detail_url: str
    source_declared_type: str
    content_detected_type: str | None
    type_resolution_status: str
    title: str
    employer: str = ""
    province: str = ""
    published_raw: str = ""
    deadline_raw: str = ""
    summary: str = ""
    description: str = ""
    conditions: str = ""
    notice_number: str = ""
    contact_text: str = ""
    detail_status: str = "not_requested"
    position: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def as_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ParsedPage:
    notices: list[ParsedNotice]
    next_page_urls: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    reported_current_page: int | None = None
    reported_total_pages: int | None = None
    end_of_results: bool | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)
