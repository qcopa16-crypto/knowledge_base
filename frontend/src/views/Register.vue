<template>
  <div class="auth-page">
    <div class="auth-card">
      <h1 class="auth-title">注册账号</h1>
      <p class="auth-subtitle">创建你的知识库管理平台账号</p>

      <form @submit.prevent="handleRegister">
        <div class="form-group">
          <label for="username">用户名 <span class="required">*</span></label>
          <input
            id="username"
            v-model="form.username"
            type="text"
            placeholder="请输入用户名"
            required
          />
          <p v-if="errors.username" class="error-text">{{ errors.username }}</p>
        </div>

        <div class="form-group">
          <label for="password">密码 <span class="required">*</span></label>
          <input
            id="password"
            v-model="form.password"
            type="password"
            placeholder="至少 6 位"
            required
          />
          <p v-if="errors.password" class="error-text">{{ errors.password }}</p>
        </div>

        <div class="form-group">
          <label for="confirm">确认密码 <span class="required">*</span></label>
          <input
            id="confirm"
            v-model="form.confirm"
            type="password"
            placeholder="再次输入密码"
            required
          />
          <p v-if="errors.confirm" class="error-text">{{ errors.confirm }}</p>
        </div>

        <div class="form-group">
          <label for="real_name">姓名</label>
          <input id="real_name" v-model="form.real_name" type="text" placeholder="请输入真实姓名（选填）" />
        </div>

        <div class="form-group">
          <label for="phone">手机号</label>
          <input id="phone" v-model="form.phone" type="tel" placeholder="请输入手机号（选填）" />
          <p v-if="errors.phone" class="error-text">{{ errors.phone }}</p>
        </div>

        <div class="form-group">
          <label for="email">邮箱</label>
          <input id="email" v-model="form.email" type="email" placeholder="请输入邮箱（选填）" />
          <p v-if="errors.email" class="error-text">{{ errors.email }}</p>
        </div>

        <p v-if="serverError" class="error-text">{{ serverError }}</p>

        <button type="submit" class="submit-btn" :disabled="loading">
          {{ loading ? '注册中...' : '注册' }}
        </button>
      </form>

      <p class="auth-footer">
        已有账号？
        <router-link to="/login">去登录</router-link>
      </p>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { register } from '../api/auth'
import { setToken, setUser } from '../store/auth'

const router = useRouter()

const form = reactive({
  username: '',
  password: '',
  confirm: '',
  real_name: '',
  phone: '',
  email: '',
})

const errors = reactive({})
const serverError = ref('')
const loading = ref(false)

const PHONE_RE = /^1[3-9]\d{9}$/
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

function validate() {
  Object.keys(errors).forEach((k) => delete errors[k])

  if (!form.username.trim()) {
    errors.username = '用户名不能为空'
  }
  if (form.password.length < 6) {
    errors.password = '密码至少 6 位'
  }
  if (form.password !== form.confirm) {
    errors.confirm = '两次输入的密码不一致'
  }
  if (form.phone && !PHONE_RE.test(form.phone)) {
    errors.phone = '手机号格式不正确'
  }
  if (form.email && !EMAIL_RE.test(form.email)) {
    errors.email = '邮箱格式不正确'
  }
  return Object.keys(errors).length === 0
}

async function handleRegister() {
  if (!validate()) return
  loading.value = true
  serverError.value = ''
  try {
    const data = await register({
      username: form.username,
      password: form.password,
      real_name: form.real_name,
      phone: form.phone,
      email: form.email,
    })
    // 注册成功，后端直接返回 token
    setToken(data.access)
    setUser({
      id: data.id,
      username: data.username,
      real_name: data.real_name,
      phone: data.phone,
      email: data.email,
    })
    router.push('/')
  } catch (e) {
    serverError.value = e.message || '注册失败，请稍后重试'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.auth-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  background: linear-gradient(135deg, #e0eafc 0%, #cfdef3 100%);
}

.auth-card {
  background: #fff;
  border-radius: 12px;
  padding: 32px;
  width: 100%;
  max-width: 440px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
}

.auth-title {
  font-size: 20px;
  text-align: center;
  margin-bottom: 4px;
}

.auth-subtitle {
  text-align: center;
  color: var(--text-muted);
  font-size: 14px;
  margin-bottom: 24px;
}

.form-group {
  margin-bottom: 14px;
}

.form-group label {
  display: block;
  margin-bottom: 6px;
  font-size: 14px;
}

.required {
  color: var(--danger);
}

.submit-btn {
  width: 100%;
  padding: 10px;
  font-size: 15px;
  margin-top: 8px;
}

.auth-footer {
  text-align: center;
  margin-top: 16px;
  font-size: 14px;
  color: var(--text-muted);
}
</style>
