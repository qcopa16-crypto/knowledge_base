"""全局异常处理

将 DRF 及未捕获异常统一转换为 {code, message, data} 结构。
"""
import logging

from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """自定义 DRF 异常处理器"""
    response = exception_handler(exc, context)

    if response is not None:
        # DRF 已识别的异常，转为统一结构
        return _build_error_response(exc, response.status_code)

    # 未捕获异常，兜底处理
    logger.exception("未捕获异常: %s", exc, exc_info=True)
    return Response(
        {"code": status.HTTP_500_INTERNAL_SERVER_ERROR, "message": "服务器内部错误", "data": None},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def _build_error_response(exc, http_status: int) -> Response:
    """根据异常类型构造统一错误响应"""
    data = None
    message = "请求失败"

    if isinstance(exc, exceptions.ValidationError):
        # 序列化器校验失败，detail 为字段错误字典
        message = "参数校验失败"
        data = exc.detail
    elif isinstance(exc, exceptions.AuthenticationFailed):
        message = str(exc.detail) if isinstance(exc.detail, str) else "认证失败"
    elif isinstance(exc, exceptions.NotAuthenticated):
        message = "未登录或登录已过期"
    elif isinstance(exc, exceptions.PermissionDenied):
        message = "无权限执行此操作"
    elif isinstance(exc, exceptions.NotFound):
        message = "请求的资源不存在"
    elif isinstance(exc, exceptions.MethodNotAllowed):
        message = "不支持的请求方法"
    elif isinstance(exc, exceptions.Throttled):
        message = "请求过于频繁，请稍后再试"
    elif isinstance(exc, Http404):
        message = "请求的资源不存在"
    else:
        # 其他 DRF 异常，尝试取 detail
        detail = getattr(exc, "detail", None)
        if isinstance(detail, str):
            message = detail
        elif isinstance(detail, (list, dict)):
            message = "请求失败"
            data = detail

    return Response(
        {"code": http_status, "message": message, "data": data},
        status=http_status,
    )
