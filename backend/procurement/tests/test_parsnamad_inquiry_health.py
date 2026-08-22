from django.test import SimpleTestCase

from procurement.connectors.parsnamad import ParsNamadParser


def inquiry_row(index: int) -> str:
    record_id = 12000000 + index
    return f"""
    <tr class="text-center">
      <th>{index}</th><td></td>
      <td><a href="/inquiry/{record_id}/sample">استعلام خدمات {index}</a></td>
      <td><a href="/inquiry/{record_id}/sample">{record_id}</a></td>
      <td>1405/05/29</td>
      <td><img src="/pnd/img/search-icons/new-large.png"></td>
      <td>تهران</td>
    </tr>
    """


def inquiry_page(row_count: int, pagination: str = "") -> str:
    rows = "".join(inquiry_row(index) for index in range(1, row_count + 1))
    return f"""
    <html><head><title>استعلام ها</title></head><body>
      <table><tbody id="search_result_list">{rows}</tbody></table>
      {pagination}
    </body></html>
    """


class ParsNamadInquiryPaginationHealthTests(SimpleTestCase):
    def setUp(self):
        self.parser = ParsNamadParser("https://www.parsnamaddata.com", "inquiry")

    def test_visible_future_page_is_not_treated_as_authoritative_total(self):
        html = inquiry_page(
            50,
            """
            <ul class="pagination">
              <li><a href="/inquiries/page/2">2</a></li>
              <li class="active"><a href="/inquiries/page/3">3</a></li>
              <li><a href="/inquiries/page/4">4</a></li>
            </ul>
            """,
        )

        page = self.parser.parse_list(
            html,
            "https://www.parsnamaddata.com/inquiries/page/3",
        )

        self.assertEqual(page.reported_current_page, 3)
        self.assertIsNone(page.reported_total_pages)
        self.assertFalse(page.end_of_results)
        self.assertEqual(page.diagnostics["visible_pagination_max"], 4)
        self.assertEqual(page.diagnostics["visible_future_pages"], [4])
        self.assertEqual(page.diagnostics["pagination_evidence"], "visible_future_page")
        self.assertEqual(page.diagnostics["reported_total_pages_source"], "unknown")

    def test_short_final_page_without_future_link_proves_natural_end(self):
        html = inquiry_page(
            2,
            """
            <ul class="pagination">
              <li><a href="/inquiries/page/2">2</a></li>
              <li><a href="/inquiries/page/3">3</a></li>
              <li class="active"><a href="/inquiries/page/4">4</a></li>
            </ul>
            """,
        )

        page = self.parser.parse_list(
            html,
            "https://www.parsnamaddata.com/inquiries/page/4",
        )

        self.assertEqual(page.reported_total_pages, 4)
        self.assertTrue(page.end_of_results)
        self.assertEqual(page.diagnostics["pagination_evidence"], "short_page_without_future")
        self.assertEqual(
            page.diagnostics["reported_total_pages_source"],
            "short_page_natural_end",
        )

    def test_short_one_page_list_is_complete_without_pagination_links(self):
        page = self.parser.parse_list(
            inquiry_page(3),
            "https://www.parsnamaddata.com/inquiries/page/1",
        )

        self.assertEqual(page.reported_current_page, 1)
        self.assertEqual(page.reported_total_pages, 1)
        self.assertTrue(page.end_of_results)
        self.assertEqual(page.diagnostics["pagination_evidence"], "short_page_without_future")

    def test_full_page_without_future_link_remains_fail_closed(self):
        page = self.parser.parse_list(
            inquiry_page(50),
            "https://www.parsnamaddata.com/inquiries/page/1",
        )

        self.assertEqual(len(page.notices), 50)
        self.assertIsNone(page.reported_total_pages)
        self.assertIsNone(page.end_of_results)
        self.assertEqual(
            page.diagnostics["pagination_evidence"],
            "full_page_without_future_unverified",
        )

    def test_empty_page_without_end_evidence_is_not_declared_complete(self):
        page = self.parser.parse_list(
            inquiry_page(0),
            "https://www.parsnamaddata.com/inquiries/page/2",
        )

        self.assertEqual(page.notices, [])
        self.assertIsNone(page.reported_total_pages)
        self.assertIsNone(page.end_of_results)
        self.assertIn("no_notice_rows_found", page.warnings)
        self.assertEqual(page.diagnostics["pagination_evidence"], "empty_page_unverified")
