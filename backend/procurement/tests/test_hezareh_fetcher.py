from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from procurement.connectors.fetchers import HezarehSessionFetcher, fetcher_for
from procurement.http import FetchedPage


class HezarehFetcherTests(SimpleTestCase):
    def test_registry_uses_persistent_public_session_for_hezareh(self):
        connector = SimpleNamespace(
            key="hezareh_inquiries",
            timeout_seconds=30,
            retry_count=1,
            page_size_hint=20,
        )

        fetcher = fetcher_for(connector, allowed_host="www.hezarehinfo.net")

        self.assertIsInstance(fetcher, HezarehSessionFetcher)

    def test_direct_list_session_is_reused_without_home_warmup(self):
        fetcher = HezarehSessionFetcher(
            allowed_host="www.hezarehinfo.net",
            timeout_seconds=30,
            retry_count=0,
            list_delay_ms=0,
        )
        page_one_url = "https://www.hezarehinfo.net/inquiries"
        page_two_url = "https://www.hezarehinfo.net/inquiries/-%21/page-2"

        def fetched(url: str) -> FetchedPage:
            return FetchedPage(url=url, status_code=200, content=b"ok", text="<html></html>")

        with patch.object(
            fetcher,
            "_fetch",
            side_effect=[fetched(page_one_url), fetched(page_two_url)],
        ) as request_fetch:
            fetcher.fetch_list(1, page_one_url)
            fetcher.fetch_list(2, page_two_url)

        self.assertEqual(request_fetch.call_count, 2)
        first_request = request_fetch.call_args_list[0].args[0]
        second_request = request_fetch.call_args_list[1].args[0]
        self.assertEqual(first_request.full_url, page_one_url)
        self.assertIsNone(first_request.headers.get("Referer"))
        self.assertEqual(second_request.full_url, page_two_url)
        self.assertEqual(second_request.headers.get("Referer"), page_one_url)
        self.assertNotEqual(first_request.full_url, fetcher.HOME_URL)
        self.assertNotEqual(second_request.full_url, fetcher.HOME_URL)
