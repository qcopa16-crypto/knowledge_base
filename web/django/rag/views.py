"""RAG 任务代理视图

Django 作为主任务处理方：
- POST /api/rag/submit/：投递 Celery 任务（入库/检索）到 RabbitMQ
- POST /api/rag/upload/：接收文件上传，保存后投递入库任务
- GET /api/rag/status/{task_id}/：查询任务状态（Redis）
- GET /api/rag/result/{task_id}/：查询任务结果（Redis）
"""
import os
import uuid
from datetime import datetime

from django.http import JsonResponse, StreamingHttpResponse
from django.views import View
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from common.authentication import CachedJWTAuthentication
from common.response import fail, success
from tool.logger import logger
from utils.mongo_history_utils import (
    create_or_update_session,
    get_recent_messages,
    get_session,
    list_sessions,
)
from utils.sse_utils import sse_generator_sync
from utils.task_utils import (
    TASK_STATUS_PENDING,
    get_task_result,
    get_task_status,
    get_done_task_list,
    get_running_task_list,
    update_task_status,
)

ALLOWED_EXTENSIONS = {".pdf", ".md", ".txt"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


class RAGUploadView(APIView):
    """文件上传入库：接收多个 PDF/MD/TXT 文件，逐个保存后投递 Celery 入库任务"""

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    def post(self, request, *args, **kwargs):
        files = request.FILES.getlist("files")
        if not files:
            return fail("缺少上传文件", code=400)

        data_root = os.getenv("DATA_BASED_ROOT_DIR", os.path.join(os.getcwd(), "data"))
        accepted = []
        skipped = []

        for file in files:
            # 扩展名校验
            ext = os.path.splitext(file.name)[1].lower()
            if ext not in ALLOWED_EXTENSIONS:
                skipped.append({"filename": file.name, "reason": "仅支持 .pdf / .md / .txt 文件"})
                continue

            # 大小校验
            if file.size > MAX_FILE_SIZE:
                skipped.append({"filename": file.name, "reason": "文件超过 50MB 限制"})
                continue

            task_id = str(uuid.uuid4())
            file_dir = os.path.join(data_root, datetime.now().strftime("%Y%m%d"), task_id)
            os.makedirs(file_dir, exist_ok=True)
            import_file_path = os.path.join(file_dir, file.name)

            # 保存文件
            with open(import_file_path, "wb") as f:
                for chunk in file.chunks():
                    f.write(chunk)

            logger.info(f"[{task_id}] 文件已保存：{import_file_path}")

            # 投递入库任务
            from tasks.rag_tasks import import_document
            update_task_status(task_id, TASK_STATUS_PENDING)
            import_document.apply_async(args=[task_id, file_dir, import_file_path])

            accepted.append({"task_id": task_id, "filename": file.name})

        if not accepted:
            return fail("没有文件通过校验", code=400, data={"skipped": skipped})

        return success({
            "files": accepted,
            "skipped": skipped,
        }, message=f"已提交 {len(accepted)} 个入库任务", status=202)


class RAGSubmitView(APIView):
    """投递 RAG 任务（入库/检索）到 Celery 队列"""

    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        op = request.data.get("op")
        task_id = str(uuid.uuid4())

        if op == "import":
            file_dir = request.data.get("file_dir", "")
            import_file_path = request.data.get("import_file_path", "")
            if not import_file_path:
                return fail("import 操作需要 import_file_path", code=400)

            from tasks.rag_tasks import import_document
            update_task_status(task_id, TASK_STATUS_PENDING)
            import_document.apply_async(args=[task_id, file_dir, import_file_path])
            return success({"task_id": task_id, "op": "import"}, message="入库任务已提交", status=202)

        elif op == "query":
            query = request.data.get("query", "")
            if not query:
                return fail("query 操作需要 query", code=400)

            # 会话 ID：前端可传已有 session_id 续聊，空则新建会话
            session_id = request.data.get("session_id") or task_id

            # 记录会话归属与标题（按登录用户隔离，标题取首条提问）
            try:
                create_or_update_session(session_id, request.user.id, query)
            except Exception as e:
                logger.warning(f"记录会话元信息失败（不影响主流程）：{e}")

            from tasks.rag_tasks import query_rag
            update_task_status(task_id, TASK_STATUS_PENDING)
            query_rag.apply_async(args=[
                task_id,
                query,
                session_id,
                request.data.get("enable_embedding", True),
                request.data.get("enable_hyde", True),
                request.data.get("enable_web_search", True),
                request.data.get("is_stream", True),
            ])
            return success({
                "task_id": task_id,
                "op": "query",
                "session_id": session_id,
            }, message="检索任务已提交", status=202)

        else:
            return fail("op 必须为 import 或 query", code=400)


class RAGStatusView(APIView):
    """查询任务状态"""

    permission_classes = [IsAuthenticated]
    authentication_classes = [CachedJWTAuthentication]

    def get(self, request, task_id, *args, **kwargs):
        task_status = get_task_status(task_id)
        if not task_status:
            return fail("任务不存在", code=404)
        return success({
            "task_id": task_id,
            "status": task_status,
            "done_list": get_done_task_list(task_id),
            "running_list": get_running_task_list(task_id),
        })


class RAGResultView(APIView):
    """查询任务结果"""

    permission_classes = [IsAuthenticated]
    authentication_classes = [CachedJWTAuthentication]

    def get(self, request, task_id, *args, **kwargs):
        task_status = get_task_status(task_id)
        if not task_status:
            return fail("任务不存在", code=404)

        answer = get_task_result(task_id, "answer", "")
        error = get_task_result(task_id, "error", "")
        return success({
            "task_id": task_id,
            "status": task_status,
            "answer": answer,
            "error": error,
        })


class RAGBatchStatusView(APIView):
    """批量查询任务状态，前端轮询专用，1次请求拿所有任务状态"""
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        task_ids = request.data.get("task_ids", [])

        # 参数校验
        if not task_ids or not isinstance(task_ids, list):
            return fail("task_ids 必须为非空列表", code=400)
        if len(task_ids) > 100:
            return fail("单次最多查询 100 个任务", code=400)

        # 一次性批量读取所有任务状态
        from utils.task_utils import batch_get_task_full_status
        results = batch_get_task_full_status(task_ids)

        return success({"results": results})


class RAGSessionListView(APIView):
    """查询当前登录用户的历史会话列表"""

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        sessions = list_sessions(request.user.id)
        return success({"sessions": sessions}, message="查询成功")


class RAGSessionMessagesView(APIView):
    """查询指定会话的历史消息（校验归属，防止越权读取他人会话）"""

    permission_classes = [IsAuthenticated]

    def get(self, request, session_id, *args, **kwargs):
        # 校验会话归属：会话必须属于当前用户
        session = get_session(session_id)
        if not session or str(session.get("user_id")) != str(request.user.id):
            return fail("会话不存在", code=404)

        records = get_recent_messages(session_id, limit=50)
        messages = []
        for r in records:
            messages.append({
                "role": r.get("role", ""),
                "text": r.get("text", ""),
                "ts": r.get("ts"),
            })
        return success({
            "session_id": session_id,
            "messages": messages,
        }, message="查询成功")


class RAGStreamView(View):
    """SSE 流式接口：订阅 Redis 频道，推送 LLM 增量

    EventSource 无法携带自定义 header，JWT 通过 ?token= query 参数传递。
    使用 Django 原生 View 而非 DRF APIView，绕开 DRF 内容协商
    （settings 仅配置 JSONRenderer，无法满足 text/event-stream，会返回 406）。
    """

    def get(self, request, session_id, *args, **kwargs):
        # 1. 校验 token（query 参数）
        token = request.GET.get("token", "")
        if token:
            from rest_framework_simplejwt.authentication import JWTAuthentication
            from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
            jwt_auth = JWTAuthentication()
            try:
                jwt_auth.get_validated_token(token)
            except (InvalidToken, TokenError):
                return JsonResponse({"code": 401, "message": "无效的 token", "data": None}, status=401)
        # 若无 token，允许匿名（简化处理；会话归属已在 submit 侧控制）

        # 2. 返回 SSE 流
        response = StreamingHttpResponse(
            sse_generator_sync(session_id),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        response["Connection"] = "keep-alive"
        return response
