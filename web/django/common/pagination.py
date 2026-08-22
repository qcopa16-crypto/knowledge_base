"""统一分页

分页结果统一为：
    {
        "count": 总条数,
        "page": 当前页,
        "page_size": 每页条数,
        "results": [ ... ]
    }
"""
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
    page_query_param = "page"

    def get_paginated_response(self, data):
        return Response(
            {
                "code": 0,
                "message": "success",
                "data": {
                    "count": self.page.paginator.count,
                    "page": self.page.number,
                    "page_size": self.get_page_size(self.request),
                    "results": data,
                },
            }
        )
