"""账号模块序列化器"""
import re

from django.contrib.auth import get_user_model
from rest_framework import serializers

from accounts.models import Permission, Role, RolePermission, UserRole

User = get_user_model()

PHONE_RE = re.compile(r"^1[3-9]\d{9}$")


class UserSerializer(serializers.ModelSerializer):
    """用户序列化器（创建时需密码，更新时密码可选）"""

    password = serializers.CharField(write_only=True, required=False, min_length=6, max_length=128)
    roles = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = User
        fields = (
            "id", "username", "password", "real_name", "phone", "email",
            "is_active", "is_staff", "is_superuser", "roles", "date_joined",
        )
        read_only_fields = ("id", "date_joined")
        extra_kwargs = {
            "username": {"max_length": 150},
        }

    def get_roles(self, obj):
        return list(obj.user_roles.values_list("role__code", flat=True))

    def validate_phone(self, value):
        if value and not PHONE_RE.match(value):
            raise serializers.ValidationError("手机号格式不正确")
        return value

    def validate_username(self, value):
        if not value.strip():
            raise serializers.ValidationError("用户名不能为空")
        return value

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        if not password:
            raise serializers.ValidationError({"password": "创建用户时必须设置密码"})
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class RegisterSerializer(serializers.Serializer):
    """注册序列化器（创建普通用户）"""

    username = serializers.CharField(max_length=150)
    password = serializers.CharField(min_length=6, max_length=128, write_only=True)
    real_name = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    email = serializers.EmailField(required=False, allow_blank=True, default="")

    def validate_username(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("用户名不能为空")
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("用户名已存在")
        return value

    def validate_phone(self, value):
        if value and not PHONE_RE.match(value):
            raise serializers.ValidationError("手机号格式不正确")
        return value

    def validate_email(self, value):
        if value and User.objects.filter(email=value).exists():
            raise serializers.ValidationError("邮箱已被使用")
        return value

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data["username"],
            password=validated_data["password"],
            real_name=validated_data.get("real_name", ""),
            phone=validated_data.get("phone", ""),
            email=validated_data.get("email", ""),
        )
        return user


class MeSerializer(serializers.ModelSerializer):
    """当前用户信息序列化器（仅允许修改 real_name/phone/email）"""

    class Meta:
        model = User
        fields = (
            "id", "username", "real_name", "phone", "email",
            "is_staff", "is_superuser", "date_joined",
        )
        read_only_fields = ("id", "username", "is_staff", "is_superuser", "date_joined")

    def validate_phone(self, value):
        if value and not PHONE_RE.match(value):
            raise serializers.ValidationError("手机号格式不正确")
        return value


class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ("id", "name", "code", "description")


class RoleSerializer(serializers.ModelSerializer):
    permissions = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Role
        fields = ("id", "name", "code", "description", "permissions", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")

    def get_permissions(self, obj):
        return list(obj.role_permissions.values_list("permission__code", flat=True))


class RolePermissionSerializer(serializers.ModelSerializer):
    """角色-权限关联（用于给角色批量赋权）"""

    class Meta:
        model = RolePermission
        fields = ("id", "role", "permission", "created_at")
        read_only_fields = ("id", "created_at")


class UserRoleSerializer(serializers.ModelSerializer):
    """用户-角色关联（用于给用户分配角色）"""

    class Meta:
        model = UserRole
        fields = ("id", "user", "role", "created_at")
        read_only_fields = ("id", "created_at")
