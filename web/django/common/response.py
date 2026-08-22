"""统一响应格式

所有接口返回统一结构：
    {
        "code": 0,          # 0=成功，非0=业务错误码（与 HTTP 状态码对齐）
        "message": "success",
        "data": { ... }     # 成功时的数据，失败时为空对象/None
    }
"""
from typing import Any

from rest_framework.response import Response


def success(data: Any = None, message: str = "success", status: int = 200) -> Response:
    """构造成功响应"""
    return Response(
        {"code": 0, "message": message, "data": data},
        status=status,
    )


def fail(
    message: str = "error",
    code: int = 400,
    data: Any = None,
    status: int = None,
) -> Response:
    """构造失败响应

    :param code: 业务错误码，默认与 HTTP 状态码一致
    :param status: 实际返回的 HTTP 状态码，默认等于 code
    """
    return Response(
        {"code": code, "message": message, "data": data},
        status=status if status is not None else code,
    )
