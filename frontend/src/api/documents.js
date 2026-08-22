import request from './request'

// 文档列表（支持多条件过滤 + 搜索）
export function getDocuments(params) {
  return request.get('/documents/documents/', { params })
}

// 文档详情
export function getDocument(id) {
  return request.get(`/documents/documents/${id}/`)
}

// 新增文档
export function createDocument(data) {
  return request.post('/documents/documents/', data)
}

// 更新文档
export function updateDocument(id, data) {
  return request.patch(`/documents/documents/${id}/`, data)
}

// 删除文档
export function deleteDocument(id) {
  return request.delete(`/documents/documents/${id}/`)
}

// 热门文档
export function getHotDocuments(limit = 10) {
  return request.get('/documents/documents/hot/', { params: { limit } })
}
