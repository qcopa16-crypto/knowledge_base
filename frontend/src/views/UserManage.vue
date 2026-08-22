<template>
  <div class="page">
    <div class="toolbar">
      <el-input
        v-model="search"
        placeholder="搜索用户名 / 姓名 / 手机号"
        class="search-input"
        clearable
        @keyup.enter="handleSearch"
        @clear="handleSearch"
      >
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-button type="primary" @click="handleSearch"><el-icon><Search /></el-icon>&nbsp;搜索</el-button>
      <el-button @click="handleReset">重置</el-button>
      <div class="spacer"></div>
      <el-button v-if="isAdmin" type="primary" @click="openCreate"><el-icon><Plus /></el-icon>&nbsp;新增用户</el-button>
    </div>

    <el-table v-loading="loading" :data="users" stripe border class="data-table">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="username" label="用户名" min-width="140" />
      <el-table-column prop="real_name" label="姓名" width="120" />
      <el-table-column prop="phone" label="手机号" width="140" />
      <el-table-column prop="email" label="邮箱" min-width="180" />
      <el-table-column label="角色" width="120">
        <template #default="{ row }">
          <el-tag v-if="row.is_superuser" type="danger">超级管理员</el-tag>
          <el-tag v-else-if="row.is_staff" type="warning">管理员</el-tag>
          <el-tag v-else type="info">普通用户</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'info'">
            {{ row.is_active ? '启用' : '停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column v-if="isAdmin" label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination">
      <el-pagination
        background
        layout="total, prev, pager, next"
        :total="total"
        :current-page="page"
        :page-size="pageSize"
        @current-change="handlePageChange"
      />
    </div>

    <el-dialog
      v-model="dialogVisible"
      :title="form.id ? '编辑用户' : '新增用户'"
      width="520px"
      @closed="resetForm"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" :disabled="!!form.id" placeholder="用户名" />
        </el-form-item>
        <el-form-item label="密码" :prop="form.id ? '' : 'password'">
          <el-input
            v-model="form.password"
            type="password"
            :placeholder="form.id ? '留空则不修改密码' : '至少 6 位'"
            show-password
          />
        </el-form-item>
        <el-form-item label="姓名">
          <el-input v-model="form.real_name" placeholder="真实姓名" />
        </el-form-item>
        <el-form-item label="手机号">
          <el-input v-model="form.phone" placeholder="手机号" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="form.email" placeholder="邮箱" />
        </el-form-item>
        <el-form-item label="管理员">
          <el-switch v-model="form.is_staff" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getUsers, createUser, updateUser, deleteUser } from '../api/accounts'
import { authState } from '../store/auth'

const isAdmin = computed(() => authState.user?.is_staff || authState.user?.is_superuser)

const users = ref([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const search = ref('')

const dialogVisible = ref(false)
const saving = ref(false)
const formRef = ref(null)

const form = reactive({
  id: null,
  username: '',
  password: '',
  real_name: '',
  phone: '',
  email: '',
  is_staff: false,
  is_active: true,
})

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少 6 位', trigger: 'blur' },
  ],
}

async function loadUsers() {
  loading.value = true
  const params = { page: page.value, page_size: pageSize.value }
  if (search.value) params.search = search.value
  try {
    const data = await getUsers(params)
    users.value = data.results || []
    total.value = data.count || 0
  } catch (e) {
    ElMessage.error(e.message || '加载用户失败')
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  page.value = 1
  loadUsers()
}

function handleReset() {
  search.value = ''
  page.value = 1
  loadUsers()
}

function handlePageChange(p) {
  page.value = p
  loadUsers()
}

function openCreate() {
  resetForm()
  dialogVisible.value = true
}

function openEdit(row) {
  Object.assign(form, {
    id: row.id,
    username: row.username,
    password: '',
    real_name: row.real_name,
    phone: row.phone,
    email: row.email,
    is_staff: row.is_staff,
    is_active: row.is_active,
  })
  dialogVisible.value = true
}

function resetForm() {
  Object.assign(form, {
    id: null,
    username: '',
    password: '',
    real_name: '',
    phone: '',
    email: '',
    is_staff: false,
    is_active: true,
  })
  formRef.value?.clearValidate()
}

async function handleSave() {
  await formRef.value.validate()
  saving.value = true
  const payload = {
    real_name: form.real_name,
    phone: form.phone,
    email: form.email,
    is_staff: form.is_staff,
    is_active: form.is_active,
  }
  if (!form.id) payload.username = form.username
  if (form.password) payload.password = form.password
  try {
    if (form.id) {
      await updateUser(form.id, payload)
      ElMessage.success('更新成功')
    } else {
      await createUser(payload)
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    loadUsers()
  } catch (e) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

function handleDelete(row) {
  ElMessageBox.confirm(`确定删除用户「${row.username}」吗？`, '删除确认', {
    type: 'warning',
    confirmButtonText: '删除',
    cancelButtonText: '取消',
  })
    .then(async () => {
      await deleteUser(row.id)
      ElMessage.success('删除成功')
      loadUsers()
    })
    .catch(() => {})
}

onMounted(loadUsers)
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  background: #fff;
  padding: 16px;
  border-radius: 8px;
}

.search-input {
  width: 240px;
}

.spacer {
  flex: 1;
}

.data-table {
  background: #fff;
  border-radius: 8px;
}

.pagination {
  display: flex;
  justify-content: flex-end;
  background: #fff;
  padding: 16px;
  border-radius: 8px;
}
</style>
