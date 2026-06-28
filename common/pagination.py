"""Pagination classes for DigiHMS API list endpoints.

All list ViewSets should set ``pagination_class = StandardPagination``.
"""

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardPagination(PageNumberPagination):
    """Default page-number pagination for DigiHMS.

    Defaults to 50 items per page and caps at 200 to avoid silent
    truncation / oversized payloads.
    """

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200

    def get_paginated_response(self, data):
        return Response(
            {
                "success": True,
                "count": self.page.paginator.count,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
            }
        )
