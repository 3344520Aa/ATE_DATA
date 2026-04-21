<template>
  <div class="login-container">
    <div class="login-box">
      <h2>Chip ATE 分析系统</h2>

      <div class="tabs">
        <span :class="{ active: mode === 'login' }" @click="mode = 'login'">登录</span>
        <span :class="{ active: mode === 'register' }" @click="mode = 'register'">注册</span>
      </div>

      <form @submit.prevent="handleSubmit">
        <div class="field">
          <label>用户名</label>
          <input v-model="form.username" type="text" placeholder="请输入用户名" required />
        </div>

        <div v-if="mode === 'register'" class="field">
          <label>邮箱</label>
          <input v-model="form.email" type="email" placeholder="请输入邮箱" required />
        </div>

        <div class="field">
          <label>密码</label>
          <input v-model="form.password" type="password" placeholder="请输入密码" required />
        </div>

        <div v-if="error" class="error">{{ error }}</div>

        <button type="submit" :disabled="loading">
          {{ loading ? '请稍候...' : mode === 'login' ? '登录' : '注册' }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const mode = ref<'login' | 'register'>('login')
const loading = ref(false)
const error = ref('')
const form = ref({ username: '', email: '', password: '' })

async function handleSubmit() {
  error.value = ''
  loading.value = true
  try {
    if (mode.value === 'login') {
      await authStore.login(form.value.username, form.value.password)
    } else {
      await authStore.register(form.value.username, form.value.email, form.value.password)
      mode.value = 'login'
      error.value = '注册成功，请登录'
      return
    }
    router.push('/')
  } catch (e: any) {
    error.value = e || '操作失败'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f0f2f5;
}
.login-box {
  background: white;
  padding: 40px;
  border-radius: 8px;
  width: 360px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.1);
}
h2 {
  text-align: center;
  margin-bottom: 24px;
  color: #1a1a2e;
  font-size: 20px;
}
.tabs {
  display: flex;
  margin-bottom: 24px;
  border-bottom: 1px solid #e8e8e8;
}
.tabs span {
  flex: 1;
  text-align: center;
  padding: 8px;
  cursor: pointer;
  color: #888;
}
.tabs span.active {
  color: #1890ff;
  border-bottom: 2px solid #1890ff;
}
.field {
  margin-bottom: 16px;
}
.field label {
  display: block;
  margin-bottom: 6px;
  font-size: 14px;
  color: #333;
}
.field input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  font-size: 14px;
  box-sizing: border-box;
}
.field input:focus {
  outline: none;
  border-color: #1890ff;
}
button {
  width: 100%;
  padding: 10px;
  background: #1890ff;
  color: white;
  border: none;
  border-radius: 4px;
  font-size: 16px;
  cursor: pointer;
  margin-top: 8px;
}
button:disabled {
  background: #aaa;
}
.error {
  color: #ff4d4f;
  font-size: 13px;
  margin-bottom: 8px;
}
</style>