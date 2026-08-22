"""RAG 代理路由（挂载在 /api/rag/ 下）"""
from django.urls import path

from rag.views import (
    RAGResultView,
    RAGSessionListView,
    RAGSessionMessagesView,
    RAGStatusView,
    RAGStreamView,
    RAGSubmitView,
    RAGUploadView, RAGBatchStatusView,
)

urlpatterns = [
    path("submit/", RAGSubmitView.as_view(), name="rag-submit"),
    path("upload/", RAGUploadView.as_view(), name="rag-upload"),
    path('status/batch/', RAGBatchStatusView.as_view(), name="rag-status-batch"),
    path("status/<str:task_id>/", RAGStatusView.as_view(), name="rag-status"),
    path("result/<str:task_id>/", RAGResultView.as_view(), name="rag-result"),
    path("sessions/", RAGSessionListView.as_view(), name="rag-session-list"),
    path("sessions/<str:session_id>/messages/", RAGSessionMessagesView.as_view(), name="rag-session-messages"),
    path("stream/<str:session_id>/", RAGStreamView.as_view(), name="rag-stream"),
]
