<template>
  <div class="chat-page">
    <!-- 历史会话侧栏 -->
    <aside class="session-sidebar">
      <div class="sidebar-header">
        <el-button type="primary" class="new-chat-btn" @click="handleNewChat">
          <el-icon><Plus /></el-icon>&nbsp;新对话
        </el-button>
      </div>
      <div class="session-list">
        <div v-if="!sessions.length" class="session-empty">暂无历史对话</div>
        <div
          v-for="s in sessions"
          :key="s.session_id"
          class="session-item"
          :class="{ active: s.session_id === currentSessionId }"
          @click="handleSelectSession(s)"
        >
          <span class="session-title">{{ s.title || '未命名会话' }}</span>
        </div>
      </div>
    </aside>

    <!-- 聊天区 -->
    <div class="chat-card">
      <div class="chat-header">
        <el-icon :size="20"><ChatDotRound /></el-icon>
        <span>智能问答</span>
      </div>

      <div class="chat-body" ref="chatBodyRef">
        <div v-if="!messages.length && !loading" class="empty-tip">
          输入你的问题，AI 将从设备手册知识库中检索并回答
        </div>

        <div
          v-for="(msg, idx) in messages"
          :key="idx"
          class="message-row"
          :class="msg.role === 'user' ? 'row-user' : 'row-assistant'"
        >
          <div class="message-bubble" :class="msg.role === 'user' ? 'bubble-user' : 'bubble-assistant'">
            <div class="message-content">{{ msg.content }}</div>
          </div>
        </div>

        <div v-if="loading" class="loading-box">
          <el-icon class="loading-icon" :size="24"><Loading /></el-icon>
          <p>正在检索知识库并生成答案，请稍候...</p>
        </div>

        <div v-if="errorMsg" class="error-box">
          <el-icon :size="16"><WarningFilled /></el-icon>
          <span>{{ errorMsg }}</span>
        </div>
      </div>

      <div class="chat-input">
        <el-input
          v-model="question"
          type="textarea"
          :rows="3"
          placeholder="例如：华为平板 C5 如何连接网络？"
          :disabled="loading"
          @keydown.enter.exact.prevent="handleAsk"
        />
        <div class="input-actions">
          <span class="hint">支持设备手册相关的自然语言提问</span>
          <el-button type="primary" :loading="loading" @click="handleAsk">
            <el-icon><Promotion /></el-icon>&nbsp;发送
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { submitRAG, getRAGResult, listSessions, getSessionMessages } from '../api/rag'

const question = ref('')
const messages = ref([])
const sessions = ref([])
const currentSessionId = ref('')
const errorMsg = ref('')
const loading = ref(false)
const chatBodyRef = ref(null)
let timer = null       // 轮询 / 打字机定时器
let pollingSeq = 0     // 防竞态序号

// 打字机速度（每次追加字符数 / 间隔 ms）
const TYPE_CHARS_PER_TICK = 3
const TYPE_TICK_MS = 20

async function scrollToBottom() {
  await nextTick()
  if (chatBodyRef.value) {
    chatBodyRef.value.scrollTop = chatBodyRef.value.scrollHeight
  }
}

async function loadSessions() {
  try {
    const data = await listSessions()
    sessions.value = data.sessions || []
  } catch (e) {
    // 历史会话加载失败不阻断主流程
    console.warn('加载历史会话失败', e)
  }
}

function handleNewChat() {
  stopPolling()
  currentSessionId.value = ''
  messages.value = []
  errorMsg.value = ''
  question.value = ''
}

async function handleSelectSession(session) {
  if (loading.value) return
  stopPolling()
  currentSessionId.value = session.session_id
  errorMsg.value = ''
  messages.value = []
  try {
    const data = await getSessionMessages(session.session_id)
    // 只显示最近 50 条，避免历史消息堆积导致页面混乱
    messages.value = (data.messages || []).slice(-50).map((m) => ({
      role: m.role,
      content: m.text,
    }))
    await scrollToBottom()
  } catch (e) {
    ElMessage.error(e.message || '加载历史消息失败')
  }
}

// 打字机逐字显示：把完整答案逐字追加到 assistant 占位消息，模拟流式输出
function typewriteAnswer(answer) {
  const last = messages.value[messages.value.length - 1]
  if (!last || last.role !== 'assistant') return
  last.content = ''  // 从空开始打字机
  let index = 0
  timer = setInterval(() => {
    if (index < answer.length) {
      const end = Math.min(index + TYPE_CHARS_PER_TICK, answer.length)
      last.content += answer.slice(index, end)
      index = end
      scrollToBottom()
    } else {
      clearInterval(timer)
      timer = null
      loading.value = false
      scrollToBottom()
    }
  }, TYPE_TICK_MS)
}

// 伪流式：轮询结果接口拿完整答案，再用打字机逐字显示
function startFakeStream(taskId) {
  // 先清掉旧定时器，避免多个轮询竞争
  stopPolling()
  const mySeq = ++pollingSeq
  let attempts = 0
  timer = setInterval(async () => {
    // 若已有新轮询启动，旧定时器回调直接忽略
    if (mySeq !== pollingSeq) return
    attempts += 1
    try {
      const result = await getRAGResult(taskId)
      if (mySeq !== pollingSeq) return
      if (result.status === 'completed') {
        stopPolling()
        const answer = result.answer || '（无答案）'
        typewriteAnswer(answer)
      } else if (result.status === 'failed') {
        stopPolling()
        errorMsg.value = result.error || '处理失败'
        loading.value = false
      } else if (attempts >= 120) {
        stopPolling()
        errorMsg.value = '处理超时，请稍后重试'
        loading.value = false
      }
    } catch (e) {
      if (mySeq !== pollingSeq) return
      stopPolling()
      errorMsg.value = e.message || '查询失败'
      loading.value = false
    }
  }, 1000)
}

function stopPolling() {
  // 递增 seq，使所有在途的旧回调立即失效
  pollingSeq += 1
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

async function handleAsk() {
  const q = question.value.trim()
  if (!q) {
    ElMessage.warning('请输入问题')
    return
  }
  if (loading.value) return

  errorMsg.value = ''
  // 立即展示用户消息（修复「用户输入不显示」）
  messages.value.push({ role: 'user', content: q })
  question.value = ''
  loading.value = true
  await scrollToBottom()

  try {
    const data = await submitRAG({
      op: 'query',
      query: q,
      session_id: currentSessionId.value || undefined,
      enable_embedding: true,
      enable_hyde: true,
      enable_web_search: true,
      is_stream: false, // 伪流式：worker 一次性生成，前端打字机逐字显示
    })
    const taskId = data.task_id
    // 若后端返回了新 session_id（首次提问），记录并刷新会话列表
    if (data.session_id) {
      currentSessionId.value = data.session_id
      loadSessions()
    }

    // 先 push 一个空的 assistant 消息占位，打字机逐字填充
    messages.value.push({ role: 'assistant', content: '' })
    await scrollToBottom()

    // 伪流式：轮询拿完整答案 + 打字机逐字显示
    startFakeStream(taskId)
  } catch (e) {
    errorMsg.value = e.message || '提交失败'
    loading.value = false
  }
}

onMounted(loadSessions)
onUnmounted(stopPolling)
</script>

<style scoped>
.chat-page {
  display: flex;
  gap: 16px;
  justify-content: center;
  align-items: flex-start;
}

.session-sidebar {
  width: 220px;
  flex-shrink: 0;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
  padding: 16px;
  display: flex;
  flex-direction: column;
  max-height: 600px;
}

.sidebar-header {
  margin-bottom: 12px;
}

.new-chat-btn {
  width: 100%;
}

.session-list {
  flex: 1;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.session-empty {
  text-align: center;
  color: #9ca3af;
  font-size: 13px;
  padding: 20px 0;
}

.session-item {
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  color: #374151;
  transition: background 0.2s;
}

.session-item:hover {
  background: #f3f4f6;
}

.session-item.active {
  background: #eff6ff;
  color: #2563eb;
}

.session-title {
  display: block;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.chat-card {
  flex: 1;
  max-width: 720px;
  background: #fff;
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
  min-height: 480px;
}

.chat-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px 20px;
  font-size: 16px;
  font-weight: 600;
  color: #2563eb;
  border-bottom: 1px solid #f0f0f0;
}

.chat-body {
  flex: 1;
  padding: 20px;
  overflow: auto;
}

.empty-tip {
  text-align: center;
  color: #9ca3af;
  padding: 60px 0;
  font-size: 14px;
}

.message-row {
  display: flex;
  margin-bottom: 14px;
}

.row-user {
  justify-content: flex-end;
}

.row-assistant {
  justify-content: flex-start;
}

.message-bubble {
  max-width: 78%;
  padding: 10px 14px;
  border-radius: 10px;
  font-size: 14px;
  line-height: 1.6;
}

.bubble-user {
  background: #2563eb;
  color: #fff;
  border-bottom-right-radius: 2px;
}

.bubble-assistant {
  background: #f0f7ff;
  color: #111827;
  border-bottom-left-radius: 2px;
}

.message-content {
  white-space: pre-wrap;
  word-break: break-word;
}

.loading-box {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 0;
  color: #6b7280;
  font-size: 13px;
}

.loading-icon {
  animation: spin 1s linear infinite;
  color: #2563eb;
}

.loading-box p {
  margin: 0;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.error-box {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #ef4444;
  background: #fef2f2;
  border-radius: 8px;
  padding: 12px 16px;
  font-size: 14px;
}

.chat-input {
  border-top: 1px solid #f0f0f0;
  padding: 16px 20px;
}

.input-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 12px;
}

.hint {
  font-size: 12px;
  color: #9ca3af;
}
</style>
