<template>
  <div class="profile">
    <div class="card profile-card">
      <h2 class="profile-title">个人中心</h2>

      <div v-if="loading" class="loading">加载中...</div>

      <template v-else-if="user">
        <form @submit.prevent="handleSave">
          <div class="form-group">
            <label>用户名</label>
            <input :value="user.username" disabled />
            <p class="hint">用户名不可修改</p>
          </div>

          <div class="form-group">
            <label>姓名</label>
            <input v-model="form.real_name" type="text" placeholder="请输入真实姓名" />
          </div>

          <div class="form-group">
            <label>手机号</label>
            <input v-model="form.phone" type="tel" placeholder="请输入手机号" />
            <p v-if="errors.phone" class="error-text">{{ errors.phone }}</p>
          </div>

          <div class="form-group">
            <label>邮箱</label>
            <input v-model="form.email" type="email" placeholder="请输入邮箱" />
            <p v-if="errors.email" class="error-text">{{ errors.email }}</p>
          </div>

          <p v-if="saveSuccess" class="success-text">保存成功</p>
          <p v-if="saveError" class="error-text">{{ saveError }}</p>

          <div class="btn-row">
            <button type="submit" :disabled="saving">
              {{ saving ? '保存中...' : '保存修改' }}
            </button>
          </div>
        </form>
      </template>

      <div v-else class="error-text">无法加载用户信息</div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { getMe, updateMe } from '../api/auth'
import { setUser, authState } from '../store/auth'

const user = ref(null)
const loading = ref(true)
const saving = ref(false)
const saveSuccess = ref(false)
const saveError = ref('')

const form = reactive({
  real_name: '',
  phone: '',
  email: '',
})

const errors = reactive({})

const PHONE_RE = /^1[3-9]\d{9}$/
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

async function loadProfile() {
  loading.value = true
  try {
    const data = await getMe()
    user.value = data
    form.real_name = data.real_name || ''
    form.phone = data.phone || ''
    form.email = data.email || ''
    setUser(data)
  } catch (e) {
    saveError.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

function validate() {
  Object.keys(errors).forEach((k) => delete errors[k])
  if (form.phone && !PHONE_RE.test(form.phone)) {
    errors.phone = '手机号格式不正确'
  }
  if (form.email && !EMAIL_RE.test(form.email)) {
    errors.email = '邮箱格式不正确'
  }
  return Object.keys(errors).length === 0
}

async function handleSave() {
  if (!validate()) return
  saving.value = true
  saveSuccess.value = false
  saveError.value = ''
  try {
    const data = await updateMe({
      real_name: form.real_name,
      phone: form.phone,
      email: form.email,
    })
    setUser(data)
    saveSuccess.value = true
  } catch (e) {
    saveError.value = e.message || '保存失败'
  } finally {
    saving.value = false
  }
}

onMounted(loadProfile)
</script>

<style scoped>
.profile-card {
  max-width: 560px;
  margin: 0 auto;
}

.profile-title {
  font-size: 18px;
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border);
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  margin-bottom: 6px;
  font-size: 14px;
}

.form-group input:disabled {
  background: #f5f5f5;
  color: var(--text-muted);
}

.hint {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 4px;
}

.success-text {
  color: var(--success);
  font-size: 13px;
}

.btn-row {
  margin-top: 8px;
}

.loading {
  text-align: center;
  color: var(--text-muted);
  padding: 20px 0;
}
</style>
