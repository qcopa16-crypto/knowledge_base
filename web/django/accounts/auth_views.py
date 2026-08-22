"""JWT 认证视图（统一响应格式包装）"""
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from accounts.serializers import MeSerializer, RegisterSerializer
from common.response import fail, success


class LoginView(TokenObtainPairView):
    """登录，返回 {code, message, data: {access, refresh}}"""

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        # 认证失败时 simplejwt 返回 401，透传给全局异常处理
        if response.status_code >= 400:
            return response
        return success(response.data, message="登录成功")


class RefreshView(TokenRefreshView):
    """刷新 token"""

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code >= 400:
            return response
        return success(response.data, message="刷新成功")


class RegisterView(APIView):
    """注册接口：创建普通用户并返回 token

    权限：允许匿名访问（authentication_classes 为空，permission_classes 为 AllowAny）
    """

    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # 注册成功后直接签发 token，免去二次登录
        refresh = RefreshToken.for_user(user)
        data = {
            "id": user.id,
            "username": user.username,
            "real_name": user.real_name,
            "phone": user.phone,
            "email": user.email,
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }
        return success(data, message="注册成功", status=status.HTTP_201_CREATED)


class MeView(generics.RetrieveUpdateAPIView):
    """当前用户信息：GET 查看，PATCH 修改 real_name/phone/email"""

    serializer_class = MeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    def get(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return success(serializer.data)

    def patch(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return success(serializer.data, message="更新成功")

    def put(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return success(serializer.data, message="更新成功")
