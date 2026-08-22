from django.core.cache import cache
from rest_framework_simplejwt.authentication import JWTAuthentication


class CachedJWTAuthentication(JWTAuthentication):
    """
    带 Redis 缓存的 JWT 认证类
    核心作用：避免每次请求都查询 MySQL 用户表，大幅降低数据库连接压力
    降级机制：缓存未命中/Redis 故障时，自动回退到原生数据库查询逻辑
    """

    CACHE_TIMEOUT = 300
    CACHE_KEY_PREFIX = "auth:user:"

    def get_user(self, validated_token):
        # 延迟导入：在方法内部调用，避免模块加载期循环依赖
        from django.contrib.auth import get_user_model
        User = get_user_model()

        user_id = validated_token["user_id"]
        cache_key = f"{self.CACHE_KEY_PREFIX}{user_id}"

        # 1. 优先读 Redis 缓存
        user = cache.get(cache_key)
        if user is not None:
            return user

        # 2. 缓存未命中，走原生逻辑查 MySQL
        user = super().get_user(validated_token)

        # 3. 写入缓存，下次请求直接复用
        cache.set(cache_key, user, timeout=self.CACHE_TIMEOUT)

        return user