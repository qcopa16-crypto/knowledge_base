"""任务状态追踪（Redis 持久化版本）

将原本的单进程内存字典迁移为 Redis，支持跨进程共享（Django 与 FastAPI worker 均可读写）。
保持所有对外函数签名不变，现有调用方无需改动。

Redis key 结构（hash）：
    kb:task:{task_id} -> {
        status:   str（pending/processing/completed/failed）
        running:  json 数组（运行中节点英文名）
        done:     json 数组（已完成节点英文名）
        result:   json 对象（结果字段，如 answer / error）
    }
"""
import json
from typing import Dict, List

from .sse_utils import push_to_session
from .redis_utils import get_task_state_client

# 任务状态常量
TASK_STATUS_PENDING = "pending"
TASK_STATUS_PROCESSING = "processing"
TASK_STATUS_COMPLETED = "completed"
TASK_STATUS_FAILED = "failed"

# Redis key 前缀
_KEY_PREFIX = "kb:task:"

# 节点名 -> 中文名映射（用于前端展示）
_NODE_NAME_TO_CN: Dict[str, str] = {
    "upload_file": "开始上传文件",
    "node_entry": "检查文件",
    "node_pdf_to_md": "PDF转Markdown",
    "node_md_img": "Markdown图片处理",
    "node_item_name_recognition": "主体名称识别",
    "node_document_split": "文档切分",
    "node_bge_embedding": "向量生成",
    "node_import_milvus": "导入向量库",
    "__end__": "处理完成",
    "END": "处理完成",
    "node_item_name_confirm": "确认问题产品",
    "node_answer_output": "生成答案",
    "node_rerank": "重排序",
    "node_rrf": "倒排融合",
    "node_web_search_mcp": "网络搜索",
    "node_search_embedding": "切片搜索",
    "node_search_embedding_hyde": "切片搜索(假设性文档)",
    "node_multi_search": "多路搜索",
    "node_join": "多路搜索合并",
}


def _client():
    """获取任务状态 Redis 客户端"""
    return get_task_state_client()


def _key(task_id: str) -> str:
    return f"{_KEY_PREFIX}{task_id}"


def _to_cn(node_name: str) -> str:
    return _NODE_NAME_TO_CN.get(node_name, node_name)


def _get_list(task_id: str, field: str) -> List[str]:
    """从 Redis hash 读取某个 json 数组字段"""
    raw = _client().hget(_key(task_id), field)
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _set_list(task_id: str, field: str, items: List[str]) -> None:
    _client().hset(_key(task_id), field, json.dumps(items, ensure_ascii=False))


def _to_cn_list(items: List[str]) -> List[str]:
    return [_to_cn(n) for n in items]


def add_running_task(task_id: str, node_name: str, is_stream: bool = False) -> None:
    """添加“正在运行”的节点任务"""
    running = _get_list(task_id, "running")
    if node_name not in running:
        running.append(node_name)
        _set_list(task_id, "running", running)
    if is_stream:
        task_push_queue(task_id)


def add_done_task(task_id: str, node_name: str, is_stream: bool = False) -> None:
    """添加“已完成”的节点任务，并移除同名的运行中节点"""
    running = [n for n in _get_list(task_id, "running") if n != node_name]
    _set_list(task_id, "running", running)

    done = _get_list(task_id, "done")
    if node_name not in done:
        done.append(node_name)
        _set_list(task_id, "done", done)

    if is_stream:
        task_push_queue(task_id)


def set_task_result(task_id: str, key: str, value: str) -> None:
    """存储任务结果字段（如 answer / error）"""
    raw = _client().hget(_key(task_id), "result")
    result: Dict = {}
    if raw:
        try:
            result = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            result = {}
    result[key] = value
    _client().hset(_key(task_id), "result", json.dumps(result, ensure_ascii=False))


def get_task_result(task_id: str, key: str, default: str = "") -> str:
    """获取任务结果字段"""
    raw = _client().hget(_key(task_id), "result")
    if not raw:
        return default
    try:
        result = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default
    return result.get(key, default)


def get_task_status(task_id: str) -> str:
    """获取当前任务状态"""
    return _client().hget(_key(task_id), "status") or ""


def get_done_task_list(task_id: str) -> List[str]:
    """获取已完成节点列表（中文展示）"""
    return _to_cn_list(_get_list(task_id, "done"))


def get_running_task_list(task_id: str) -> List[str]:
    """获取正在运行节点列表（中文展示）"""
    return _to_cn_list(_get_list(task_id, "running"))


def update_task_status(task_id: str, status_name: str, push_queue: bool = False) -> None:
    """更新任务状态"""
    _client().hset(_key(task_id), "status", status_name)
    if push_queue:
        task_push_queue(task_id)


def task_push_queue(task_id: str):
    """推送进度事件（SSE，仅流式场景使用）"""
    push_to_session(task_id, "progress", {
        "status": get_task_status(task_id),
        "done_list": get_done_task_list(task_id),
        "running_list": get_running_task_list(task_id),
    })


def clear_task(task_id: str):
    """清空任务的所有状态"""
    _client().delete(_key(task_id))


def batch_get_task_full_status(task_ids):
    """
    批量获取任务完整状态
    基于现有 Hash 结构，使用 pipeline 批量读取，仅 1 次 Redis 网络往返
    返回格式与单查询接口完全一致，前端无感知
    """
    if not task_ids:
        return {}

    task_ids = list(set(task_ids))
    pipe = _client().pipeline()

    # 批量入队：每个任务一次性读取 status / running / done 三个字段
    for task_id in task_ids:
        pipe.hmget(_key(task_id), "status", "running", "done")

    # 一次性执行所有命令
    results_raw = pipe.execute()

    results = {}
    for idx, task_id in enumerate(task_ids):
        status_raw, running_raw, done_raw = results_raw[idx]

        # 任务不存在则跳过
        if not status_raw:
            continue

        # 解析 JSON 数组并转中文
        try:
            running_list = json.loads(running_raw) if running_raw else []
        except (json.JSONDecodeError, TypeError):
            running_list = []

        try:
            done_list = json.loads(done_raw) if done_raw else []
        except (json.JSONDecodeError, TypeError):
            done_list = []

        results[task_id] = {
            "task_id": task_id,
            "status": status_raw,
            "done_list": _to_cn_list(done_list),
            "running_list": _to_cn_list(running_list),
        }

    return results
