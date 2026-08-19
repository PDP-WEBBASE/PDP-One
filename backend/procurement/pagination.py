from rest_framework.pagination import PageNumberPagination


class PDPPageNumberPagination(PageNumberPagination):
    """Bounded page-number pagination used by PDP One list APIs.

    The browser may request 30, 50 or 100 rows. Other positive values are
    accepted up to the hard 100-row cap so API clients cannot accidentally
    recreate the historical full-collection loading pattern.
    """

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 100
