import re

from bs4 import BeautifulSoup

from .base import (
    absolute_url,
    canonicalize_hezareh_url,
    detect_notice_type,
    first_date,
    first_numeric,
    normalize_text,
    page_number_from_url,
    pagination_page_numbers,
)
from .types import ParsedNotice, ParsedPage


class HezarehParser:
    row_selector = "div.table-1 table.table.table-hover tbody tr"
    source_page_report_re = re.compile(r"صفحه\s*(\d+)\s*از\s*(\d+)", re.IGNORECASE)
    explicit_date_re = re.compile(r"(?:13|14|20)\d{2}[/-]\d{1,2}[/-]\d{1,2}")

    def __init__(self, base_url: str, declared_type: str):
        self.base_url = base_url
        self.declared_type = declared_type

    def parse_list(self, html: str, page_url: str) -> ParsedPage:
        soup = BeautifulSoup(html, "html.parser")
        notices: list[ParsedNotice] = []
        warnings: list[str] = []

        for position, row in enumerate(soup.select(self.row_selector), start=1):
            cells = row.find_all(["td", "th"], recursive=False)
            if len(cells) < 7:
                warnings.append(f"row-{position}: unexpected column count {len(cells)}")
                continue
            link = cells[1].select_one("a[href]")
            source_record_id = first_numeric(cells[0].get_text(" ", strip=True))
            title = normalize_text(link.get_text(" ", strip=True) if link else cells[1].get_text(" ", strip=True))
            if not source_record_id or not title:
                warnings.append(f"row-{position}: missing source id or title")
                continue
            detail_url = absolute_url(self.base_url, link.get("href") if link else "")
            province = normalize_text(cells[2].get_text(" ", strip=True))
            if province.startswith("استان "):
                province = province[6:].strip()

            insertion_raw = normalize_text(cells[3].get_text(" ", strip=True))
            published_raw = first_date(insertion_raw) if self.explicit_date_re.search(insertion_raw) else ""
            source_status = "" if published_raw else insertion_raw
            deadline_raw = first_date(cells[4].get_text(" ", strip=True))
            image_sources = [normalize_text(img.get("src")) for img in row.select("img[src]")]
            has_documents = bool(cells[5].select_one('a[href*="/services/ntcdoc"]'))
            has_active_deadline = bool(cells[6].select_one(".fa-hourglass-2")) or "مهلت دارد" in normalize_text(cells[6].get("data-title"))
            is_special = any("special-notice" in source for source in image_sources)
            detected, resolution_status = detect_notice_type(title, self.declared_type)
            raw_payload = {
                "insertion_raw": insertion_raw,
                "published_raw": published_raw,
                "source_status": source_status,
                "deadline_raw": deadline_raw,
                "province_raw": normalize_text(cells[2].get_text(" ", strip=True)),
                "is_special": is_special,
                "has_documents": has_documents,
                "has_active_deadline": has_active_deadline,
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
                    deadline_raw=deadline_raw,
                    position=position,
                    metadata={
                        "insertion_raw": insertion_raw,
                        "source_status": source_status,
                        "is_new_on_source": insertion_raw == "جدید",
                        "is_special_on_source": is_special,
                        "has_documents": has_documents,
                        "has_active_deadline": has_active_deadline,
                    },
                    raw_payload=raw_payload,
                )
            )

        next_page_urls = []
        seen = set()
        for anchor in soup.select("ul.pagination a[href]"):
            url = canonicalize_hezareh_url(absolute_url(self.base_url, anchor.get("href")))
            if url not in seen:
                next_page_urls.append(url)
                seen.add(url)

        security_challenge = self._is_security_challenge(soup)
        if not notices and security_challenge:
            warnings.append("security_challenge")
        elif not notices:
            warnings.append("no_notice_rows_found")

        url_current_page = page_number_from_url(page_url, default=1)
        page_numbers = pagination_page_numbers([page_url, *next_page_urls])
        visible_total_pages = max(page_numbers) if page_numbers else None
        source_report = self._source_page_report(soup)
        if source_report is not None:
            reported_current_page, total_pages = source_report
            total_pages_source = "source_report"
        else:
            reported_current_page = url_current_page
            total_pages = visible_total_pages
            total_pages_source = "visible_links" if visible_total_pages is not None else "unknown"

        end_of_results: bool | None = None
        if security_challenge:
            end_of_results = False
        elif source_report is not None and reported_current_page is not None:
            if notices:
                end_of_results = reported_current_page >= total_pages
            elif reported_current_page > total_pages:
                end_of_results = True
            else:
                end_of_results = False

        page_title = normalize_text(soup.title.get_text(" ", strip=True) if soup.title else "")
        return ParsedPage(
            notices=notices,
            next_page_urls=next_page_urls,
            warnings=warnings,
            reported_current_page=reported_current_page,
            reported_total_pages=total_pages,
            end_of_results=end_of_results,
            diagnostics={
                "page_title": page_title[:200],
                "matched_rows": len(soup.select(self.row_selector)),
                "security_challenge": security_challenge,
                "reported_total_pages_source": total_pages_source,
                "visible_pagination_max": visible_total_pages,
            },
        )

    def parse_detail(self, html: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")
        if self._is_security_challenge(soup):
            return {"detail_status": "security_challenge"}

        title_node = soup.select_one("h1.entry-title")
        return {
            "detail_status": "enriched",
            "title": normalize_text(title_node.get_text(" ", strip=True) if title_node else ""),
            "description": self._label_value(soup, ["شرح آگهی"]),
            "conditions": self._label_value(soup, ["شرایط آگهی"]),
            "employer": self._label_value(soup, ["برگزار کننده"]),
            "province": self._label_value(soup, ["منطقه"]).removeprefix("استان ").strip(),
            "published_raw": first_date(self._label_value(soup, ["تاريخ انتشار", "تاریخ انتشار"])),
            "document_deadline_raw": first_date(self._label_value(soup, ["مهلت دريافت", "مهلت دریافت"])),
            "deadline_raw": first_date(self._label_value(soup, ["مهلت ارسال"])),
            "opening_date_raw": first_date(self._label_value(soup, ["تاريخ بازگشايی", "تاریخ بازگشایی"])),
            "announcement_round": self._label_value(soup, ["نوبت اعلام"]),
            "notice_number": self._label_value(soup, ["شماره آگهی"]),
            "source_label": self._label_value(soup, ["منبع"]),
            "phone": self._label_value(soup, ["تلفن"]),
            "fax": self._label_value(soup, ["فکس"]),
            "email": self._label_value(soup, ["ایمیل"]),
            "website": self._label_value(soup, ["وب سایت", "وب‌سایت"]),
            "address": self._label_value(soup, ["آدرس"]),
        }

    @classmethod
    def _source_page_report(cls, soup: BeautifulSoup) -> tuple[int, int] | None:
        text = normalize_text(soup.get_text(" ", strip=True))
        match = cls.source_page_report_re.search(text)
        if not match:
            return None
        current_page = int(match.group(1))
        total_pages = int(match.group(2))
        if current_page < 1 or total_pages < 1 or current_page > total_pages:
            return None
        return current_page, total_pages

    @staticmethod
    def _is_security_challenge(soup: BeautifulSoup) -> bool:
        title = normalize_text(soup.title.get_text(" ", strip=True) if soup.title else "")
        body = normalize_text(soup.get_text(" ", strip=True))
        return "کد امنیتی" in title or "جهت دسترسی به صفحه مورد نظر، کد امنیتی" in body

    @staticmethod
    def _label_value(soup: BeautifulSoup, aliases: list[str]) -> str:
        normalized_aliases = {normalize_text(alias).rstrip(":") for alias in aliases}
        for label in soup.find_all(["b", "strong", "label"]):
            label_text = normalize_text(label.get_text(" ", strip=True)).rstrip(":")
            if label_text not in normalized_aliases:
                continue
            container = label.parent
            container_text = normalize_text(container.get_text(" ", strip=True))
            value = container_text
            for alias in normalized_aliases:
                if value.startswith(alias):
                    value = value[len(alias):].lstrip(" :")
                    break
            if value:
                return value
            sibling = container.find_next_sibling()
            if sibling is not None and not sibling.find(["b", "strong", "label"]):
                return normalize_text(sibling.get_text(" ", strip=True))
        return ""
