<template>
  <div class="page">
    <div class="toolbar">
      <el-input
        v-model="search"
        placeholder="搜索分类名称 / 编码"
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
      <el-button v-if="isAdmin" type="primary" @click="openCreate"><el-icon><Plus /></el-icon>&nbsp;新增分类</el-button>
    </div>

    <el-table v-loading="loading" :data="categories" stripe border class="data-table">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="name" label="分类名称" min-width="180" />
      <el-table-column prop="code" label="编码" width="160" />
      <el-table-column prop="level" label="层级" width="80" />
      <el-table-column prop="sort_order" label="排序" width="80" />
      <el-table-column label="上级分类" width="160">
        <template #default="{ row }">{{ parentName(row.parent) }}</template>
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
      :title="form.id ? '编辑分类' : '新增分类'"
      width="480px"
      @closed="resetForm"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="分类名称" />
        </el-form-item>
        <el-form-item label="编码" prop="code">
          <el-input v-model="form.code" placeholder="分类编码" />
        </el-form-item>
        <el-form-item label="上级分类">
          <el-select v-model="form.parent" placeholder="无（顶级分类）" clearable style="width: 100%">
            <el-option
              v-for="c in categories"
              :key="c.id"
              :label="c.name"
              :value="c.id"
              :disabled="c.id === form.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.sort_order" :min="0" />
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
import { getCategories, createCategory, updateCategory, deleteCategory } from '../api/catalog'
import { authState } from '../store/auth'

const isAdmin = computed(() => authState.user?.is_staff || authState.user?.is_superuser)

const categories = ref([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const search = ref('')

const dialogVisible = ref(false)
const saving = ref(false)
const formRef = ref(null)

const form = reactive({ id: null, name: '', code: '', parent: null, sort_order: 0 })

const rules = {
  name: [{ required: true, message: '请输入分类名称', trigger: 'blur' }],
  code: [{ required: true, message: '请输入分类编码', trigger: 'blur' }],
}

function parentName(parentId) {
  if (!parentId) return '-'
  const p = categories.value.find((c) => c.id === parentId)
  return p ? p.name : parentId
}

async function loadCategories() {
  loading.value = true
  const params = { page: page.value, page_size: pageSize.value }
  if (search.value) params.search = search.value
  try {
    const data = await getCategories(params)
    categories.value = data.results || []
    total.value = data.count || 0
  } catch (e) {
    ElMessage.error(e.message || '加载分类失败')
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  page.value = 1
  loadCategories()
}

function handleReset() {
  search.value = ''
  page.value = 1
  loadCategories()
}

function handlePageChange(p) {
  page.value = p
  loadCategories()
}

function openCreate() {
  resetForm()
  dialogVisible.value = true
}

function openEdit(row) {
  Object.assign(form, {
    id: row.id,
    name: row.name,
    code: row.code,
    parent: row.parent,
    sort_order: row.sort_order,
  })
  dialogVisible.value = true
}

function resetForm() {
  Object.assign(form, { id: null, name: '', code: '', parent: null, sort_order: 0 })
  formRef.value?.clearValidate()
}

async function handleSave() {
  await formRef.value.validate()
  saving.value = true
  const payload = {
    name: form.name,
    code: form.code,
    parent: form.parent || null,
    sort_order: form.sort_order,
  }
  try {
    if (form.id) {
      await updateCategory(form.id, payload)
      ElMessage.success('更新成功')
    } else {
      await createCategory(payload)
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    loadCategories()
  } catch (e) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

function handleDelete(row) {
  ElMessageBox.confirm(`确定删除分类「${row.name}」吗？`, '删除确认', {
    type: 'warning',
    confirmButtonText: '删除',
    cancelButtonText: '取消',
  })
    .then(async () => {
      await deleteCategory(row.id)
      ElMessage.success('删除成功')
      loadCategories()
    })
    .catch(() => {})
}

onMounted(loadCategories)
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
