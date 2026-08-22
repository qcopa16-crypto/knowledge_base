"""搜索日志模块路由"""
from rest_framework.routers import DefaultRouter

from search.views import DocumentLogViewSet, SearchLogViewSet

router = DefaultRouter()
router.register("logs", SearchLogViewSet, basename="search-log")
router.register("document-logs", DocumentLogViewSet, basename="document-log")

urlpatterns = router.urls
