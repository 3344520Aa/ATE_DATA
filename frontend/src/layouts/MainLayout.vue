<template>
  <div class="layout">
    <!-- 侧边栏 -->
    <aside :class="['sidebar', { collapsed }]">
      <div class="logo">
        <span class="logo-icon">⚡</span>
        <span v-if="!collapsed" class="logo-text">ATE 分析系统</span>
      </div>

      <nav class="menu">
        <RouterLink to="/" class="menu-item">
          <span class="icon">📋</span>
          <span v-if="!collapsed" class="label">数据列表</span>
        </RouterLink>
        <RouterLink to="/analysis" class="menu-item">
          <span class="icon">📊</span>
          <span v-if="!collapsed" class="label">数据分析</span>
        </RouterLink>
        <RouterLink to="/reports" class="menu-item">
          <span class="icon">📈</span>
          <span v-if="!collapsed" class="label">报表中心</span>
        </RouterLink>
        <RouterLink to="/settings" class="menu-item">
          <span class="icon">⚙️</span>
          <span v-if="!collapsed" class="label">系统设置</span>
        </RouterLink>
      </nav>

      <div class="sidebar-footer">
        <div class="user-info" v-if="!collapsed">
          <span class="username">{{ authStore.user?.username }}</span>
          <button class="logout-btn" @click="handleLogout">退出</button>
        </div>
        <button v-else class="logout-btn-small" @click="handleLogout">↩</button>
      </div>
    </aside>

    <!-- 主内容区 -->
    <div class="main">
      <!-- 顶部栏 -->
      <header class="topbar">
        <button class="collapse-btn" @click="collapsed = !collapsed">
          {{ collapsed ? '▶' : '◀' }}
        </button>
        <span class="page-title">{{ pageTitle }}</span>
        <div class="topbar-right">
          <span class="username-tag">{{ authStore.user?.username }}</span>
        </div>
      </header>

      <!-- 页面内容 -->
      <main class="content">
        <RouterView />
      </main>
    </div>

    <!-- AI 对话悬浮框 -->
    <div :class="['ai-panel', { open: aiOpen }]">
      <div class="ai-header" @click="aiOpen = !aiOpen">
        <span>🤖 AI 助手</span>
        <span>{{ aiOpen ? '▶' : '◀' }}</span>
      </div>
      <div class="ai-body" v-if="aiOpen">
        <div class="ai-placeholder">AI 对话功能即将上线</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
const router = useRouter()
const route = useRoute()

const collapsed = ref(false)
const aiOpen = ref(false)

const pageTitles: Record<string, string> = {
  '/': '数据列表',
  '/analysis': '数据分析',
  '/reports': '报表中心',
  '/settings': '系统设置',
}

const pageTitle = computed(() => pageTitles[route.path] || '')

function handleLogout() {
  authStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

/* 侧边栏 */
.sidebar {
  width: 220px;
  background: #1a1a2e;
  color: white;
  display: flex;
  flex-direction: column;
  transition: width 0.2s;
  flex-shrink: 0;
}
.sidebar.collapsed {
  width: 56px;
}
.logo {
  height: 56px;
  display: flex;
  align-items: center;
  padding: 0 16px;
  gap: 10px;
  border-bottom: 1px solid rgba(255,255,255,0.1);
  font-size: 16px;
  font-weight: bold;
}
.logo-icon { font-size: 20px; }

.menu { flex: 1; padding: 8px 0; }
.menu-item {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  gap: 10px;
  color: rgba(255,255,255,0.7);
  text-decoration: none;
  transition: background 0.2s;
  font-size: 14px;
}
.menu-item:hover,
.menu-item.router-link-active {
  background: rgba(255,255,255,0.1);
  color: white;
}
.icon { font-size: 18px; width: 20px; text-align: center; }

.sidebar-footer {
  padding: 16px;
  border-top: 1px solid rgba(255,255,255,0.1);
}
.user-info {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.username { font-size: 13px; color: rgba(255,255,255,0.8); }
.logout-btn {
  background: transparent;
  border: 1px solid rgba(255,255,255,0.3);
  color: white;
  padding: 4px 8px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}
.logout-btn-small {
  background: transparent;
  border: none;
  color: white;
  font-size: 16px;
  cursor: pointer;
  width: 100%;
}

/* 主内容区 */
.main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #f0f2f5;
}
.topbar {
  height: 56px;
  background: white;
  display: flex;
  align-items: center;
  padding: 0 16px;
  gap: 16px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.08);
  flex-shrink: 0;
}
.collapse-btn {
  background: transparent;
  border: none;
  cursor: pointer;
  font-size: 14px;
  color: #666;
  padding: 4px 8px;
}
.page-title {
  font-size: 16px;
  font-weight: 500;
  color: #333;
  flex: 1;
}
.topbar-right { display: flex; align-items: center; gap: 12px; }
.username-tag {
  font-size: 13px;
  color: #666;
  background: #f0f2f5;
  padding: 4px 10px;
  border-radius: 12px;
}

.content {
  flex: 1;
  overflow: hidden;
  padding: 0;
}

/* AI 悬浮框 */
.ai-panel {
  position: fixed;
  right: 0;
  top: 50%;
  transform: translateY(-50%);
  z-index: 100;
  display: flex;
  flex-direction: row-reverse;
}
.ai-header {
  background: #1890ff;
  color: white;
  writing-mode: vertical-rl;
  padding: 16px 8px;
  cursor: pointer;
  border-radius: 8px 0 0 8px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  box-shadow: -2px 0 8px rgba(0,0,0,0.1);
}
.ai-body {
  width: 320px;
  height: 480px;
  background: white;
  box-shadow: -2px 0 12px rgba(0,0,0,0.1);
  display: flex;
  flex-direction: column;
}
.ai-placeholder {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #999;
  font-size: 14px;
}
</style>