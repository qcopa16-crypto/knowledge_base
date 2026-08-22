<template>
  <div class="upload-page">
    <div class="upload-card">
      <div class="card-header">
        <el-icon :size="20">
          <UploadFilled/>
        </el-icon>
        <span>文档上传入库</span>
      </div>

      <!-- 文件选择 -->
      <div class="upload-area">
        <el-upload
            drag
            multiple
            :auto-upload="false"
            accept=".pdf,.md,.txt"
            :on-change="handleFileChange"
            :on-remove="handleFileRemove"
            :file-list="fileList"
        >
          <el-icon class="upload-icon" :size="48">
            <UploadFilled/>
          </el-icon>
          <div class="el-upload__text">将文件拖到此处，或 <em>点击选择</em></div>
          <template #tip>
            <div class="el-upload__tip">支持 PDF / Markdown / 文本文件，单个不超过 50MB，可多选</div>
          </template>
        </el-upload>
      </div>

      <div class="actions">
        <el-button
            type="primary"
            :disabled="!pendingFiles.length || uploading"
            :loading="uploading"
            @click="handleUpload"
        >
          <el-icon>
            <Promotion/>
          </el-icon>&nbsp;开始入库
        </el-button>
      </div>

      <!-- 逐文件进度列表 -->
      <div v-if="uploadItems.length" class="progress-box">
        <div class="progress-title">入库进度</div>
        <div class="file-progress-list">
          <div v-for="item in uploadItems" :key="item.uid" class="file-progress-item">
            <div class="file-progress-header">
              <span class="file-name" :title="item.name">{{ item.name }}</span>
              <el-tag :type="statusTag(item.status)" size="small">{{ statusLabel(item.status) }}</el-tag>
            </div>
            <div v-if="item.status === 'processing'" class="running-line">
              <span class="running-label">正在处理：</span>
              <span class="running-node">{{ item.runningList.join(' → ') || '准备中...' }}</span>
            </div>
            <div v-if="item.doneList.length" class="done-line">
              <span class="done-label">已完成：</span>
              <span class="done-node">{{ item.doneList.join(' → ') }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import {computed, onUnmounted, ref} from 'vue'
import {ElMessage} from 'element-plus'
import {uploadDocuments, batchGetRAGStatus,} from '../api/rag'

const fileList = ref([])
const uploadItems = ref([])
const uploading = ref(false)
let timer = null

const pendingFiles = computed(() => uploadItems.value.filter((i) => !i.taskId))

function statusLabel(status) {
  const map = {
    pending: '等待处理',
    processing: '解析处理中',
    completed: '入库完成',
    failed: '入库失败',
    skipped: '已跳过',
  }
  return map[status] || '等待处理'
}

function statusTag(status) {
  const map = {
    pending: 'warning',
    processing: 'primary',
    completed: 'success',
    failed: 'danger',
    skipped: 'info',
  }
  return map[status] || 'info'
}

function handleFileChange(file) {
  if (file.size > 50 * 1024 * 1024) {
    ElMessage.warning(`${file.name} 超过 50MB 限制`)
    return
  }
  uploadItems.value.push({
    uid: file.uid,
    name: file.name,
    raw: file.raw,
    taskId: '',
    status: 'pending',
    doneList: [],
    runningList: [],
  })
}

function handleFileRemove(file) {
  const idx = uploadItems.value.findIndex((i) => i.uid === file.uid)
  if (idx !== -1) {
    uploadItems.value.splice(idx, 1)
  }
}

async function handleUpload() {
  const targets = pendingFiles.value
  if (!targets.length) {
    ElMessage.warning('请先选择文件')
    return
  }
  uploading.value = true
  try {
    const files = targets.map((i) => i.raw)
    const data = await uploadDocuments(files)

    // 成功文件：建立 uid -> task_id 映射
    const accepted = data.files || []
    const acceptedByName = new Map(accepted.map((f) => [f.filename, f.task_id]))

    for (const item of targets) {
      const taskId = acceptedByName.get(item.name)
      if (taskId) {
        item.taskId = taskId
        item.status = 'processing'
      } else {
        item.status = 'skipped'
      }
    }

    // 展示被跳过的文件提示
    const skipped = data.skipped || []
    if (skipped.length) {
      ElMessage.warning(`${skipped.length} 个文件未通过校验`)
    }

    if (accepted.length) {
      ElMessage.success(`已提交 ${accepted.length} 个入库任务`)
      startPolling()
    } else {
      uploading.value = false
    }
  } catch (e) {
    ElMessage.error(e.message || '上传失败')
    uploading.value = false
  }
}

function startPolling() {
  let attempts = 0
  timer = setInterval(async () => {
    attempts += 1
    const active = uploadItems.value.filter(
        (i) => i.taskId && !['completed', 'failed'].includes(i.status)
    )
    if (!active.length) {
      stopPolling()
      uploading.value = false
      return
    }
    try {
      // 提取所有任务ID，一次请求拿回全部状态
      const taskIds = active.map((item) => item.taskId)
      const {results} = await batchGetRAGStatus(taskIds)

      // 批量更新每个文件的状态
      for (const item of active) {
        const info = results[item.taskId]
        if (info) {
          item.status = info.status
          item.doneList = info.done_list || []
          item.runningList = info.running_list || []
        }
      }
    } catch (e) {
      console.warn('轮询状态失败', e)
    }

    const finished = uploadItems.value.every(
        (i) => !i.taskId || ['completed', 'failed'].includes(i.status)
    )
    if (finished || attempts >= 60) {
      stopPolling()
      uploading.value = false
      if (attempts >= 60) {
        ElMessage.warning('部分文件处理超时，请稍后查看')
      }
    }
  }, 2000)
}

function stopPolling() {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

onUnmounted(stopPolling)
</script>

<style scoped>
.upload-page {
  display: flex;
  justify-content: center;
}

.upload-card {
  width: 100%;
  max-width: 720px;
  background: #fff;
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: #2563eb;
  margin-bottom: 20px;
}

.upload-area {
  margin-bottom: 16px;
}

.upload-icon {
  color: #9ca3af;
}

.actions {
  display: flex;
  justify-content: center;
  margin-bottom: 24px;
}

.progress-box {
  border-top: 1px solid #f0f0f0;
  padding-top: 20px;
}

.progress-title {
  font-size: 14px;
  font-weight: 600;
  color: #111827;
  margin-bottom: 16px;
}

.file-progress-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.file-progress-item {
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  padding: 12px 14px;
}

.file-progress-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.file-name {
  font-size: 14px;
  color: #111827;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 70%;
}

.running-line,
.done-line {
  font-size: 12px;
  color: #6b7280;
  margin-top: 4px;
  line-height: 1.6;
}

.running-label {
  color: #2563eb;
  font-weight: 600;
}

.running-node {
  color: #2563eb;
}

.done-label {
  color: #16a34a;
  font-weight: 600;
}

.done-node {
  color: #374151;
}
</style>
