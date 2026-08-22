"""用户管理接口测试"""
import pytest


@pytest.mark.django_db
def test_list_users_requires_admin(auth_client):
    resp = auth_client.get("/api/accounts/users/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_list_users_as_admin(admin_client, admin_user, normal_user):
    resp = admin_client.get("/api/accounts/users/")
    assert resp.status_code == 200
    assert resp.data["code"] == 0
    usernames = {u["username"] for u in resp.data["data"]["results"]}
    assert "admin" in usernames
    assert "normal" in usernames


@pytest.mark.django_db
def test_create_user_success(admin_client):
    resp = admin_client.post(
        "/api/accounts/users/",
        {"username": "alice", "password": "alice123456", "real_name": "Alice"},
        format="json",
    )
    assert resp.status_code == 201
    assert resp.data["code"] == 0
    assert resp.data["data"]["username"] == "alice"


@pytest.mark.django_db
def test_create_user_missing_password(admin_client):
    resp = admin_client.post(
        "/api/accounts/users/",
        {"username": "bob"},
        format="json",
    )
    assert resp.status_code == 400
    assert resp.data["code"] == 400
    assert "password" in resp.data["data"]


@pytest.mark.django_db
def test_create_user_duplicate_username(admin_client, admin_user):
    resp = admin_client.post(
        "/api/accounts/users/",
        {"username": "admin", "password": "admin123456"},
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_create_user_short_password(admin_client):
    resp = admin_client.post(
        "/api/accounts/users/",
        {"username": "carol", "password": "123"},
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_update_user(admin_client, normal_user):
    resp = admin_client.patch(
        f"/api/accounts/users/{normal_user.id}/",
        {"real_name": "张三"},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["data"]["real_name"] == "张三"


@pytest.mark.django_db
def test_delete_user(admin_client, normal_user):
    resp = admin_client.delete(f"/api/accounts/users/{normal_user.id}/")
    assert resp.status_code == 200
    assert resp.data["code"] == 0


@pytest.mark.django_db
def test_get_nonexistent_user_404(admin_client):
    resp = admin_client.get("/api/accounts/users/999999/")
    assert resp.status_code == 404
    assert resp.data["code"] == 404
