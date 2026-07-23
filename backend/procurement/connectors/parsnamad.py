import json
import math
from typing import Any

from bs4 import BeautifulSoup

from .base import (
    absolute_url,
    detect_notice_type,
    normalize_text,
    page_number_from_url,
    pagination_page_numbers,
)
from .types import ParsedNotice, ParsedPage


class ParsNamadParser:
    row_selector = "tbody#search_result_list > tr.text-center"

    def __init__(self, base_url: str, declared_type: str):
        self.base_url = base_url
        self.declared_type = declared_type

    def parse_list(self, html: str, page_url: str) -> ParsedPage:
        soup = BeautifulSoup(html, "html.parser")
        notices: list[ParsedNotice] = []
        warnings: list[str] = []
        detected_counts = {"tender": 0, "inquiry": 0}

        for position, row in enumerate(soup.select(self.row_selector), start=1):
            cells = row.find_all(["td", "th"], recursive=False)
            if len(cells) < 7:
                warnings.append(f"row-{position}: unexpected column count {len(cells)}")
                continue
            title_link = cells[2].select_one("a[href]")
            code_link = cells[3].select_one("a[href]")
            title = normalize_text(
                title_link.get_text(" ", strip=True)
                if title_link
                else cells[2].get_text(" ", strip=True)
            )
            source_record_id = normalize_text(
                code_link.get_text(" ", strip=True)
                if code_link
                else cells[3].get_text(" ", strip=True)
            )
            if not source_record_id or not title:
                warnings.append(f"row-{position}: missing source id or title")
                continue
            detail_href = (
                title_link.get("href")
                if title_link
                else (code_link.get("href") if code_link else "")
            )
            detail_url = absolute_url(self.base_url, detail_href)
            published_raw = normalize_text(cells[4].get_text(" ", strip=True))
            province = normalize_text(cells[6].get_text(" ", strip=True))
            image_sources = [
                normalize_text(img.get("src")) for img in cells[5].select("img[src]")
            ]
            is_new = any("new-large" in source for source in image_sources)
            is_old = any("old-large" in source for source in image_sources)
            is_special = any(
                "special-large" in source and "special-dis" not in source
                for source in image_sources
            )
            has_ladder = any(
                "ladder-large" in source and "ladder-dis" not in source
                for source in image_sources
            )
            detected, resolution_status = detect_notice_type(title, self.declared_type)
            if detected in detected_counts:
                detected_counts[detected] += 1
            raw_payload = {
                "published_raw": published_raw,
                "province_raw": province,
                "icons": image_sources,
                "is_new": is_new,
                "is_old": is_old,
                "is_special": is_special,
                "has_ladder": has_ladder,
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
                    province=province,
                    published_raw=published_raw,
                    position=position,
                    metadata={
                        "is_new_on_source": is_new,
                        "is_old_on_source": is_old,
                        "is_special_on_source": is_special,
                        "has_ladder": has_ladder,
                    },
                    raw_payload=raw_payload,
                )
            )

        if notices:
            opposite_type = "inquiry" if self.declared_type == "tender" else "tender"
            mismatch_count = detected_counts[opposite_type]
            mismatch_limit = max(3, math.ceil(len(notices) * 0.8))
            if mismatch_count >= mismatch_limit:
                raise ValueError(
                    "Pars Namad page type mismatch: "
                    f"connector={self.declared_type}, detected={opposite_type}, "
                    f"mismatch_count={mismatch_count}, total={len(notices)}"
                )

        next_page_urls = []
        seen = set()
        for anchor in soup.select("ul.pagination a[href], a.page-link[href]"):
            url = absolute_url(self.base_url, anchor.get("href"))
            if url not in seen:
                next_page_urls.append(url)
                seen.add(url)

        if not notices:
            warnings.append("no_notice_rows_found")

        current_page = page_number_from_url(page_url, default=1)
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
                "matched_rows": len(soup.select(self.row_selector)),
                "detected_type_counts": detected_counts,
            },
        )

    def parse_detail(self, html: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")
        event = self._event_json_ld(soup)
        if not event:
            return {"detail_status": "failed"}
        address = (
            event.get("location", {}).get("address", {})
            if isinstance(event.get("location"), dict)
            else {}
        )
        province = normalize_text(
            address.get("streetAddrees") or address.get("streetAddress") or ""
        )
        if province.endswith(", ایران"):
            province = province[:-7].strip()
        title = normalize_text(event.get("name"))
        detected, resolution_status = detect_notice_type(
            title + " " + normalize_text(event.get("description")),
            self.declared_type,
        )
        return {
            "detail_status": "enriched",
            "title": title,
            "description": normalize_text(event.get("description")),
            "published_raw": normalize_text(event.get("publishDate")),
            "start_date_raw": normalize_text(event.get("startDate")),
            "deadline_raw": normalize_text(event.get("endDate")),
            "province": province,
            "source_record_id": normalize_text(event.get("mpn") or event.get("sku")),
            "detail_url": normalize_text(event.get("url")),
            "event_status": normalize_text(event.get("eventStatus")),
            "content_detected_type": detected,
            "type_resolution_status": resolution_status,
            "json_ld": event,
        }

    @staticmethod
    def _event_json_ld(soup: BeautifulSoup) -> dict[str, Any] | None:
        for script in soup.select('script[type="application/ld+json"]'):
            text = script.string or script.get_text()
            try:
                payload = json.loads(text)
            except (TypeError, json.JSONDecodeError):
                continue
            candidates = payload if isinstance(payload, list) else [payload]
            for candidate in candidates:
                if isinstance(candidate, dict) and candidate.get("@type") == "Event":
                    return candidate
        return None
