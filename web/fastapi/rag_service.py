"""合并后的单一 RAG 服务（入库 + 检索）

统一运行在 8080 端口，提供：
- 统一入口 POST /api/rag/（op=import/query 分发）
- 兼容路径 /upload、/query、/status/{task_id}、/stream/{session_id}、/history/{session_id}、/health
- 入库/检索实际执行通过 Celery 任务投递到 RabbitMQ，由 worker 异步消费
"""
from datetime import datetime
import os
import shutil
import uuid
from typing import List

from fastapi import FastAPI, BackgroundTasks, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request

from config.minio_config import minio_config
from tool.logger import logger
from utils.minio_utils import get_minio_client
from utils.mongo_history_utils import get_recent_messages, clear_history
from utils.sse_utils import create_sse_queue, sse_generator
from utils.task_utils import (
    add_running_task,
    add_done_task,
    get_task_status,
    get_done_task_list,
    get_running_task_list,
    update_task_status,
    get_task_result,
    TASK_STATUS_PROCESSING,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
)

app = FastAPI(
    title="掌柜智库 - RAG 服务",
    description="合并入库与检索的单一 RAG 服务（8080）"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# 统一入口：POST /api/rag/
# ---------------------------------------------------------------------------
class RAGRequest(BaseModel):
    op: str = Field(..., description="操作类型：import / query")
    # import 参数
    file_dir: str = Field(None, description="文件目录")
    import_file_path: str = Field(None, description="文件路径")
    # query 参数
    query: str = Field(None, description="查询内容")
    session_id: str = Field(None, description="会话ID")
    enable_embedding: bool = Field(True)
    enable_hyde: bool = Field(True)
    enable_web_search: bool = Field(True)


@app.post("/api/rag/")
async def rag_unified(request: RAGRequest):
    """统一 RAG 入口：根据 op 分发到入库或检索，投递 Celery 任务后立即返回 task_id"""
    task_id = str(uuid.uuid4())

    if request.op == "import":
        if not request.import_file_path:
            raise HTTPException(status_code=400, detail="import 操作需要 import_file_path")
        from tasks.rag_tasks import import_document
        # 投递 Celery 任务（异步，由 worker 消费执行）
        import_document.apply_async(args=[task_id, request.file_dir or "", request.import_file_path])
        return {"code": 0, "message": "入库任务已提交", "data": {"task_id": task_id, "op": "import"}}

    elif request.op == "query":
        if not request.query:
            raise HTTPException(status_code=400, detail="query 操作需要 query")
        from tasks.rag_tasks import query_rag
        query_rag.apply_async(args=[
            task_id,
            request.query,
            request.session_id or task_id,
            request.enable_embedding,
            request.enable_hyde,
            request.enable_web_search,
        ])
        return {"code": 0, "message": "检索任务已提交", "data": {"task_id": task_id, "op": "query"}}

    else:
        raise HTTPException(status_code=400, detail="op 必须为 import 或 query")


# ---------------------------------------------------------------------------
# 兼容路径：入库
# ---------------------------------------------------------------------------
@app.post("/upload")
async def upload_files(background_tasks: BackgroundTasks, files: List[UploadFile] = File(...)):
    """多文件上传（兼容原 import_service），投递 Celery 入库任务"""
    data_based_root_dir = os.getenv("DATA_BASED_ROOT_DIR")
    data_dir = os.path.join(data_based_root_dir, datetime.now().strftime("%Y%m%d"))
    task_ids = []

    for file in files:
        task_id = str(uuid.uuid4())
        task_ids.append(task_id)
        logger.info(f"[{task_id}] 开始处理上传文件：{file.filename}")

        add_running_task(task_id, "upload_file")

        file_dir = os.path.join(data_dir, task_id)
        os.makedirs(file_dir, exist_ok=True)
        import_file_path = os.path.join(file_dir, file.filename)

        with open(import_file_path, "wb") as file_buffer:
            shutil.copyfileobj(file.file, file_buffer)

        # 上传 MinIO（失败不阻断）
        try:
            minio_client = get_minio_client()
            minio_object_name = f"pdf_files/{datetime.now().strftime('%Y%m%d')}/{file.filename}"
            minio_client.fput_object(
                bucket_name=minio_config.bucket_name,
                object_name=minio_object_name,
                file_path=import_file_path,
                content_type=file.content_type,
            )
        except Exception as e:
            logger.warning(f"[{task_id}] MinIO 上传失败：{e}", exc_info=True)

        add_done_task(task_id, "upload_file")

        # 投递 Celery 入库任务（异步）
        from tasks.rag_tasks import import_document
        import_document.apply_async(args=[task_id, file_dir, import_file_path])

    return {"code": 200, "message": f"文件上传成功, total: {len(files)}", "task_ids": task_ids}


@app.get("/status/{task_id}")
async def get_task_progress(task_id: str):
    """任务状态查询（兼容原 import_service）"""
    return {
        "code": 200,
        "task_id": task_id,
        "status": get_task_status(task_id),
        "done_list": get_done_task_list(task_id),
        "running_list": get_running_task_list(task_id),
    }


# ---------------------------------------------------------------------------
# 兼容路径：检索
# ---------------------------------------------------------------------------
class QueryRequest(BaseModel):
    query: str = Field(..., description="查询内容")
    session_id: str = Field(None, description="会话ID")
    is_stream: bool = Field(False, description="是否流式返回")
    enable_embedding: bool = Field(True)
    enable_hyde: bool = Field(True)
    enable_web_search: bool = Field(True)


@app.post("/query")
async def query(request: QueryRequest):
    """检索接口（兼容原 query_service），投递 Celery 检索任务"""
    session_id = request.session_id or str(uuid.uuid4())
    task_id = str(uuid.uuid4())

    if request.is_stream:
        create_sse_queue(session_id)
    update_task_status(session_id, TASK_STATUS_PROCESSING, request.is_stream)

    from tasks.rag_tasks import query_rag
    query_rag.apply_async(args=[
        task_id, request.query, session_id,
        request.enable_embedding, request.enable_hyde, request.enable_web_search,
    ])

    if request.is_stream:
        return {"message": "结果正在处理中...", "session_id": session_id, "task_id": task_id}
    else:
        return {"message": "处理中...", "session_id": session_id, "task_id": task_id}


@app.get("/stream/{session_id}")
async def stream(session_id: str, request: Request):
    """SSE 流式返回"""
    return StreamingResponse(
        sse_generator(session_id, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.delete("/history/{session_id}")
async def clear_chat_history(session_id: str):
    count = clear_history(session_id)
    return {"message": "历史会话已清空", "deleted_count": count}


@app.get("/history/{session_id}")
async def history(session_id: str, limit: int = 50):
    try:
        records = get_recent_messages(session_id, limit=limit)
        items = []
        for r in records:
            items.append({
                "_id": str(r.get("_id")) if r.get("_id") is not None else "",
                "session_id": r.get("session_id", ""),
                "role": r.get("role", ""),
                "text": r.get("text", ""),
                "rewritten_query": r.get("rewritten_query", ""),
                "item_names": r.get("item_names", []),
                "ts": r.get("ts"),
            })
        return {"session_id": session_id, "items": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"history error: {e}")


@app.get("/health")
async def health():
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    # 多 worker 提升并发接收能力（重活已投递 Celery，此处仅需快速接收请求）
    workers = int(os.getenv("FASTAPI_WORKERS", "1"))
    uvicorn.run(app=app, host="127.0.0.1", port=8080, workers=workers)
