"""认证路由（挂载在 /api/auth/ 下）"""
from django.urls import path

from accounts.auth_views import LoginView, MeView, RefreshView, RegisterView

urlpatterns = [
    path("login/", LoginView.as_view(), name="token_obtain_pair"),
    path("refresh/", RefreshView.as_view(), name="token_refresh"),
    path("register/", RegisterView.as_view(), name="register"),
    path("me/", MeView.as_view(), name="me"),
]
