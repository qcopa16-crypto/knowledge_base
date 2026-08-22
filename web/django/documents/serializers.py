"""文档模块序列化器"""
import re

from rest_framework import serializers

from documents.models import Document, DocumentContent, DocumentVersion, UserFavorite

MODEL_CODE_RE = re.compile(r"^[A-Za-z0-9\-_\.\s]{1,128}$")


class DocumentSerializer(serializers.ModelSerializer):
    brand_name = serializers.CharField(source="brand.name", read_only=True)
    device_type_name = serializers.CharField(source="device_type.name", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    created_by_name = serializers.CharField(source="created_by.username", read_only=True)

    class Meta:
        model = Document
        fields = (
            "id", "title", "brand", "brand_name", "device_type", "device_type_name",
            "category", "category_name", "model_code", "os_type", "doc_type",
            "version", "file_path", "file_md5", "file_size", "cover", "summary",
            "keywords", "view_count", "download_count", "is_latest", "status",
            "created_by", "created_by_name", "created_at", "updated_at",
        )
        read_only_fields = (
            "id", "view_count", "download_count", "created_by", "created_at", "updated_at",
        )

    def validate_model_code(self, value):
        if not MODEL_CODE_RE.match(value):
            raise serializers.ValidationError("型号编码格式不正确")
        return value

    def validate_title(self, value):
        if not value.strip():
            raise serializers.ValidationError("标题不能为空")
        return value

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data["created_by"] = request.user
        return super().create(validated_data)


class DocumentVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentVersion
        fields = (
            "id", "document", "version", "file_path", "file_md5",
            "remark", "created_by", "created_at",
        )
        read_only_fields = ("id", "created_by", "created_at")

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data["created_by"] = request.user
        return super().create(validated_data)


class DocumentContentSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentContent
        fields = (
            "id", "document", "content_text", "page_count",
            "parse_status", "parse_time",
        )
        read_only_fields = ("id", "parse_time")


class UserFavoriteSerializer(serializers.ModelSerializer):
    document_title = serializers.CharField(source="document.title", read_only=True)

    class Meta:
        model = UserFavorite
        fields = ("id", "user", "document", "document_title", "created_at")
        read_only_fields = ("id", "created_at")

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data["user"] = request.user
        return super().create(validated_data)
