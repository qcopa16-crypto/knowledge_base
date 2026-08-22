<template>
  <div class="not-found">
    <div class="code">404</div>
    <p class="message">抱歉，你访问的页面不存在</p>
    <router-link to="/" class="back-btn">返回首页</router-link>
  </div>
</template>

<script setup>
</script>

<style scoped>
.not-found {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  text-align: center;
  padding: 16px;
}

.code {
  font-size: 96px;
  font-weight: 700;
  color: var(--primary);
  line-height: 1;
}

.message {
  font-size: 16px;
  color: var(--text-muted);
}

.back-btn {
  display: inline-block;
  padding: 10px 24px;
  background: var(--primary);
  color: #fff;
  border-radius: 6px;
  transition: background 0.2s;
}

.back-btn:hover {
  background: var(--primary-dark);
  color: #fff;
}

@media (max-width: 768px) {
  .code {
    font-size: 64px;
  }
}
</style>
