"""账号管理路由（挂载在 /api/accounts/ 下）"""
from rest_framework.routers import DefaultRouter

from accounts.views import (
    PermissionViewSet,
    RolePermissionViewSet,
    RoleViewSet,
    UserRoleViewSet,
    UserViewSet,
)

router = DefaultRouter()
router.register("users", UserViewSet, basename="user")
router.register("roles", RoleViewSet, basename="role")
router.register("permissions", PermissionViewSet, basename="permission")
router.register("role-permissions", RolePermissionViewSet, basename="role-permission")
router.register("user-roles", UserRoleViewSet, basename="user-role")

urlpatterns = router.urls
