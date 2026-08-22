"""目录模块视图"""
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser, IsAuthenticated

from catalog.models import Brand, Category, DeviceType
from catalog.serializers import BrandSerializer, CategorySerializer, DeviceTypeSerializer
from common.response import success
from common.viewsets import BaseViewSet


class BrandViewSet(BaseViewSet):
    """品牌：登录可读，写操作需管理员"""

    queryset = Brand.objects.all().order_by("id")
    serializer_class = BrandSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsAdminUser()]
        return super().get_permissions()


class DeviceTypeViewSet(BaseViewSet):
    """设备类型：登录可读，写操作需管理员"""

    queryset = DeviceType.objects.all().order_by("id")
    serializer_class = DeviceTypeSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsAdminUser()]
        return super().get_permissions()


class CategoryViewSet(BaseViewSet):
    """分类：登录可读，写操作需管理员"""

    queryset = Category.objects.all().order_by("sort_order", "id")
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsAdminUser()]
        return super().get_permissions()

    @action(detail=False, methods=["get"])
    def tree(self, request):
        """返回完整分类树（仅根节点，children 递归嵌套）"""
        roots = self.get_queryset().filter(parent__isnull=True)
        serializer = self.get_serializer(roots, many=True)
        return success(serializer.data)
