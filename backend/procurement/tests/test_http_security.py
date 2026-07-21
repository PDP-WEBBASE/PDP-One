import socket
from unittest.mock import patch

from django.test import SimpleTestCase

from procurement.http import SourceFetchError, validate_source_url


class SourceUrlSecurityTests(SimpleTestCase):
    @patch("procurement.http.socket.getaddrinfo")
    def test_configured_public_domain_is_allowed(self, getaddrinfo):
        getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ]
        validate_source_url(
            "https://www.hezarehinfo.net/tenders/-%21/page-1",
            "www.hezarehinfo.net",
        )

    @patch("procurement.http.socket.getaddrinfo")
    def test_private_dns_result_is_rejected(self, getaddrinfo):
        getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))
        ]
        with self.assertRaises(SourceFetchError) as context:
            validate_source_url("https://www.hezarehinfo.net/test", "www.hezarehinfo.net")
        self.assertEqual(context.exception.category, "validation")
        self.assertFalse(context.exception.retryable)

    @patch("procurement.http.socket.getaddrinfo")
    def test_other_domain_and_non_https_urls_are_rejected(self, getaddrinfo):
        with self.assertRaises(SourceFetchError):
            validate_source_url("https://example.com/test", "www.hezarehinfo.net")
        with self.assertRaises(SourceFetchError):
            validate_source_url("http://www.hezarehinfo.net/test", "www.hezarehinfo.net")
        getaddrinfo.assert_not_called()
