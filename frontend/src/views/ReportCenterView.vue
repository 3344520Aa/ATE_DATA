<template>
  <div class="report-center">
    <div class="page-header">
      <h2>📊 报表中心</h2>
      <div class="header-actions">
        <div class="filter-group">
          <label class="filter-label">产品名筛选:</label>
          <div class="product-filter-container">
            <label class="all-check">
              <input type="checkbox" :checked="isAllProductsSelected" @change="toggleAllProducts" />
              <span>全选</span>
            </label>
            <div class="product-options">
              <label v-for="prod in uniqueProducts" :key="prod" class="prod-option">
                <input type="checkbox" :value="prod" v-model="selectedProducts" />
                <span>{{ prod }}</span>
              </label>
            </div>
          </div>
        </div>
        <input 
          type="text" 
          v-model="searchQuery" 
          placeholder="搜索报表名称..." 
          class="search-input"
        />
      </div>
    </div>

    <div class="report-list-card">
      <table class="report-table">
        <thead>
          <tr>
            <th style="width: 60px;">No.</th>
            <th @click="sort('product_name')">产品名 <span v-if="sortBy === 'product_name'">{{ sortOrder === 'asc' ? '↑' : '↓' }}</span></th>
            <th @click="sort('name')">报表名称 <span v-if="sortBy === 'name'">{{ sortOrder === 'asc' ? '↑' : '↓' }}</span></th>
            <th @click="sort('type')">类型 <span v-if="sortBy === 'type'">{{ sortOrder === 'asc' ? '↑' : '↓' }}</span></th>
            <th>分析备注</th>
            <th @click="sort('createTime')">保存时间 <span v-if="sortBy === 'createTime'">{{ sortOrder === 'asc' ? '↑' : '↓' }}</span></th>
            <th class="actions-col">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(report, index) in filteredReports" :key="report.id">
            <td class="no-cell">{{ index + 1 }}</td>
            <td class="product-cell">{{ report.product_name || '-' }}</td>
            <td class="name-cell">
              <div v-if="editingId === report.id" class="edit-box">
                <input 
                  type="text" 
                  v-model="editName" 
                  @blur="saveEdit(report)" 
                  @keyup.enter="saveEdit(report)" 
                  class="edit-input"
                  v-focus
                />
              </div>
              <div v-else class="name-display">
                <a :href="report.url" target="_blank" class="report-link">{{ report.name }}</a>
                <button class="action-btn rename-small" @click="startEdit(report)" title="重命名">✏️</button>
              </div>
            </td>
            <td><span class="type-badge">{{ report.type }}</span></td>
            <td class="comment-cell">
              <textarea 
                v-model="report.comment" 
                @blur="saveToLocal" 
                placeholder="添加分析备注..."
                class="inline-comment-input"
              ></textarea>
            </td>
            <td class="time-cell">{{ report.createTime }}</td>
            <td class="actions-cell">
              <button class="action-btn delete" @click="deleteReport(report.id)" title="删除">🗑️</button>
            </td>
          </tr>
          <tr v-if="filteredReports.length === 0">
            <td colspan="7" class="empty-state">暂无报表记录</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'

interface Report {
  id: string | number
  name: string
  product_name?: string
  url: string
  createTime: string
  type: string
  comment?: string
}

const reports = ref<Report[]>([])
const searchQuery = ref('')
const sortBy = ref('createTime')
const sortOrder = ref<'asc' | 'desc'>('desc')

const editingId = ref<string | number | null>(null)
const editName = ref('')
const selectedProducts = ref<string[]>([])

const uniqueProducts = computed(() => {
  const prods = new Set<string>()
  reports.value.forEach(r => {
    if (r.product_name) prods.add(r.product_name)
    else prods.add('Unknown')
  })
  return Array.from(prods).sort()
})

const isAllProductsSelected = computed(() => {
  return selectedProducts.value.length === uniqueProducts.value.length
})

function toggleAllProducts() {
  if (isAllProductsSelected.value) {
    selectedProducts.value = []
  } else {
    selectedProducts.value = [...uniqueProducts.value]
  }
}

function loadReports() {
  const saved = localStorage.getItem('saved_reports')
  if (saved) {
    reports.value = JSON.parse(saved)
    selectedProducts.value = [...uniqueProducts.value]
  }
}

const filteredReports = computed(() => {
  let list = reports.value.filter(r => {
    const matchesSearch = r.name.toLowerCase().includes(searchQuery.value.toLowerCase()) ||
                         r.type.toLowerCase().includes(searchQuery.value.toLowerCase())
    const matchesProduct = selectedProducts.value.includes(r.product_name || 'Unknown')
    return matchesSearch && matchesProduct
  })

  list.sort((a: any, b: any) => {
    let valA = a[sortBy.value]
    let valB = b[sortBy.value]
    if (sortBy.value === 'createTime') {
      valA = new Date(valA).getTime()
      valB = new Date(valB).getTime()
    }
    
    if (valA < valB) return sortOrder.value === 'asc' ? -1 : 1
    if (valA > valB) return sortOrder.value === 'asc' ? 1 : -1
    return 0
  })

  return list
})

function sort(field: string) {
  if (sortBy.value === field) {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortBy.value = field
    sortOrder.value = 'desc'
  }
}

function deleteReport(id: string | number) {
  if (confirm('确定要删除该报表记录吗？')) {
    reports.value = reports.value.filter(r => r.id !== id)
    saveToLocal()
  }
}

function startEdit(report: Report) {
  editingId.value = report.id
  editName.value = report.name
}

function saveEdit(report: Report) {
  if (!editName.value.trim()) return
  report.name = editName.value.trim()
  editingId.value = null
  saveToLocal()
}

function saveToLocal() {
  localStorage.setItem('saved_reports', JSON.stringify(reports.value))
}

const vFocus = {
  mounted: (el: HTMLInputElement) => el.focus()
}

onMounted(loadReports)
</script>

<script lang="ts">
export default {
  name: 'ReportCenterView'
}
</script>

<style scoped>
.report-center {
  padding: 24px;
  background: #f0f2f5;
  min-height: 100%;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 0;
  font-size: 20px;
  color: #1a1a1a;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 24px;
}

.filter-group {
  display: flex;
  align-items: center;
  gap: 12px;
}

.filter-label {
  font-size: 13px;
  color: #666;
  font-weight: 500;
  white-space: nowrap;
}

.product-filter-container {
  display: flex;
  align-items: center;
  gap: 10px;
  background: #fff;
  border: 1px solid #d9d9d9;
  padding: 4px 12px;
  border-radius: 6px;
  font-size: 13px;
}

.product-options {
  display: flex;
  align-items: center;
  gap: 12px;
  border-left: 1px solid #eee;
  padding-left: 12px;
  max-width: 500px;
  overflow-x: auto;
}

.all-check, .prod-option {
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  white-space: nowrap;
}

.all-check span { font-weight: bold; color: #1890ff; }

.search-input {
  padding: 8px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  width: 250px;
  font-size: 14px;
  outline: none;
  transition: all 0.3s;
}
.search-input:focus {
  border-color: #1890ff;
  box-shadow: 0 0 0 2px rgba(24,144,255,0.2);
}

.report-list-card {
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  overflow: hidden;
}

.report-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

.report-table th, .report-table td {
  padding: 14px 16px;
  text-align: left;
  border-bottom: 1px solid #f0f0f0;
}

.report-table th {
  background: #fafafa;
  font-weight: 600;
  color: #555;
  cursor: pointer;
  user-select: none;
}
.report-table th:hover { background: #f0f0f0; }

.report-link {
  color: #1890ff;
  text-decoration: none;
  font-weight: 500;
}
.report-link:hover { text-decoration: underline; }

.type-badge {
  background: #e6f7ff;
  color: #1890ff;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  border: 1px solid #91d5ff;
}

.time-cell {
  color: #888;
  font-size: 13px;
}

.actions-cell {
  display: flex;
  gap: 12px;
}

.action-btn {
  background: transparent;
  border: none;
  cursor: pointer;
  font-size: 16px;
  padding: 4px;
  border-radius: 4px;
  transition: background 0.2s;
}
.action-btn:hover { background: #f5f5f5; }
.action-btn.delete:hover { background: #fff1f0; }

.empty-state {
  text-align: center;
  padding: 40px !important;
  color: #999;
}

.name-display {
  display: flex;
  align-items: center;
  gap: 8px;
}

.rename-small {
  font-size: 12px;
  opacity: 0.3;
  transition: opacity 0.2s;
}

.name-cell:hover .rename-small {
  opacity: 1;
}

.comment-cell {
  width: 300px;
}

.inline-comment-input {
  width: 100%;
  height: 32px;
  border: 1px solid transparent;
  background: transparent;
  border-radius: 4px;
  padding: 4px 8px;
  font-size: 13px;
  resize: vertical;
  transition: all 0.2s;
  color: #666;
}

.inline-comment-input:hover {
  background: #f9f9f9;
  border-color: #d9d9d9;
}

.inline-comment-input:focus {
  background: white;
  border-color: #1890ff;
  outline: none;
  box-shadow: 0 0 0 2px rgba(24,144,255,0.1);
  height: 60px;
}
</style>
