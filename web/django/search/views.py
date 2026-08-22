"""搜索日志模块视图"""
from rest_framework.permissions import IsAdminUser, IsAuthenticated

from common.viewsets import BaseViewSet, ReadOnlyBaseViewSet
from search.models import DocumentLog, SearchLog
from search.serializers import DocumentLogSerializer, SearchLogSerializer


class SearchLogViewSet(BaseViewSet):
    """搜索日志：登录可写，删除仅管理员"""

    queryset = SearchLog.objects.select_related("user").all()
    serializer_class = SearchLogSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action == "destroy":
            return [IsAdminUser()]
        return super().get_permissions()


class DocumentLogViewSet(ReadOnlyBaseViewSet):
    """文档操作日志：只读（日志由文档浏览/下载动作产生）"""

    queryset = DocumentLog.objects.select_related("document", "user").all()
    serializer_class = DocumentLogSerializer
    permission_classes = [IsAuthenticated]
