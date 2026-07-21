from bs4 import BeautifulSoup

from .base import (
    absolute_url,
    canonicalize_hezareh_url,
    detect_notice_type,
    first_date,
    first_numeric,
    normalize_text,
)
from .types import ParsedNotice, ParsedPage


class HezarehParser:
    row_selector = "div.table-1 table.table.table-hover tbody tr"

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
            source_status = normalize_text(cells[3].get_text(" ", strip=True))
            deadline_raw = first_date(cells[4].get_text(" ", strip=True))
            image_sources = [normalize_text(img.get("src")) for img in row.select("img[src]")]
            has_documents = bool(cells[5].select_one('a[href*="/services/ntcdoc"]'))
            has_active_deadline = bool(cells[6].select_one(".fa-hourglass-2")) or "مهلت دارد" in normalize_text(cells[6].get("data-title"))
            is_special = any("special-notice" in source for source in image_sources)
            detected, resolution_status = detect_notice_type(title, self.declared_type)
            raw_payload = {
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
                    deadline_raw=deadline_raw,
                    position=position,
                    metadata={
                        "source_status": source_status,
                        "is_new_on_source": source_status == "جدید",
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

        if not notices and self._is_security_challenge(soup):
            warnings.append("security_challenge")
        elif not notices:
            warnings.append("no_notice_rows_found")
        return ParsedPage(notices=notices, next_page_urls=next_page_urls, warnings=warnings)

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
