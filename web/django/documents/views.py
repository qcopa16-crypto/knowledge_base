"""文档模块视图"""
from django.db.models import F
from rest_framework import filters
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser, IsAuthenticated

from common.response import success
from common.viewsets import BaseViewSet
from documents.models import Document, DocumentContent, DocumentVersion, UserFavorite
from documents.serializers import (
    DocumentContentSerializer,
    DocumentSerializer,
    DocumentVersionSerializer,
    UserFavoriteSerializer,
)


class DocumentViewSet(BaseViewSet):
    """文档：登录可读，写操作需管理员"""

    queryset = Document.objects.select_related("brand", "device_type", "category", "created_by")
    serializer_class = DocumentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ["title", "model_code", "keywords", "summary"]

    def get_queryset(self):
        queryset = super().get_queryset()
        # 多条件过滤
        brand = self.request.query_params.get("brand")
        device_type = self.request.query_params.get("device_type")
        category = self.request.query_params.get("category")
        os_type = self.request.query_params.get("os_type")
        doc_type = self.request.query_params.get("doc_type")
        model_code = self.request.query_params.get("model_code")
        status = self.request.query_params.get("status")
        is_latest = self.request.query_params.get("is_latest")

        if brand:
            queryset = queryset.filter(brand_id=brand)
        if device_type:
            queryset = queryset.filter(device_type_id=device_type)
        if category:
            queryset = queryset.filter(category_id=category)
        if os_type:
            queryset = queryset.filter(os_type=os_type)
        if doc_type:
            queryset = queryset.filter(doc_type=doc_type)
        if model_code:
            queryset = queryset.filter(model_code=model_code)
        if status:
            queryset = queryset.filter(status=status)
        if is_latest is not None:
            queryset = queryset.filter(is_latest=is_latest.lower() in ("true", "1"))
        return queryset

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsAdminUser()]
        return super().get_permissions()

    @action(detail=False, methods=["get"])
    def hot(self, request):
        """热门文档排行（按浏览量倒序）"""
        limit = int(request.query_params.get("limit", 10))
        limit = max(1, min(limit, 100))
        queryset = self.get_queryset().order_by("-view_count")[:limit]
        serializer = self.get_serializer(queryset, many=True)
        return success(serializer.data)

    @action(detail=True, methods=["post"])
    def view(self, request, pk=None):
        """浏览量自增（原子操作）"""
        Document.objects.filter(pk=pk).update(view_count=F("view_count") + 1)
        return success(None, message="浏览记录已更新")

    @action(detail=True, methods=["post"])
    def download(self, request, pk=None):
        """下载量自增（原子操作）"""
        Document.objects.filter(pk=pk).update(download_count=F("download_count") + 1)
        return success(None, message="下载记录已更新")


class DocumentVersionViewSet(BaseViewSet):
    """文档版本历史：登录可读，写需管理员"""

    queryset = DocumentVersion.objects.select_related("document").all()
    serializer_class = DocumentVersionSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsAdminUser()]
        return super().get_permissions()


class DocumentContentViewSet(BaseViewSet):
    """文档解析内容：登录可读，写需管理员"""

    queryset = DocumentContent.objects.select_related("document").all()
    serializer_class = DocumentContentSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsAdminUser()]
        return super().get_permissions()


class UserFavoriteViewSet(BaseViewSet):
    """用户收藏：仅操作自己的收藏"""

    serializer_class = UserFavoriteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return UserFavorite.objects.filter(user=self.request.user).select_related("document")

    @action(detail=False, methods=["post"])
    def toggle(self, request):
        """切换收藏状态（未收藏则收藏，已收藏则取消）"""
        document_id = request.data.get("document")
        if not document_id:
            return success(None, message="缺少 document 参数", status=400)
        favorite = UserFavorite.objects.filter(user=request.user, document_id=document_id).first()
        if favorite:
            favorite.delete()
            return success({"favorited": False}, message="已取消收藏")
        UserFavorite.objects.create(user=request.user, document_id=document_id)
        return success({"favorited": True}, message="收藏成功")
