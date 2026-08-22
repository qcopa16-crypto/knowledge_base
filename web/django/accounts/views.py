"""账号模块视图"""
from django.contrib.auth import get_user_model
from rest_framework import viewsets
from rest_framework.permissions import IsAdminUser

from accounts.models import Permission, Role, RolePermission, UserRole
from accounts.serializers import (
    PermissionSerializer,
    RolePermissionSerializer,
    RoleSerializer,
    UserRoleSerializer,
    UserSerializer,
)
from common.viewsets import BaseViewSet

User = get_user_model()


class UserViewSet(BaseViewSet):
    """用户管理（仅管理员可操作）"""

    queryset = User.objects.all().order_by("id")
    serializer_class = UserSerializer
    permission_classes = [IsAdminUser]


class RoleViewSet(BaseViewSet):
    """角色管理（仅管理员可操作）"""

    queryset = Role.objects.all().order_by("id")
    serializer_class = RoleSerializer
    permission_classes = [IsAdminUser]


class PermissionViewSet(BaseViewSet):
    """权限管理（仅管理员可操作）"""

    queryset = Permission.objects.all().order_by("id")
    serializer_class = PermissionSerializer
    permission_classes = [IsAdminUser]


class RolePermissionViewSet(BaseViewSet):
    """角色-权限关联（仅管理员可操作）"""

    queryset = RolePermission.objects.all().order_by("id")
    serializer_class = RolePermissionSerializer
    permission_classes = [IsAdminUser]


class UserRoleViewSet(BaseViewSet):
    """用户-角色关联（仅管理员可操作）"""

    queryset = UserRole.objects.all().order_by("id")
    serializer_class = UserRoleSerializer
    permission_classes = [IsAdminUser]
