<template>
  <div class="page">
    <!-- 顶部搜索筛选工具栏 -->
    <div class="toolbar">
      <el-input
        v-model="filters.search"
        placeholder="搜索标题 / 型号 / 关键词"
        class="search-input"
        clearable
        @keyup.enter="handleSearch"
        @clear="handleSearch"
      >
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>

      <el-select v-model="filters.brand" placeholder="全部品牌" clearable class="filter-select" @change="handleSearch">
        <el-option v-for="b in brands" :key="b.id" :label="b.name" :value="b.id" />
      </el-select>

      <el-select v-model="filters.device_type" placeholder="全部设备类型" clearable class="filter-select" @change="handleSearch">
        <el-option v-for="t in deviceTypes" :key="t.id" :label="t.name" :value="t.id" />
      </el-select>

      <el-select v-model="filters.os_type" placeholder="全部操作系统" clearable class="filter-select" @change="handleSearch">
        <el-option v-for="(label, code) in OS_OPTIONS" :key="code" :label="label" :value="code" />
      </el-select>

      <el-button type="primary" @click="handleSearch"><el-icon><Search /></el-icon>&nbsp;搜索</el-button>
      <el-button @click="handleReset">重置</el-button>

      <div class="spacer"></div>

      <el-button v-if="isAdmin" type="primary" @click="openCreate"><el-icon><Plus /></el-icon>&nbsp;新增文档</el-button>
    </div>

    <!-- 数据表格 -->
    <el-table
      v-loading="loading"
      :data="documents"
      stripe
      border
      class="data-table"
    >
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
      <el-table-column prop="brand_name" label="品牌" width="120" />
      <el-table-column prop="device_type_name" label="设备类型" width="120" />
      <el-table-column prop="model_code" label="型号" width="140" />
      <el-table-column label="操作系统" width="120">
        <template #default="{ row }">{{ OS_OPTIONS[row.os_type] || row.os_type || '-' }}</template>
      </el-table-column>
      <el-table-column prop="version" label="版本" width="90" />
      <el-table-column prop="view_count" label="浏览量" width="90" />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="STATUS_TAG[row.status] || 'info'">{{ STATUS_LABEL[row.status] || row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column v-if="isAdmin" label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div class="pagination">
      <el-pagination
        background
        layout="total, prev, pager, next, sizes"
        :total="total"
        :current-page="page"
        :page-size="pageSize"
        :page-sizes="[10, 20, 50]"
        @current-change="handlePageChange"
        @size-change="handleSizeChange"
      />
    </div>

    <!-- 新增/编辑弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="form.id ? '编辑文档' : '新增文档'"
      width="560px"
      @closed="resetForm"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="标题" prop="title">
          <el-input v-model="form.title" placeholder="文档标题" />
        </el-form-item>
        <el-form-item label="品牌">
          <el-select v-model="form.brand" placeholder="选择品牌" clearable style="width: 100%">
            <el-option v-for="b in brands" :key="b.id" :label="b.name" :value="b.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="设备类型">
          <el-select v-model="form.device_type" placeholder="选择设备类型" clearable style="width: 100%">
            <el-option v-for="t in deviceTypes" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="型号" prop="model_code">
          <el-input v-model="form.model_code" placeholder="如 BZT3-W59" />
        </el-form-item>
        <el-form-item label="操作系统">
          <el-select v-model="form.os_type" placeholder="选择操作系统" clearable style="width: 100%">
            <el-option v-for="(label, code) in OS_OPTIONS" :key="code" :label="label" :value="code" />
          </el-select>
        </el-form-item>
        <el-form-item label="文档类型">
          <el-select v-model="form.doc_type" placeholder="选择文档类型" style="width: 100%">
            <el-option v-for="(label, code) in DOC_TYPE_OPTIONS" :key="code" :label="label" :value="code" />
          </el-select>
        </el-form-item>
        <el-form-item label="版本">
          <el-input v-model="form.version" placeholder="版本号" />
        </el-form-item>
        <el-form-item label="摘要">
          <el-input v-model="form.summary" type="textarea" :rows="2" placeholder="文档摘要" />
        </el-form-item>
        <el-form-item label="关键词">
          <el-input v-model="form.keywords" placeholder="关键词，逗号分隔" />
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
import { getBrands, getDeviceTypes } from '../api/catalog'
import {
  getDocuments,
  createDocument,
  updateDocument,
  deleteDocument,
} from '../api/documents'
import { authState } from '../store/auth'

const OS_OPTIONS = {
  windows11: 'Windows 11',
  harmonyos: 'HarmonyOS',
  uos: 'UOS',
  kos: 'KOS',
  emui: 'EMUI',
  android: 'Android',
  other: '其他',
}

const DOC_TYPE_OPTIONS = {
  user_guide: '用户指南',
  user_manual: '用户手册',
  instruction: '使用说明书',
  safety: '产品安全手册',
  config_guide: '配置指导',
  comm_config: '通讯配置说明',
  other: '其他',
}

const STATUS_LABEL = {
  pending: '待解析',
  processing: '解析中',
  ready: '已就绪',
  failed: '解析失败',
}

const STATUS_TAG = {
  pending: 'warning',
  processing: 'primary',
  ready: 'success',
  failed: 'danger',
}

const isAdmin = computed(() => authState.user?.is_staff || authState.user?.is_superuser)

const brands = ref([])
const deviceTypes = ref([])
const documents = ref([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)

const filters = reactive({ search: '', brand: '', device_type: '', os_type: '' })

const dialogVisible = ref(false)
const saving = ref(false)
const formRef = ref(null)

const form = reactive({
  id: null,
  title: '',
  brand: null,
  device_type: null,
  model_code: '',
  os_type: '',
  doc_type: 'user_manual',
  version: '',
  summary: '',
  keywords: '',
})

const rules = {
  title: [{ required: true, message: '请输入标题', trigger: 'blur' }],
  model_code: [{ required: true, message: '请输入型号', trigger: 'blur' }],
}

async function loadOptions() {
  const [b, t] = await Promise.all([getBrands({ page_size: 100 }), getDeviceTypes({ page_size: 100 })])
  brands.value = b.results || []
  deviceTypes.value = t.results || []
}

async function loadDocuments() {
  loading.value = true
  const params = { page: page.value, page_size: pageSize.value }
  if (filters.search) params.search = filters.search
  if (filters.brand) params.brand = filters.brand
  if (filters.device_type) params.device_type = filters.device_type
  if (filters.os_type) params.os_type = filters.os_type

  try {
    const data = await getDocuments(params)
    documents.value = data.results || []
    total.value = data.count || 0
  } catch (e) {
    ElMessage.error(e.message || '加载文档失败')
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  page.value = 1
  loadDocuments()
}

function handleReset() {
  filters.search = ''
  filters.brand = ''
  filters.device_type = ''
  filters.os_type = ''
  page.value = 1
  loadDocuments()
}

function handlePageChange(p) {
  page.value = p
  loadDocuments()
}

function handleSizeChange(s) {
  pageSize.value = s
  page.value = 1
  loadDocuments()
}

function openCreate() {
  resetForm()
  dialogVisible.value = true
}

function openEdit(row) {
  Object.assign(form, {
    id: row.id,
    title: row.title,
    brand: row.brand,
    device_type: row.device_type,
    model_code: row.model_code,
    os_type: row.os_type,
    doc_type: row.doc_type,
    version: row.version,
    summary: row.summary,
    keywords: row.keywords,
  })
  dialogVisible.value = true
}

function resetForm() {
  Object.assign(form, {
    id: null,
    title: '',
    brand: null,
    device_type: null,
    model_code: '',
    os_type: '',
    doc_type: 'user_manual',
    version: '',
    summary: '',
    keywords: '',
  })
  formRef.value?.clearValidate()
}

async function handleSave() {
  await formRef.value.validate()
  saving.value = true
  const payload = {
    title: form.title,
    brand: form.brand || null,
    device_type: form.device_type || null,
    model_code: form.model_code,
    os_type: form.os_type,
    doc_type: form.doc_type,
    version: form.version,
    summary: form.summary,
    keywords: form.keywords,
  }
  try {
    if (form.id) {
      await updateDocument(form.id, payload)
      ElMessage.success('更新成功')
    } else {
      await createDocument(payload)
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    loadDocuments()
  } catch (e) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

function handleDelete(row) {
  ElMessageBox.confirm(`确定删除文档「${row.title}」吗？`, '删除确认', {
    type: 'warning',
    confirmButtonText: '删除',
    cancelButtonText: '取消',
  })
    .then(async () => {
      await deleteDocument(row.id)
      ElMessage.success('删除成功')
      loadDocuments()
    })
    .catch(() => {})
}

onMounted(() => {
  loadOptions()
  loadDocuments()
})
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

.filter-select {
  width: 150px;
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
