import axios from 'axios'
import { authState, clearAuth } from '../store/auth'
import router from '../router'

// 将 Axios 原生英文错误信息汉化为中文
function normalizeErrorMessage(error) {
  const status = error.response?.status
  const backendMessage = error.response?.data?.message

  // 优先使用后端返回的中文 message
  if (backendMessage) {
    return backendMessage
  }

  const raw = error.message || ''

  // 请求失败，状态码：500 -> 请求失败，状态码：500
  const statusMatch = raw.match(/Request failed with status code (\d+)/)
  if (statusMatch) {
    return `请求失败，状态码：${statusMatch[1]}`
  }

  // 网络连接失败
  if (/Network Error/i.test(raw)) {
    return '网络连接失败，请检查网络或服务是否启动'
  }

  // 请求超时
  if (/timeout/i.test(raw)) {
    return '请求超时，请稍后重试'
  }

  // 有状态码但无后端 message 的兜底
  if (status) {
    return `请求失败，状态码：${status}`
  }

  // 最终兜底
  return '请求失败'
}

// 统一请求实例
const instance = axios.create({
  baseURL: '/api',
  timeout: 15000,
})

// 请求拦截器：注入 token
instance.interceptors.request.use((config) => {
  if (authState.token) {
    config.headers.Authorization = `Bearer ${authState.token}`
  }
  return config
})

// 响应拦截器：统一处理 {code, message, data}
instance.interceptors.response.use(
  (response) => {
    const data = response.data
    // 后端统一格式 {code, message, data}
    if (data && typeof data.code !== 'undefined') {
      if (data.code === 0) {
        return data.data
      }
      // 业务错误
      return Promise.reject(new Error(data.message || '请求失败'))
    }
    // 非统一格式，直接返回
    return data
  },
  (error) => {
    const status = error.response?.status
    if (status === 401) {
      // token 失效，清除并跳转登录
      clearAuth()
      if (router.currentRoute.value.path !== '/login') {
        router.push('/login')
      }
    }
    // 提取后端错误信息，并汉化 Axios 原生英文错误
    const message = normalizeErrorMessage(error)
    return Promise.reject(new Error(message))
  }
)

export default instance
