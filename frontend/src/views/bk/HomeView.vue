<template>
  <div class="lot-list">
    <!-- 顶部操作栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <button class="btn btn-primary" @click="showUpload = true">⬆ 上传</button>
        <button class="btn" @click="fetchLots">🔄 刷新</button>
        <button class="btn btn-danger" :disabled="!selectedRows.length" @click="handleDelete">
          🗑 删除 {{ selectedRows.length ? `(${selectedRows.length})` : '' }}
        </button>
      </div>
      <div class="toolbar-right">
        <input
          v-model="filters.product_name"
          placeholder="产品名筛选"
          class="filter-input"
          @input="fetchLots"
        />
        <input
          v-model="filters.lot_id"
          placeholder="批号筛选"
          class="filter-input"
          @input="fetchLots"
        />
        <select v-model="filters.status" class="filter-select" @change="fetchLots">
          <option value="">全部状态</option>
          <option value="pending">待处理</option>
          <option value="processing">处理中</option>
          <option value="processed">已完成</option>
          <option value="failed">失败</option>
        </select>
      </div>
    </div>

    <!-- 表格 -->
    <div class="table-container">
      <ag-grid-vue
        class="ag-theme-alpine"
        :rowData="lots"
        :columnDefs="columnDefs"
        :defaultColDef="defaultColDef"
        rowSelection="multiple"
        :pagination="true"
        :paginationPageSize="50"
        @selection-changed="onSelectionChanged"
        @grid-ready="onGridReady"
        style="width: 100%; height: 100%;"
      />
    </div>

    <!-- 上传对话框 -->
    <div v-if="showUpload" class="modal-overlay" @click.self="showUpload = false">
      <div class="modal">
        <h3>上传数据文件</h3>
        <div
          class="drop-zone"
          @dragover.prevent
          @drop.prevent="handleDrop"
          @click="fileInput?.click()"
        >
          <p>点击或拖拽文件到此处</p>
          <p class="hint">支持 .csv / .zip 格式</p>
        </div>
        <input ref="fileInput" type="file" accept=".csv,.zip" multiple hidden @change="handleFileSelect" />
        <div v-if="uploadFiles.length" class="upload-list">
          <div v-for="f in uploadFiles" :key="f.name" class="upload-item">
            <span>{{ f.name }}</span>
            <span class="file-size">{{ formatSize(f.size) }}</span>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn" @click="showUpload = false">取消</button>
          <button class="btn btn-primary" :disabled="!uploadFiles.length || uploading" @click="handleUpload">
            {{ uploading ? '上传中...' : '开始上传' }}
          </button>
        </div>
      </div>
    </div>
  </div>

  <!-- 产品名设置弹窗 -->
  <div v-if="productDialog" class="modal-overlay" @click.self="productDialog = false">
      <div class="modal">
          <h3>设置产品名</h3>
          <div class="field">
              <label>程序名</label>
              <input :value="productForm.program" disabled style="background:#f5f5f5" />
          </div>
          <div class="field">
              <label>匹配前缀</label>
              <input :value="productForm.prefix" disabled style="background:#f5f5f5" />
          </div>
          <div class="field">
              <label>产品名</label>
              <input
                  v-model="productForm.product_name"
                  placeholder="请输入产品名，如 HL5083A-BD"
                  @keyup.enter="saveProductName"
              />
          </div>
          <p style="font-size:12px;color:#999;margin-top:4px">
              保存后所有相同前缀的LOT将自动更新产品名
          </p>
          <div class="modal-actions">
              <button class="btn" @click="productDialog = false">取消</button>
              <button class="btn btn-primary" @click="saveProductName">保存</button>
          </div>
      </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { AgGridVue } from 'ag-grid-vue3'
import type { GridApi, ColDef } from 'ag-grid-community'
import api from '@/api'
import { useRouter } from 'vue-router'

const lots = ref<any[]>([])
const selectedRows = ref<any[]>([])
const showUpload = ref(false)
const uploading = ref(false)
const uploadFiles = ref<File[]>([])
const fileInput = ref<HTMLInputElement>()
const gridApi = ref<GridApi>()
const filters = ref({ product_name: '', lot_id: '', status: '' })
const productDialog = ref(false)
const productForm = ref({ id: 0, program: '', prefix: '', product_name: '' })
const router = useRouter()

const defaultColDef: ColDef = {
  resizable: true,
  sortable: true,
  filter: true,
  minWidth: 80,
}

const columnDefs: ColDef[] = [
  { checkboxSelection: true, headerCheckboxSelection: true, width: 48, pinned: 'left' },
  { headerName: '序号', valueGetter: 'node.rowIndex + 1', width: 70, pinned: 'left' },
  {
    headerName: '操作',
    width: 140,
    pinned: 'left',
    cellRenderer: (p: any) => {
      return `
        <div style="display:flex;gap:6px;align-items:center;height:100%">
          <span style="color:#1890ff;cursor:pointer;font-size:12px" data-action="analysis" data-id="${p.data.id}">参数分析</span>
          <span style="color:#52c41a;cursor:pointer;font-size:12px" data-action="bin" data-id="${p.data.id}">BIN分析</span>
        </div>
      `
    },
    onCellClicked: (p: any) => {
      const target = p.event.target as HTMLElement
      const action = target.dataset.action
      const id = target.dataset.id
      if (action === 'analysis') router.push(`/lot/${id}`)
      if (action === 'bin') router.push(`/lot/${id}/bin`)
    }
  },
  {
    headerName: '文件名',
    field: 'filename',
    width: 220,
    pinned: 'left',
    //cellStyle: { color: '#1890ff', cursor: 'pointer' },
    //onCellClicked: (p: any) => {
    //  router.push(`/lot/${p.data.id}`)
    //}
  },
  { headerName: '产品名', field: 'product_name', width: 140 },
  { headerName: '批号', field: 'lot_id', width: 120 },
  { headerName: '品圆编号', field: 'wafer_id', width: 100 },
  { headerName: '程序', field: 'program', width: 160 },
  { headerName: '测试机', field: 'test_machine', width: 100 },
  { headerName: 'Data Type', field: 'data_type', width: 100 },
  { headerName: '品圆数', field: 'die_count', width: 90 },
  { headerName: '良品数', field: 'pass_count', width: 90 },
  {
    headerName: '良率',
    field: 'yield_rate',
    width: 90,
    valueFormatter: (p) => p.value ? `${(p.value * 100).toFixed(2)}%` : '-',
    cellStyle: (p) => {
      if (!p.value) return {}
      if (p.value < 0.8) return { color: 'red', fontWeight: 'bold' }
      if (p.value < 0.95) return { color: 'orange' }
      return { color: 'green' }
    }
  },
  {
      headerName: '产品名',
      field: 'product_name',
      width: 140,
      cellRenderer: (p: any) => {
          if (p.value) return p.value
          return `<span style="color:#1890ff;cursor:pointer" data-id="${p.data.id}" data-program="${p.data.program}">点击设置</span>`
      },
      onCellClicked: (p: any) => {
          if (!p.data.program) return
          showProductDialog(p.data)
      }
  },
  
  {
    headerName: '状态',
    field: 'status',
    width: 90,
    cellRenderer: (p: any) => {
      const map: Record<string, string> = {
        pending: '<span style="color:#888">待处理</span>',
        processing: '<span style="color:#1890ff">处理中</span>',
        processed: '<span style="color:green">已完成</span>',
        failed: '<span style="color:red">失败</span>',
      }
      return map[p.value] || p.value
    }
  },
  { headerName: '文件大小', field: 'file_size', width: 100, valueFormatter: (p) => p.value ? formatSize(p.value) : '-' },
  { headerName: '测试日期', field: 'test_date', width: 160, valueFormatter: (p) => p.value ? new Date(p.value).toLocaleString() : '-' },
  { headerName: '上传日期', field: 'upload_date', width: 160, valueFormatter: (p) => p.value ? new Date(p.value).toLocaleString() : '-' },
]

function formatSize(bytes: number) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}

async function fetchLots() {
  const params: any = { page: 1, page_size: 200 }
  if (filters.value.product_name) params.product_name = filters.value.product_name
  if (filters.value.lot_id) params.lot_id = filters.value.lot_id
  if (filters.value.status) params.status = filters.value.status
  const data: any = await api.get('/lots', { params })
  console.log('fetchLots response:', data)  // 加这行
  lots.value = data.items
}

async function showProductDialog(row: any) {
    const data: any = await api.get('/products/suggest', {
        params: { program: row.program }
    })
    productForm.value = {
        id: row.id,
        program: row.program,
        prefix: data.prefix,
        product_name: data.product_name || ''
    }
    productDialog.value = true
}

async function saveProductName() {
    await api.post('/products/mapping', {
        prefix: productForm.value.prefix,
        product_name: productForm.value.product_name
    })
    productDialog.value = false
    await fetchLots()
}

function onGridReady(params: any) {
  gridApi.value = params.api
}

function onSelectionChanged() {
  selectedRows.value = gridApi.value?.getSelectedRows() || []
}

function handleDrop(e: DragEvent) {
  const files = Array.from(e.dataTransfer?.files || [])
  uploadFiles.value = files.filter(f => f.name.endsWith('.csv') || f.name.endsWith('.zip'))
}

function handleFileSelect(e: Event) {
  const files = Array.from((e.target as HTMLInputElement).files || [])
  uploadFiles.value = files
}

async function handleUpload() {
  uploading.value = true
  try {
    const formData = new FormData()
    uploadFiles.value.forEach(f => formData.append('files', f))
    await api.post('/lots/upload', formData)
    showUpload.value = false
    uploadFiles.value = []
    await fetchLots()
  } catch (e) {
    alert('上传失败')
  } finally {
    uploading.value = false
  }
}

async function handleDelete() {
  if (!confirm(`确认删除 ${selectedRows.value.length} 条记录？`)) return
  const ids = selectedRows.value.map(r => r.id)
  await api.delete('/lots', { data: { ids } })
  await fetchLots()
}

onMounted(fetchLots)
</script>

<style scoped>
.lot-list {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: white;
  padding: 10px 16px;
  border-radius: 6px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
.toolbar-left, .toolbar-right {
  display: flex;
  gap: 8px;
  align-items: center;
}
.btn {
  padding: 6px 14px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  background: white;
  cursor: pointer;
  font-size: 13px;
}
.btn:hover { background: #f5f5f5; }
.btn-primary { background: #1890ff; color: white; border-color: #1890ff; }
.btn-primary:hover { background: #40a9ff; }
.btn-danger { color: #ff4d4f; border-color: #ff4d4f; }
.btn-danger:disabled { opacity: 0.5; cursor: not-allowed; }
.filter-input, .filter-select {
  padding: 5px 10px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  font-size: 13px;
  height: 32px;
}
.table-container {
  flex: 1;
  background: white;
  border-radius: 6px;
  overflow: hidden;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}

/* 上传弹窗 */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
}
.modal {
  background: white;
  padding: 24px;
  border-radius: 8px;
  width: 440px;
}
.modal h3 { margin-bottom: 16px; font-size: 16px; }
.drop-zone {
  border: 2px dashed #d9d9d9;
  border-radius: 6px;
  padding: 40px;
  text-align: center;
  cursor: pointer;
  color: #666;
  transition: border-color 0.2s;
}
.drop-zone:hover { border-color: #1890ff; }
.hint { font-size: 12px; color: #999; margin-top: 6px; }
.upload-list { margin-top: 12px; }
.upload-item {
  display: flex;
  justify-content: space-between;
  padding: 6px 0;
  border-bottom: 1px solid #f0f0f0;
  font-size: 13px;
}
.file-size { color: #999; }
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
}
</style>