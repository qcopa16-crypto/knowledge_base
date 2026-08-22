import { reactive } from 'vue'

const TOKEN_KEY = 'kb_token'
const USER_KEY = 'kb_user'

// 轻量认证状态（基于 localStorage 持久化 + 响应式）
export const authState = reactive({
  token: localStorage.getItem(TOKEN_KEY) || '',
  user: JSON.parse(localStorage.getItem(USER_KEY) || 'null'),
})

export function setToken(token) {
  authState.token = token
  localStorage.setItem(TOKEN_KEY, token)
}

export function setUser(user) {
  authState.user = user
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function clearAuth() {
  authState.token = ''
  authState.user = null
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

export function isAuthenticated() {
  return !!authState.token
}
