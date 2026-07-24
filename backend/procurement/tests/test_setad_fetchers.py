from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from procurement.connectors.fetchers import (
    SetadEprocFetcher,
    SetadEtendFetcher,
    fetcher_for,
)
from procurement.http import FetchedPage


class SetadFetcherTests(SimpleTestCase):
    def test_fetcher_registry_returns_connector_specific_clients(self):
        base = {
            "timeout_seconds": 30,
            "retry_count": 1,
            "page_size_hint": 30,
        }
        etend = fetcher_for(
            SimpleNamespace(key="setad_tenders", **base),
            allowed_host="setadiran.ir",
        )
        eproc = fetcher_for(
            SimpleNamespace(key="setad_inquiries", **base),
            allowed_host="setadiran.ir",
        )
        self.assertIsInstance(etend, SetadEtendFetcher)
        self.assertIsInstance(eproc, SetadEprocFetcher)

    def test_eproc_discovers_dynamic_displaytag_page_parameter(self):
        fetcher = SetadEprocFetcher(
            allowed_host="setadiran.ir",
            timeout_seconds=30,
            retry_count=0,
        )
        first = FetchedPage(
            url=fetcher.BASE_LIST_URL,
            status_code=200,
            content=b"first",
            text='<a href="/eproc/needs.do?pager=true&amp;d-146909-p=2">2</a>',
        )
        second = FetchedPage(
            url=f"{fetcher.BASE_LIST_URL}?pager=true&d-146909-p=2",
            status_code=200,
            content=b"second",
            text="<table id='aList'></table>",
        )
        with patch.object(fetcher, "_fetch_html", side_effect=[first, second]) as fetch_html:
            self.assertIs(fetcher.fetch_list(1, "ignored"), first)
            result = fetcher.fetch_list(2, "ignored")

        self.assertIs(result, second)
        self.assertEqual(fetcher.page_parameter, "d-146909-p")
        self.assertEqual(
            fetch_html.call_args_list[1].args[0],
            "https://eproc.setadiran.ir/eproc/needs.do?pager=true&d-146909-p=2",
        )

    def test_etend_public_session_token_is_not_exposed_in_safe_page_url(self):
        fetcher = SetadEtendFetcher(
            allowed_host="setadiran.ir",
            timeout_seconds=30,
            retry_count=0,
            rows=30,
        )
        calls = []

        def fake_fetch(request, **kwargs):
            calls.append((request, kwargs))
            if request.full_url == fetcher.INDEX_URL:
                return FetchedPage(fetcher.INDEX_URL, 200, b"index", "<html></html>")
            if request.full_url == fetcher.WELCOME_URL:
                welcome = '<input type="hidden" name="csrf_token" value="secret-token">'
                return FetchedPage(fetcher.WELCOME_URL, 200, welcome.encode(), welcome)
            return FetchedPage(kwargs["safe_url"], 200, b'{"gridModel":[]}', '{"gridModel":[]}')

        with patch.object(fetcher, "_fetch", side_effect=fake_fetch):
            result = fetcher.fetch_list(2, "ignored")

        list_request, list_kwargs = calls[2]
        self.assertIn("csrf_token=secret-token", list_request.full_url)
        self.assertNotIn("secret-token", list_kwargs["safe_url"])
        self.assertEqual(
            result.url,
            "https://etend.setadiran.ir/etend/callMainPageCartable-anonymous.action?page=2&rows=30",
        )
