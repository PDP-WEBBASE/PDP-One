import json

from django.test import SimpleTestCase

from procurement.connectors.setad import SetadEprocParser, SetadEtendParser, repair_setad_text


def mojibake(value: str) -> str:
    return value.encode("utf-8").decode("cp1256")


def eproc_row(number="۱۱۰۵۰۹۳۹۹۲۰۰۰۰۳۱", deadline="۴ روز و ۸ ساعت") -> str:
    return f"""
      <tr>
        <td>۱</td>
        <td><a href="javascript:void(0)" onclick="javascript:showPurchaseNeed(7279593,1432,5239285)">{number}</a></td>
        <td>خدمات مطالعات و طراحی شبکه برق</td>
        <td>شرکت برق منطقه‌ای</td>
        <td>اصفهان</td>
        <td>انتخاب تامین کننده</td>
        <td>خدمات</td>
        <td></td>
        <td>فعالیت‌های حرفه‌ای، علمی و فنی</td>
        <td>۱۴۰۵/۰۴/۳۱</td>
        <td>{deadline}</td>
      </tr>
    """


class SetadEtendParserTests(SimpleTestCase):
    def test_json_parser_repairs_windows_capture_encoding_and_maps_fields(self):
        payload = {
            "page": 1,
            "total": 2,
            "records": 31,
            "gridModel": [
                {
                    "id": 650152,
                    "number": 2005001211000033,
                    "title": mojibake("فراخوان ارزیابی کیفی شرکت‌های مشاور انرژی"),
                    "type": "SHORT_LIST_QUALITY_EVALUATION",
                    "typeName": mojibake("ارزیابی کیفی برای لیست کوتاه"),
                    "organization": {"name": mojibake("شرکت توزیع برق اصفهان")},
                    "operationProvinceName": mojibake("اصفهان"),
                    "operationCityName": mojibake("اصفهان"),
                    "publicNotificationDate": "1405/04/31 19:00:00",
                    "documentsDeadlineDate": "1405/05/06 19:00:00",
                    "proposalDeadlineDate": "1405/05/20 19:00:00",
                    "domainsDescription": mojibake("شناسایی و جذب شرکت‌های مشاور انرژی"),
                    "allowedContractor": True,
                    "allowedConsultation": False,
                    "allowedCommodity": False,
                    "allowedServices": False,
                }
            ],
        }
        parser = SetadEtendParser("https://setadiran.ir", "tender")
        page = parser.parse_list(
            json.dumps(payload, ensure_ascii=False),
            "https://etend.setadiran.ir/etend/callMainPageCartable-anonymous.action?page=1&rows=30",
        )

        self.assertEqual(len(page.notices), 1)
        notice = page.notices[0]
        self.assertEqual(notice.source_record_id, "650152")
        self.assertEqual(notice.notice_number, "2005001211000033")
        self.assertEqual(notice.title, "فراخوان ارزیابی کیفی شرکت های مشاور انرژی")
        self.assertEqual(notice.employer, "شرکت توزیع برق اصفهان")
        self.assertEqual(notice.province, "اصفهان")
        self.assertEqual(notice.deadline_raw, "1405/05/20 19:00:00")
        self.assertEqual(notice.metadata["setad_channel"], "etend")
        self.assertEqual(
            page.next_page_urls,
            ["https://etend.setadiran.ir/etend/callMainPageCartable-anonymous.action?page=2"],
        )

    def test_repair_does_not_change_normal_persian_text(self):
        self.assertEqual(repair_setad_text("مناقصه عمومی"), "مناقصه عمومی")


class SetadEprocParserTests(SimpleTestCase):
    def test_html_parser_extracts_public_need_and_detail_identifiers(self):
        html = f"""
        <html><body>
          <span class="pagelinks"><a href="/eproc/needs.do?pager=true&amp;d-146909-p=2">2</a></span>
          <table class="grid" id="aList"><tbody>{eproc_row()}</tbody></table>
        </body></html>
        """
        parser = SetadEprocParser("https://setadiran.ir", "inquiry")
        page = parser.parse_list(html, "https://eproc.setadiran.ir/eproc/needs.do")

        self.assertEqual(len(page.notices), 1)
        notice = page.notices[0]
        self.assertEqual(notice.source_record_id, "۱۱۰۵۰۹۳۹۹۲۰۰۰۰۳۱")
        self.assertEqual(notice.notice_number, "۱۱۰۵۰۹۳۹۹۲۰۰۰۰۳۱")
        self.assertEqual(notice.title, "خدمات مطالعات و طراحی شبکه برق")
        self.assertEqual(notice.employer, "شرکت برق منطقه ای")
        self.assertEqual(notice.province, "اصفهان")
        self.assertEqual(notice.deadline_raw, "۴ روز و ۸ ساعت")
        self.assertIn("reqId=7279593", notice.detail_url)
        self.assertIn("domainType=1432", notice.detail_url)
        self.assertIn("needId=5239285", notice.detail_url)
        self.assertEqual(notice.metadata["setad_channel"], "eproc")
        self.assertEqual(page.reported_current_page, 1)
        self.assertIsNone(page.reported_total_pages)
        self.assertFalse(page.end_of_results)
        self.assertEqual(
            page.next_page_urls,
            ["https://eproc.setadiran.ir/eproc/needs.do?pager=true&d-146909-p=2"],
        )

    def test_dynamic_displaytag_parameter_reports_actual_current_page(self):
        html = f"""
        <html><body>
          <span class="pagelinks">
            <a href="/eproc/needs.do?pager=true&amp;d-146909-p=4">4</a>
            <a href="/eproc/needs.do?pager=true&amp;d-146909-p=6">6</a>
          </span>
          <table class="grid" id="aList"><tbody>{eproc_row()}</tbody></table>
        </body></html>
        """
        parser = SetadEprocParser("https://setadiran.ir", "inquiry")
        page = parser.parse_list(
            html,
            "https://eproc.setadiran.ir/eproc/needs.do?pager=true&d-146909-p=5",
        )

        self.assertEqual(page.reported_current_page, 5)
        self.assertIsNone(page.reported_total_pages)
        self.assertFalse(page.end_of_results)
        self.assertEqual(page.diagnostics["visible_max_page"], 6)
        self.assertTrue(page.diagnostics["dynamic_page_parameter"])

    def test_sliding_visible_window_is_not_treated_as_total_pages(self):
        html = f"""
        <html><body>
          <span class="pagelinks">
            <a href="/eproc/needs.do?pager=true&amp;d-146909-p=8">8</a>
            <a href="/eproc/needs.do?pager=true&amp;d-146909-p=9">9</a>
            <a href="/eproc/needs.do?pager=true&amp;d-146909-p=11">11</a>
            <a href="/eproc/needs.do?pager=true&amp;d-146909-p=12">12</a>
          </span>
          <table class="grid" id="aList"><tbody>{eproc_row()}</tbody></table>
        </body></html>
        """
        parser = SetadEprocParser("https://setadiran.ir", "inquiry")
        page = parser.parse_list(
            html,
            "https://eproc.setadiran.ir/eproc/needs.do?pager=true&d-146909-p=10",
        )

        self.assertEqual(page.reported_current_page, 10)
        self.assertFalse(page.end_of_results)
        self.assertIsNone(page.reported_total_pages)
        self.assertEqual(page.diagnostics["future_page_numbers"], [11, 12])

    def test_last_page_without_future_link_is_reported_complete(self):
        html = f"""
        <html><body>
          <span class="pagelinks">
            <a href="/eproc/needs.do?pager=true&amp;d-146909-p=18">18</a>
            <a href="/eproc/needs.do?pager=true&amp;d-146909-p=19">19</a>
          </span>
          <table class="grid" id="aList"><tbody>{eproc_row()}</tbody></table>
        </body></html>
        """
        parser = SetadEprocParser("https://setadiran.ir", "inquiry")
        page = parser.parse_list(
            html,
            "https://eproc.setadiran.ir/eproc/needs.do?pager=true&d-146909-p=20",
        )

        self.assertEqual(page.reported_current_page, 20)
        self.assertEqual(page.reported_total_pages, 20)
        self.assertTrue(page.end_of_results)
        self.assertEqual(page.diagnostics["future_page_numbers"], [])

    def test_short_single_page_list_is_complete_without_pagination_parameter(self):
        html = f"""
        <html><body>
          <table class="grid" id="aList"><tbody>{eproc_row()}</tbody></table>
        </body></html>
        """
        parser = SetadEprocParser("https://setadiran.ir", "inquiry")
        page = parser.parse_list(html, "https://eproc.setadiran.ir/eproc/needs.do")

        self.assertEqual(page.reported_current_page, 1)
        self.assertEqual(page.reported_total_pages, 1)
        self.assertTrue(page.end_of_results)

    def test_full_size_first_page_without_pagination_stays_unverified(self):
        rows = "".join(
            eproc_row(number=f"۱۱۰۵۰۹۳۹۹۲۰۰۰{index:04d}")
            for index in range(SETAD_EPROC_PAGE_SIZE_FOR_TEST)
        )
        html = f"""
        <html><body>
          <table class="grid" id="aList"><tbody>{rows}</tbody></table>
        </body></html>
        """
        parser = SetadEprocParser("https://setadiran.ir", "inquiry")
        page = parser.parse_list(html, "https://eproc.setadiran.ir/eproc/needs.do")

        self.assertEqual(page.reported_current_page, 1)
        self.assertIsNone(page.reported_total_pages)
        self.assertIsNone(page.end_of_results)


SETAD_EPROC_PAGE_SIZE_FOR_TEST = 30
