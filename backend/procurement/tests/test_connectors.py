import json

from django.test import SimpleTestCase

from procurement.connectors.hezareh import HezarehParser
from procurement.connectors.parsnamad import ParsNamadParser


class HezarehParserTests(SimpleTestCase):
    def test_list_parser_extracts_rows_and_canonicalizes_pagination(self):
        html = """
        <div class="table-1"><table class="table table-hover"><tbody>
          <tr>
            <td>10950416<img src="/content/img/special-notice.png"></td>
            <td><a href="/tenders/nid10950416">مناقصه خرید خدمات</a></td>
            <td>استان تهران</td><td>جدید</td><td>1405/05/05</td>
            <td><a href="/services/ntcdoc">اسناد</a></td>
            <td><i class="fa fa-hourglass-2"></i></td>
          </tr>
        </tbody></table></div>
        <ul class="pagination"><li><a href="/tenders/-!/page-2">2</a></li></ul>
        """
        parser = HezarehParser("https://www.hezarehinfo.net", "tender")
        page = parser.parse_list(html, "https://www.hezarehinfo.net/tenders/-%21/page-1")

        self.assertEqual(len(page.notices), 1)
        notice = page.notices[0]
        self.assertEqual(notice.source_record_id, "10950416")
        self.assertEqual(notice.province, "تهران")
        self.assertTrue(notice.metadata["is_special_on_source"])
        self.assertTrue(notice.metadata["has_documents"])
        self.assertEqual(
            page.next_page_urls,
            ["https://www.hezarehinfo.net/tenders/-%21/page-2"],
        )

    def test_detail_parser_extracts_label_values(self):
        html = """
        <html><head><title>نمونه</title></head><body>
        <h1 class="entry-title">مناقصه طراحی ساختمان</h1>
        <div><div><b>شرح آگهی:</b></div><div>شرح کامل پروژه</div></div>
        <div><b>برگزار کننده:</b> شرکت نمونه</div>
        <div><b>منطقه:</b> استان تهران</div>
        <div><b>تاريخ انتشار:</b> 1405/04/29</div>
        <div><b>مهلت ارسال:</b> 1405/05/18</div>
        <div><b>شماره آگهی:</b> 05-04-01</div>
        </body></html>
        """
        detail = HezarehParser("https://www.hezarehinfo.net", "tender").parse_detail(html)
        self.assertEqual(detail["detail_status"], "enriched")
        self.assertEqual(detail["employer"], "شرکت نمونه")
        self.assertEqual(detail["province"], "تهران")
        self.assertEqual(detail["deadline_raw"], "1405/05/18")
        self.assertEqual(detail["description"], "شرح کامل پروژه")

    def test_security_challenge_does_not_raise_parser_failure(self):
        html = "<html><head><title>ورود کد امنیتی</title></head><body>کد امنیتی</body></html>"
        detail = HezarehParser("https://www.hezarehinfo.net", "inquiry").parse_detail(html)
        self.assertEqual(detail, {"detail_status": "security_challenge"})


class ParsNamadParserTests(SimpleTestCase):
    def test_tender_page_with_inquiry_title_is_marked_for_review(self):
        html = """
        <table><tbody id="search_result_list">
          <tr class="text-center">
            <th>1</th><td></td>
            <td><a href="/tender/10897070/sample">استعلام هندراب</a></td>
            <td><a href="/tender/10897070/sample">10897070</a></td>
            <td>1405/04/31</td>
            <td><img src="/pnd/img/search-icons/new-large.png"><img src="/pnd/img/search-icons/special-dis-large.png"></td>
            <td>اصفهان</td>
          </tr>
        </tbody></table>
        """
        page = ParsNamadParser("https://www.parsnamaddata.com", "tender").parse_list(
            html,
            "https://www.parsnamaddata.com/tenders/page/1",
        )
        self.assertEqual(len(page.notices), 1)
        notice = page.notices[0]
        self.assertEqual(notice.content_detected_type, "inquiry")
        self.assertEqual(notice.type_resolution_status, "needs_review")
        self.assertTrue(notice.metadata["is_new_on_source"])
        self.assertFalse(notice.metadata["is_special_on_source"])

    def test_json_ld_detail_is_preferred(self):
        payload = {
            "@context": "https://schema.org",
            "@type": "Event",
            "name": "استعلام خدمات مطالعاتی",
            "eventStatus": "فعال",
            "location": {"address": {"streetAddrees": "تهران, ایران"}},
            "publishDate": "2026-07-21T00:00:00",
            "endDate": "2026-07-25T00:00:00",
            "description": "شرح استعلام",
            "mpn": 10897070,
            "url": "https://www.parsnamaddata.com/tender/10897070/sample",
        }
        html = f'<script type="application/ld+json">{json.dumps(payload, ensure_ascii=False)}</script>'
        detail = ParsNamadParser("https://www.parsnamaddata.com", "inquiry").parse_detail(html)
        self.assertEqual(detail["detail_status"], "enriched")
        self.assertEqual(detail["source_record_id"], "10897070")
        self.assertEqual(detail["province"], "تهران")
        self.assertEqual(detail["type_resolution_status"], "resolved")
