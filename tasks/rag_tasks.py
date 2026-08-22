"""RAG 任务定义（Celery）

- import_document：入库任务，执行 KBImportWorkflow
- query_rag：检索任务，执行 KBQueryWorkflow

任务执行完成后，将结果投递到结果队列（kb_rag_result），供 Django 消费。
"""
import json

from tool.logger import logger

from tasks.celery_app import celery_app
from utils.sse_utils import SSEEvent, push_close, push_to_session
from utils.task_utils import (
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_PROCESSING,
    add_done_task,
    add_running_task,
    set_task_result,
    update_task_status,
)

RESULT_QUEUE = "kb_rag_result"


def _publish_result(task_id: str, payload: dict):
    """将任务结果投递到结果队列（供 Django 消费）"""
    try:
        with celery_app.producer_pool.acquire(block=True) as producer:
            producer.publish(
                payload,
                serializer="json",
                exchange="kb_rag_exchange",
                routing_key=RESULT_QUEUE,
                declare=[_result_queue_declare()],
            )
        logger.info(f"[{task_id}] 结果已投递到结果队列 {RESULT_QUEUE}")
    except Exception as e:
        logger.error(f"[{task_id}] 结果投递失败: {e}", exc_info=True)


def _result_queue_declare():
    from kombu import Exchange, Queue
    exchange = Exchange("kb_rag_exchange", type="direct", durable=True)
    return Queue(RESULT_QUEUE, exchange=exchange, routing_key=RESULT_QUEUE, durable=True)


@celery_app.task(name="tasks.import_document", bind=True, max_retries=3)
def import_document(self, task_id: str, file_dir: str, import_file_path: str):
    """入库任务：PDF 解析 → 向量化 → Milvus 入库"""
    update_task_status(task_id, TASK_STATUS_PROCESSING)
    try:
        from processor.import_processor.main_graph import KBImportWorkflow

        init_state = {
            "task_id": task_id,
            "file_dir": file_dir,
            "import_file_path": import_file_path,
        }
        workflow = KBImportWorkflow()
        for event in workflow.run(init_state, stream=True):
            if not event or not isinstance(event, dict):
                continue
            for node_name, node_result in event.items():
                # 先标记「正在处理」，再标记「完成」（add_done_task 内部移除同名 running）
                add_running_task(task_id, node_name)
                add_done_task(task_id, node_name)

        update_task_status(task_id, TASK_STATUS_COMPLETED)
        set_task_result(task_id, "status", TASK_STATUS_COMPLETED)
        _publish_result(task_id, {
            "task_id": task_id,
            "status": TASK_STATUS_COMPLETED,
            "type": "import",
        })
        return {"task_id": task_id, "status": TASK_STATUS_COMPLETED}
    except Exception as e:
        logger.error(f"[{task_id}] 入库任务失败: {e}", exc_info=True)
        update_task_status(task_id, TASK_STATUS_FAILED)
        set_task_result(task_id, "error", str(e))
        _publish_result(task_id, {
            "task_id": task_id,
            "status": TASK_STATUS_FAILED,
            "type": "import",
            "error": str(e),
        })
        # 失败重试
        raise self.retry(exc=e, countdown=5)


@celery_app.task(name="tasks.query_rag", bind=True, max_retries=3)
def query_rag(
    self,
    task_id: str,
    query: str,
    session_id: str = None,
    enable_embedding: bool = True,
    enable_hyde: bool = True,
    enable_web_search: bool = True,
    is_stream: bool = True,
):
    """检索任务：语义检索 → RRF → Reranker → 生成答案"""
    update_task_status(task_id, TASK_STATUS_PROCESSING)
    try:
        from processor.query_processor.main_graph import KBQueryWorkflow

        init_state = {
            "original_query": query,
            "session_id": session_id or task_id,
            "is_stream": is_stream,
            "enable_embedding": enable_embedding,
            "enable_hyde": enable_hyde,
            "enable_web_search": enable_web_search,
        }
        workflow = KBQueryWorkflow()
        final_state = workflow.run(init_state, stream=False)

        answer = final_state.get("answer", "") if isinstance(final_state, dict) else ""
        update_task_status(task_id, TASK_STATUS_COMPLETED)
        set_task_result(task_id, "answer", answer)
        _publish_result(task_id, {
            "task_id": task_id,
            "status": TASK_STATUS_COMPLETED,
            "type": "query",
            "answer": answer,
        })
        # 流式场景：推送最终答案 + 关闭信号，让前端 SSE 正常结束
        if is_stream:
            push_to_session(session_id or task_id, SSEEvent.FINAL, {"answer": answer})
            push_close(session_id or task_id)
        return {"task_id": task_id, "status": TASK_STATUS_COMPLETED, "answer": answer}
    except Exception as e:
        logger.error(f"[{task_id}] 检索任务失败: {e}", exc_info=True)
        update_task_status(task_id, TASK_STATUS_FAILED)
        set_task_result(task_id, "error", str(e))
        _publish_result(task_id, {
            "task_id": task_id,
            "status": TASK_STATUS_FAILED,
            "type": "query",
            "error": str(e),
        })
        # 流式场景：推送错误 + 关闭信号
        if is_stream:
            push_to_session(session_id or task_id, SSEEvent.ERROR, {"error": str(e)})
            push_close(session_id or task_id)
        raise self.retry(exc=e, countdown=5)
