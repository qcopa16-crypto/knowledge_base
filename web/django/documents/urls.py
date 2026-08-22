"""文档模块路由"""
from rest_framework.routers import DefaultRouter

from documents.views import (
    DocumentContentViewSet,
    DocumentVersionViewSet,
    DocumentViewSet,
    UserFavoriteViewSet,
)

router = DefaultRouter()
router.register("documents", DocumentViewSet, basename="document")
router.register("versions", DocumentVersionViewSet, basename="document-version")
router.register("contents", DocumentContentViewSet, basename="document-content")
router.register("favorites", UserFavoriteViewSet, basename="user-favorite")

urlpatterns = router.urls
