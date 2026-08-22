import request from './request'

// 用户列表
export function getUsers(params) {
  return request.get('/accounts/users/', { params })
}

// 新增用户
export function createUser(data) {
  return request.post('/accounts/users/', data)
}

// 更新用户
export function updateUser(id, data) {
  return request.patch(`/accounts/users/${id}/`, data)
}

// 删除用户
export function deleteUser(id) {
  return request.delete(`/accounts/users/${id}/`)
}
