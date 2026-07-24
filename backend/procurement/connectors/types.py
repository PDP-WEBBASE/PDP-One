from dataclasses import asdict, dataclass, field
from typing import Any

from procurement.http import SourceFetchError


class PageContentMismatchError(SourceFetchError):
    """The page is reachable, but its dominant content belongs to another connector type."""

    def __init__(
        self,
        *,
        expected_type: str,
        detected_type: str,
        mismatch_count: int,
        total_count: int,
        source_name: str = "",
    ):
        self.expected_type = expected_type
        self.detected_type = detected_type
        self.mismatch_count = mismatch_count
        self.total_count = total_count
        self.source_name = source_name
        message = (
            "نوع غالب محتوای صفحه با Connector انتخاب‌شده سازگار نیست؛ "
            f"نوع مورد انتظار {expected_type} و نوع تشخیص‌داده‌شده {detected_type} است."
        )
        super().__init__(
            message,
            category="validation",
            retryable=False,
        )

    def as_details(self) -> dict[str, Any]:
        return {
            "expected_type": self.expected_type,
            "detected_type": self.detected_type,
            "mismatch_count": self.mismatch_count,
            "total_count": self.total_count,
            "source_name": self.source_name,
        }


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
