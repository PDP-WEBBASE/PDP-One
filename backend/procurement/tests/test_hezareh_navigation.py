from unittest.mock import patch

from django.test import SimpleTestCase

from procurement.connectors.fetchers import HezarehSessionFetcher
from procurement.http import FetchedPage


class HezarehNavigationTests(SimpleTestCase):
    def _fetcher(self, *, delay_ms=1200):
        return HezarehSessionFetcher(
            allowed_host="www.hezarehinfo.net",
            timeout_seconds=10,
            retry_count=0,
            list_delay_ms=delay_ms,
        )

    def test_first_list_request_is_direct_without_home_warmup_or_referer(self):
        fetcher = self._fetcher(delay_ms=0)
        observed = []

        def fake_fetch(request, **kwargs):
            observed.append((request.full_url, request.headers.get("Referer")))
            body = b"<html></html>"
            return FetchedPage(
                url=request.full_url,
                status_code=200,
                content=body,
                text=body.decode("utf-8"),
            )

        page1 = "https://www.hezarehinfo.net/inquiries"
        with patch.object(fetcher, "_fetch", side_effect=fake_fetch):
            fetcher.fetch_list(1, page1)

        self.assertEqual(observed, [(page1, None)])

    def test_list_navigation_uses_previous_successful_page_as_referer(self):
        fetcher = self._fetcher()
        observed = []

        def fake_fetch(request, **kwargs):
            observed.append((request.full_url, request.headers.get("Referer")))
            body = b"<html></html>"
            return FetchedPage(
                url=request.full_url,
                status_code=200,
                content=body,
                text=body.decode("utf-8"),
            )

        page1 = "https://www.hezarehinfo.net/inquiries"
        page2 = "https://www.hezarehinfo.net/inquiries/-%21/page-2"
        page3 = "https://www.hezarehinfo.net/inquiries/-%21/page-3"

        with patch.object(fetcher, "_fetch", side_effect=fake_fetch), patch(
            "procurement.connectors.fetchers.time.sleep"
        ) as sleep_mock:
            fetcher.fetch_list(1, page1)
            fetcher.fetch_list(2, page2)
            fetcher.fetch_list(3, page3)

        self.assertEqual(
            observed,
            [
                (page1, None),
                (page2, page1),
                (page3, page2),
            ],
        )
        self.assertEqual(sleep_mock.call_count, 2)
        sleep_mock.assert_any_call(1.2)

    def test_first_list_page_has_no_navigation_delay(self):
        fetcher = self._fetcher(delay_ms=1500)

        def fake_fetch(request, **kwargs):
            body = b"<html></html>"
            return FetchedPage(
                url=request.full_url,
                status_code=200,
                content=body,
                text=body.decode("utf-8"),
            )

        with patch.object(fetcher, "_fetch", side_effect=fake_fetch), patch(
            "procurement.connectors.fetchers.time.sleep"
        ) as sleep_mock:
            fetcher.fetch_list(1, "https://www.hezarehinfo.net/tenders")

        sleep_mock.assert_not_called()

    def test_navigation_delay_is_bounded(self):
        self.assertEqual(self._fetcher(delay_ms=-1).list_delay_ms, 0)
        self.assertEqual(self._fetcher(delay_ms=9999).list_delay_ms, 3000)

    def test_detail_request_uses_last_successful_list_page_as_referer(self):
        fetcher = self._fetcher(delay_ms=0)
        observed = []

        def fake_fetch(request, **kwargs):
            observed.append((request.full_url, request.headers.get("Referer")))
            body = b"<html></html>"
            return FetchedPage(
                url=request.full_url,
                status_code=200,
                content=body,
                text=body.decode("utf-8"),
            )

        list_url = "https://www.hezarehinfo.net/inquiries"
        detail_url = "https://www.hezarehinfo.net/inquiries/nid12345"
        with patch.object(fetcher, "_fetch", side_effect=fake_fetch):
            fetcher.fetch_list(1, list_url)
            fetcher.fetch_detail(detail_url)

        self.assertEqual(observed[-1], (detail_url, list_url))
