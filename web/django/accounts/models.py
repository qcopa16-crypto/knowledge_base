"""账号与权限模块模型"""
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from common.authentication import CachedJWTAuthentication


class User(AbstractUser):
    """用户（扩展 Django 内置用户）"""

    real_name = models.CharField("真实姓名", max_length=64, blank=True, default="")
    phone = models.CharField("手机号", max_length=20, blank=True, default="")

    class Meta:
        db_table = "accounts_user"
        verbose_name = "用户"
        verbose_name_plural = "用户"

    def __str__(self):
        return self.username


class Role(models.Model):
    """角色"""

    name = models.CharField("角色名", max_length=64, unique=True)
    code = models.CharField("角色编码", max_length=64, unique=True)
    description = models.CharField("描述", max_length=255, blank=True, default="")
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "accounts_role"
        verbose_name = "角色"
        verbose_name_plural = "角色"

    def __str__(self):
        return self.name


class Permission(models.Model):
    """权限"""

    name = models.CharField("权限名", max_length=64, unique=True)
    code = models.CharField("权限编码", max_length=128, unique=True)
    description = models.CharField("描述", max_length=255, blank=True, default="")

    class Meta:
        db_table = "accounts_permission"
        verbose_name = "权限"
        verbose_name_plural = "权限"

    def __str__(self):
        return self.name


class RolePermission(models.Model):
    """角色-权限关联"""

    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="role_permissions")
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, related_name="role_permissions")
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        db_table = "accounts_role_permission"
        unique_together = ("role", "permission")
        verbose_name = "角色权限关联"
        verbose_name_plural = "角色权限关联"


class UserRole(models.Model):
    """用户-角色关联"""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_roles")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="user_roles")
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        db_table = "accounts_user_role"
        unique_together = ("user", "role")
        verbose_name = "用户角色关联"
        verbose_name_plural = "用户角色关联"


# ====================== 缓存一致性处理 ======================
def _clear_user_auth_cache(user_id):
    """统一的清除用户认证缓存方法"""
    cache_key = f"{CachedJWTAuthentication.CACHE_KEY_PREFIX}{user_id}"
    cache.delete(cache_key)


@receiver(post_save, sender=User)
def clear_cache_on_user_save(sender, instance, **kwargs):
    """用户信息新增/修改时清缓存"""
    _clear_user_auth_cache(instance.id)


@receiver(post_delete, sender=User)
def clear_cache_on_user_delete(sender, instance, **kwargs):
    """用户删除时清缓存，避免残留缓存"""
    _clear_user_auth_cache(instance.id)


@receiver(post_save, sender=UserRole)
@receiver(post_delete, sender=UserRole)
def clear_cache_on_user_role_change(sender, instance, **kwargs):
    """用户角色分配/移除时，同步清除对应用户缓存
    说明：当前缓存仅存 User 基础字段，角色权限为实时关联查询，本步骤可按需开启
    若后续权限校验加入缓存、或用户信息预加载角色，必须开启
    """
    _clear_user_auth_cache(instance.user_id)
