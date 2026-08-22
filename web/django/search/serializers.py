"""搜索日志模块序列化器"""
from rest_framework import serializers

from search.models import DocumentLog, SearchLog


class SearchLogSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = SearchLog
        fields = ("id", "keyword", "result_count", "user", "username", "created_at")
        read_only_fields = ("id", "user", "created_at")

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data["user"] = request.user
        return super().create(validated_data)


class DocumentLogSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    document_title = serializers.CharField(source="document.title", read_only=True)

    class Meta:
        model = DocumentLog
        fields = (
            "id", "document", "document_title", "user", "username",
            "action", "created_at",
        )
        read_only_fields = ("id", "user", "created_at")

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data["user"] = request.user
        return super().create(validated_data)
