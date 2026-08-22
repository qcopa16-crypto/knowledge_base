"""真实 PDF 入库端到端冒烟脚本（独立运行，可选）

用途：用指定 PDF 做一次完整的入库冒烟验证，观察各处理节点的真实进度。

前置条件：
1. 已启动外部依赖：Milvus / MongoDB / MinIO / Redis / RabbitMQ
2. 已启动 Celery worker（gevent 并发）
3. 已启动 Django（8000）

运行方式（conda 环境）：
    conda activate shopkeeper-ai
    python test/integration_import.py
"""

import os
import sys
import time

# 指定测试 PDF
TEST_PDF = r"E:\doc\Aolynk CB304n Cable网桥 用户手册-5W100-整本手册.pdf"

# Django 服务地址（默认本地）
BASE_URL = os.getenv("RAG_BASE_URL", "http://127.0.0.1:8000")


def upload_and_poll(pdf_path: str):
    """上传单个 PDF 并轮询状态，打印各节点进度"""
    import requests

    if not os.path.exists(pdf_path):
        print(f"[错误] 测试 PDF 不存在：{pdf_path}")
        sys.exit(1)

    # 1. 登录获取 token
    login_resp = requests.post(
        f"{BASE_URL}/api/auth/login/",
        json={"username": "admin", "password": "admin123456"},
    )
    if login_resp.status_code != 200:
        print(f"[错误] 登录失败：{login_resp.status_code} {login_resp.text}")
        sys.exit(1)
    token = login_resp.json()["data"]["access"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. 上传文件
    with open(pdf_path, "rb") as f:
        upload_resp = requests.post(
            f"{BASE_URL}/api/rag/upload/",
            files={"files": (os.path.basename(pdf_path), f, "application/pdf")},
            headers=headers,
        )
    if upload_resp.status_code != 202:
        print(f"[错误] 上传失败：{upload_resp.status_code} {upload_resp.text}")
        sys.exit(1)

    data = upload_resp.json()["data"]
    files = data["files"]
    skipped = data["skipped"]
    print(f"[信息] 已提交 {len(files)} 个文件，跳过 {len(skipped)} 个")
    if not files:
        print(f"[信息] 跳过详情：{skipped}")
        sys.exit(1)

    task_id = files[0]["task_id"]
    print(f"[信息] task_id = {task_id}")

    # 3. 轮询状态，观察节点进度
    deadline = time.time() + 600
    last_running = None
    while time.time() < deadline:
        status_resp = requests.get(
            f"{BASE_URL}/api/rag/status/{task_id}/", headers=headers
        )
        st = status_resp.json()["data"]
        status = st["status"]
        running = st.get("running_list", [])
        done = st.get("done_list", [])

        if running != last_running:
            print(f"[进度] 状态={status} 正在处理={running or '无'} 已完成={done}")
            last_running = running

        if status in ("completed", "failed"):
            print(f"[结果] 最终状态={status} 已完成节点={done}")
            if status == "failed":
                sys.exit(1)
            print("[成功] PDF 入库完成")
            return
        time.sleep(3)

    print("[错误] 入库超时")
    sys.exit(1)


if __name__ == "__main__":
    upload_and_poll(TEST_PDF)
