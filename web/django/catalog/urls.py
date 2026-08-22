"""目录模块路由"""
from rest_framework.routers import DefaultRouter

from catalog.views import BrandViewSet, CategoryViewSet, DeviceTypeViewSet

router = DefaultRouter()
router.register("brands", BrandViewSet, basename="brand")
router.register("device-types", DeviceTypeViewSet, basename="device-type")
router.register("categories", CategoryViewSet, basename="category")

urlpatterns = router.urls
