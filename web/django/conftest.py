"""pytest 配置与共享 fixture

测试直连外部数据库（MySQL / Redis / MongoDB），不做 SQLite 内存库 mock。
- MySQL：复用 settings 中的 MYSQL_* 环境变量（默认库 kb_platform）
- Redis：utils/redis_utils 直连（任务状态 db2）
- MongoDB：utils/mongo_history_utils 直连（chat_message / chat_session 集合）

测试数据使用可识别前缀，并在 teardown 清理，避免污染真实数据。
"""
import os

# 在加载 Django 前设置 settings 模块
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "kb_platform.settings")

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()

# 测试会话前缀，用于识别并清理测试产生的会话/消息
TEST_SESSION_PREFIX = "test-session-"


def _new_client():
    """创建全新的 APIClient 实例（每次调用都是独立对象）"""
    from rest_framework.test import APIClient
    return APIClient()


@pytest.fixture
def api_client():
    """未认证的 API 客户端"""
    return _new_client()


@pytest.fixture
def admin_user(db):
    """管理员用户（测试专用，teardown 删除）"""
    user = User.objects.create_superuser(
        username="admin", password="admin123456", email="admin@test.com"
    )
    yield user
    user.delete()


@pytest.fixture
def normal_user(db):
    """普通用户（测试专用，teardown 删除）"""
    user = User.objects.create_user(
        username="normal", password="normal123456", email="normal@test.com"
    )
    yield user
    user.delete()


@pytest.fixture
def auth_client(normal_user):
    """已认证（普通用户）的 API 客户端（独立实例）"""
    client = _new_client()
    client.force_authenticate(user=normal_user)
    return client


@pytest.fixture
def admin_client(admin_user):
    """已认证（管理员）的 API 客户端（独立实例）"""
    client = _new_client()
    client.force_authenticate(user=admin_user)
    return client


def _login(client, username, password):
    """通过登录接口获取 JWT 并设置到 client（用于真实 JWT 流程测试）"""
    resp = client.post("/api/auth/login/", {"username": username, "password": password}, format="json")
    assert resp.status_code == 200, resp.data
    token = resp.data["data"]["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.fixture(autouse=True)
def _cleanup_test_sessions():
    """测试结束后清理测试产生的会话/消息，避免污染真实数据库"""
    yield
    try:
        from utils.mongo_history_utils import get_history_mongo_tool
        tool = get_history_mongo_tool()
        tool.chat_message.delete_many({"session_id": {"$regex": f"^{TEST_SESSION_PREFIX}"}})
        tool.chat_session.delete_many({"session_id": {"$regex": f"^{TEST_SESSION_PREFIX}"}})
    except Exception:
        # 清理失败不影响测试结果（如 Mongo 不可达）
        pass
