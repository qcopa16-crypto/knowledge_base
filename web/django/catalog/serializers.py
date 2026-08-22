"""目录模块序列化器"""
from rest_framework import serializers

from catalog.models import Brand, Category, DeviceType


class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = ("id", "name", "code", "description", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")


class DeviceTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceType
        fields = ("id", "name", "code", "description", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")


class CategorySerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Category
        fields = (
            "id", "name", "code", "parent", "path", "level",
            "sort_order", "children", "created_at", "updated_at",
        )
        read_only_fields = ("id", "path", "level", "created_at", "updated_at")

    def get_children(self, obj):
        # 仅一层子节点（避免递归过深）
        children = obj.children.all()
        if children.exists():
            return CategorySerializer(children, many=True, context=self.context).data
        return []

    def validate(self, attrs):
        parent = attrs.get("parent")
        # 计算 level 与 path
        if parent:
            attrs["level"] = parent.level + 1
            attrs["path"] = f"{parent.path}/{attrs.get('code', '')}".strip("/")
        else:
            attrs["level"] = 1
            attrs["path"] = attrs.get("code", "")
        return attrs

    def create(self, validated_data):
        # path/level 已在 validate 中设置
        return super().create(validated_data)

    def update(self, instance, validated_data):
        old_code = instance.code
        new_code = validated_data.get("code", old_code)
        parent = validated_data.get("parent", instance.parent)
        # 重算 path/level
        if parent:
            validated_data["level"] = parent.level + 1
            validated_data["path"] = f"{parent.path}/{new_code}".strip("/")
        else:
            validated_data["level"] = 1
            validated_data["path"] = new_code
        return super().update(instance, validated_data)
