import html as html_module
import json
import re
from typing import Any
from urllib.parse import urlencode, urljoin

from bs4 import BeautifulSoup

from .base import (
    detect_notice_type,
    normalize_text,
    page_number_from_url,
    pagination_page_numbers,
)
from .types import ParsedNotice, ParsedPage

MOJIBAKE_MARKERS = ("ط§", "ط±", "ظ…", "غŒ", "ع©", "ظ‡", "ط´")


def repair_setad_text(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: repair_setad_text(item) for key, item in value.items()}
    if isinstance(value, list):
        return [repair_setad_text(item) for item in value]
    if not isinstance(value, str) or not any(marker in value for marker in MOJIBAKE_MARKERS):
        return value
    try:
        return value.encode("cp1256").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


def _organization_name(row: dict[str, Any]) -> str:
    organization = row.get("organization")
    if isinstance(organization, dict):
        return normalize_text(organization.get("name"))
    return normalize_text(organization)


class SetadEtendParser:
    def __init__(self, base_url: str, declared_type: str):
        self.base_url = base_url
        self.declared_type = declared_type

    def parse_list(self, payload_text: str, page_url: str) -> ParsedPage:
        try:
            payload = repair_setad_text(json.loads(payload_text))
        except json.JSONDecodeError as exc:
            raise ValueError("SETAD eTender response is not valid JSON.") from exc

        rows = payload.get("gridModel") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise ValueError("SETAD eTender response does not contain gridModel rows.")

        notices: list[ParsedNotice] = []
        warnings: list[str] = []
        for position, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                warnings.append(f"row-{position}: invalid row payload")
                continue

            source_record_id = normalize_text(row.get("id") or row.get("number"))
            notice_number = normalize_text(row.get("number") or row.get("identificationCode"))
            title = normalize_text(row.get("title") or row.get("domainsDescription"))
            if not source_record_id or not title:
                warnings.append(f"row-{position}: missing source id or title")
                continue

            employer = _organization_name(row)
            province = normalize_text(row.get("operationProvinceName"))
            city = normalize_text(row.get("operationCityName"))
            published_raw = normalize_text(row.get("publicNotificationDate"))
            deadline_raw = normalize_text(
                row.get("proposalDeadlineDate")
                or row.get("inquiryDeadlineDate")
                or row.get("evaluationDeadlineDate")
                or row.get("documentsDeadlineDate")
            )
            summary = normalize_text(row.get("domainsDescription"))
            detected, resolution_status = detect_notice_type(
                " ".join(filter(None, [title, normalize_text(row.get("typeName"))])),
                self.declared_type,
            )

            metadata = {
                "setad_channel": "etend",
                "internal_id": row.get("id"),
                "public_number": notice_number,
                "tender_type": normalize_text(row.get("type")),
                "tender_type_name": normalize_text(row.get("typeName")),
                "city": city,
                "document_deadline_raw": normalize_text(row.get("documentsDeadlineDate")),
                "proposal_deadline_raw": normalize_text(row.get("proposalDeadlineDate")),
                "evaluation_deadline_raw": normalize_text(row.get("evaluationDeadlineDate")),
                "opening_date_raw": normalize_text(row.get("openingDate")),
                "allowed_contractor": bool(row.get("allowedContractor")),
                "allowed_consultation": bool(row.get("allowedConsultation")),
                "allowed_commodity": bool(row.get("allowedCommodity")),
                "allowed_services": bool(row.get("allowedServices")),
            }
            notices.append(
                ParsedNotice(
                    source_record_id=source_record_id,
                    source_url=page_url,
                    detail_url="",
                    source_declared_type=self.declared_type,
                    content_detected_type=detected,
                    type_resolution_status=resolution_status,
                    title=title,
                    employer=employer,
                    province=province,
                    published_raw=published_raw,
                    deadline_raw=deadline_raw,
                    summary=summary,
                    description=summary,
                    notice_number=notice_number,
                    detail_status="access_limited",
                    position=position,
                    metadata=metadata,
                    raw_payload=row,
                )
            )

        current_page = int(payload.get("page") or 1) if isinstance(payload, dict) else 1
        total_pages = int(payload.get("total") or 0) if isinstance(payload, dict) else 0
        next_page_urls = []
        if current_page < total_pages:
            next_page_urls.append(f"{page_url.split('?')[0]}?page={current_page + 1}")
        if not notices:
            warnings.append("no_notice_rows_found")
        end_of_results = total_pages == 0 or current_page >= total_pages
        return ParsedPage(
            notices=notices,
            next_page_urls=next_page_urls,
            warnings=warnings,
            reported_current_page=current_page,
            reported_total_pages=total_pages,
            end_of_results=end_of_results,
            diagnostics={
                "payload_records": payload.get("records") if isinstance(payload, dict) else None,
                "grid_rows": len(rows),
            },
        )

    @staticmethod
    def parse_detail(html: str) -> dict:
        return {"detail_status": "access_limited"}


class SetadEprocParser:
    TABLE_SELECTOR = "table#aList"
    DETAIL_ARGS_RE = re.compile(
        r"showPurchaseNeed\(\s*(?P<req_id>\d+)\s*,\s*(?P<domain_type>\d+)\s*,\s*(?P<need_id>\d+)\s*\)"
    )

    def __init__(self, base_url: str, declared_type: str):
        self.base_url = base_url
        self.declared_type = declared_type

    def parse_list(self, html: str, page_url: str) -> ParsedPage:
        soup = BeautifulSoup(html, "html.parser")
        table = soup.select_one(self.TABLE_SELECTOR)
        current_page = page_number_from_url(page_url, default=1)
        if table is None:
            body = normalize_text(soup.get_text(" ", strip=True))
            security_challenge = "کد امنیتی" in body
            warnings = ["security_challenge" if security_challenge else "needs_table_not_found"]
            page_title = normalize_text(soup.title.get_text(" ", strip=True) if soup.title else "")
            return ParsedPage(
                notices=[],
                warnings=warnings,
                reported_current_page=current_page,
                end_of_results=False,
                diagnostics={
                    "page_title": page_title[:200],
                    "security_challenge": security_challenge,
                    "table_found": False,
                },
            )

        notices: list[ParsedNotice] = []
        warnings: list[str] = []
        rows = table.select("tbody tr") or table.select("tr")
        for position, row in enumerate(rows, start=1):
            cells = row.find_all("td", recursive=False)
            if not cells:
                continue
            if len(cells) < 11:
                warnings.append(f"row-{position}: unexpected column count {len(cells)}")
                continue

            number_link = cells[1].select_one("a")
            source_record_id = normalize_text(
                number_link.get_text(" ", strip=True) if number_link else cells[1].get_text(" ", strip=True)
            )
            title = normalize_text(cells[2].get_text(" ", strip=True))
            if not source_record_id or not title:
                warnings.append(f"row-{position}: missing need number or title")
                continue

            onclick = normalize_text(number_link.get("onclick") if number_link else "")
            detail_url = ""
            match = self.DETAIL_ARGS_RE.search(onclick)
            detail_identifiers: dict[str, str] = {}
            if match:
                detail_identifiers = match.groupdict()
                query = urlencode(
                    {
                        "reqId": detail_identifiers["req_id"],
                        "domainType": detail_identifiers["domain_type"],
                        "needId": detail_identifiers["need_id"],
                    }
                )
                detail_url = urljoin(page_url, f"needDetailsInfoModal-load.do?{query}")

            employer = normalize_text(cells[3].get_text(" ", strip=True))
            province = normalize_text(cells[4].get_text(" ", strip=True))
            need_type = normalize_text(cells[5].get_text(" ", strip=True))
            category = normalize_text(cells[6].get_text(" ", strip=True))
            goods_group = normalize_text(cells[7].get_text(" ", strip=True))
            service_group = normalize_text(cells[8].get_text(" ", strip=True))
            published_raw = normalize_text(cells[9].get_text(" ", strip=True))
            deadline_raw = normalize_text(cells[10].get_text(" ", strip=True))
            detected, resolution_status = detect_notice_type(
                " ".join(filter(None, [title, need_type])),
                self.declared_type,
            )
            summary = " | ".join(filter(None, [need_type, category, goods_group, service_group]))
            raw_payload = {
                "need_number": source_record_id,
                "title": title,
                "employer": employer,
                "province": province,
                "need_type": need_type,
                "category": category,
                "goods_group": goods_group,
                "service_group": service_group,
                "published_raw": published_raw,
                "deadline_raw": deadline_raw,
                **detail_identifiers,
            }
            notices.append(
                ParsedNotice(
                    source_record_id=source_record_id,
                    source_url=page_url,
                    detail_url=detail_url,
                    source_declared_type=self.declared_type,
                    content_detected_type=detected,
                    type_resolution_status=resolution_status,
                    title=title,
                    employer=employer,
                    province=province,
                    published_raw=published_raw,
                    deadline_raw=deadline_raw,
                    summary=summary,
                    description=title,
                    notice_number=source_record_id,
                    detail_status="not_requested",
                    position=position,
                    metadata={
                        "setad_channel": "eproc",
                        "need_type": need_type,
                        "category": category,
                        "goods_group": goods_group,
                        "service_group": service_group,
                        "relative_deadline": deadline_raw,
                        **detail_identifiers,
                    },
                    raw_payload=raw_payload,
                )
            )

        next_page_urls: list[str] = []
        seen: set[str] = set()
        for anchor in soup.select('a[href*="needs.do"][href*="pager=true"]'):
            href = html_module.unescape(anchor.get("href") or "")
            url = urljoin(page_url, href)
            if url not in seen:
                seen.add(url)
                next_page_urls.append(url)
        if not notices:
            warnings.append("no_notice_rows_found")

        page_numbers = pagination_page_numbers([page_url, *next_page_urls])
        total_pages = max(page_numbers) if page_numbers else None
        end_of_results: bool | None = None
        if total_pages is not None and current_page is not None:
            if notices:
                end_of_results = current_page >= total_pages
            elif current_page > total_pages:
                end_of_results = True
            else:
                end_of_results = False

        page_title = normalize_text(soup.title.get_text(" ", strip=True) if soup.title else "")
        return ParsedPage(
            notices=notices,
            next_page_urls=next_page_urls,
            warnings=warnings,
            reported_current_page=current_page,
            reported_total_pages=total_pages,
            end_of_results=end_of_results,
            diagnostics={
                "page_title": page_title[:200],
                "table_found": True,
                "matched_rows": len(rows),
            },
        )

    @staticmethod
    def parse_detail(html: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")
        body = normalize_text(soup.get_text(" ", strip=True))
        if "کد امنیتی" in body:
            return {"detail_status": "security_challenge"}
        return {"detail_status": "access_limited"}
