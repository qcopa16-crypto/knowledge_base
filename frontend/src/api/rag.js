import request from './request'
import {authState} from '../store/auth'

// 提交 RAG 任务（op=import/query）
export function submitRAG(data) {
    return request.post('/rag/submit/', data)
}

// 构造 SSE 流式地址（EventSource 无法带自定义 header，token 通过 query 参数传递）
export function getStreamUrl(sessionId) {
    const token = authState.token || ''
    return `/api/rag/stream/${sessionId}/?token=${encodeURIComponent(token)}`
}

// 查询任务状态
export function getRAGStatus(taskId) {
    return request.get(`/rag/status/${taskId}/`)
}

// 查询任务结果
export function getRAGResult(taskId) {
    return request.get(`/rag/result/${taskId}/`)
}

// 上传文档（触发入库任务）
export function uploadDocument(file, extra = {}) {
    const formData = new FormData()
    formData.append('file', file)
    Object.entries(extra).forEach(([k, v]) => formData.append(k, v))
    return request.post('/rag/upload/', formData, {
        headers: {'Content-Type': 'multipart/form-data'},
    })
}

// 多文件上传（一次上传多个文件，字段名 files）
export function uploadDocuments(files, extra = {}) {
    const formData = new FormData()
    files.forEach((file) => formData.append('files', file))
    Object.entries(extra).forEach(([k, v]) => formData.append(k, v))
    return request.post('/rag/upload/', formData, {
        headers: {'Content-Type': 'multipart/form-data'},
    })
}

// 历史会话列表
export function listSessions() {
    return request.get('/rag/sessions/')
}

// 会话历史消息
export function getSessionMessages(sessionId) {
    return request.get(`/rag/sessions/${sessionId}/messages/`)
}

export function batchGetRAGStatus(taskIds) {
    return request({
        url: '/api/rag/status/batch/',
        method: 'post',
        data: {task_ids: taskIds}
    })
}
