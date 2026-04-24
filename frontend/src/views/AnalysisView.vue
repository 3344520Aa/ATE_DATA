

<template>
  <div class="analysis-view">
    <!-- 顶部LOT信息栏 -->
    <div class="lot-info-bar" v-if="lotInfo">
      <div class="info-grid">
        <div class="info-item">
          <span class="label">名称</span>
          <span class="value">{{ lotInfo.filename }}</span>
        </div>
        <div class="info-item">
          <span class="label">程序</span>
          <span class="value">{{ lotInfo.program }}</span>
        </div>
        <div class="info-item">
          <span class="label">测试机</span>
          <span class="value">{{ lotInfo.test_machine }}</span>
        </div>
        <div class="info-item">
          <span class="label">工位数</span>
          <span class="value">{{ lotInfo.station_count }}</span>
        </div>
        <div class="info-item">
          <span class="label">测试数量</span>
          <span class="value">{{ lotInfo.die_count }}</span>
        </div>
        <div class="info-item">
          <span class="label">测试项数</span>
          <span class="value">{{ itemCount }}</span>
        </div>
        <div class="info-item">
          <span class="label">良率</span>
          <span class="value" :style="yieldColor(lotInfo.yield_rate)">
            {{ lotInfo.yield_rate ? (lotInfo.yield_rate * 100).toFixed(2) + '%' : '-' }}
          </span>
        </div>
        <div class="info-item">
          <span class="label">测试阶段</span>
          <span class="value">{{ lotInfo.data_type }}</span>
        </div>
        <div class="info-item">
            <span class="label">测试日期</span>
            <span class="value">{{ formatDate(lotInfo.test_date) }}</span>
        </div>     
      </div>
      <div class="info-actions">
        <button class="btn-bin" @click="router.push(`/lot/${lotId}/bin`)">📊 BIN分析</button>
      </div>

    </div>

    <!-- 主体：左侧Options + 右侧图表 + 底部表格 -->
    <div class="main-body">
      <!-- 左侧Options面板 -->
      <div class="options-panel">
        <div class="options-title">Options</div>

        <div class="option-group">
          <label>Filter</label>
          <select v-model="options.filter_type">
            <option value="all">All Data</option>
            <option value="robust">Robust Data</option>
            <option value="filter_by_limit">Filter By Limit</option>
            <option value="filter_by_sigma">Filter by Sigma</option>
          </select>
        </div>

        <div class="option-group" v-if="options.filter_type === 'filter_by_sigma'">
          <label>Sigma</label>
          <input v-model.number="options.sigma" type="number" step="0.5" min="1" max="6" />
        </div>

        <div class="option-group">
          <label>DataRange</label>
          <div class="radio-group row">
            <label><input type="radio" v-model="options.data_range" value="final" /> Final</label>
            <label><input type="radio" v-model="options.data_range" value="original" /> Original</label>
          </div>
        </div>

        <div class="option-group">
          <label>chars_row</label>
          <div class="radio-group row">
            <label><input type="radio" v-model="options.chars_row" :value="1" /> 1</label>
            <label><input type="radio" v-model="options.chars_row" :value="3" /> 3</label>
            <label><input type="radio" v-model="options.chars_row" :value="5" /> 5</label>
          </div>
        </div>

        <button class="export-btn" :disabled="exporting" @click="handleExport">
          <template v-if="!exporting">导出 Excel</template>
          <div v-else class="progress-circle">
            <svg viewBox="0 0 36 36">
              <path class="circle-bg" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
              <path class="circle" :style="{ strokeDasharray: `${exportProgress}, 100` }" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
              <text x="18" y="20.35" class="percentage">{{ exportProgress }}%</text>
            </svg>
          </div>
        </button>
      </div>

      <!-- 右侧内容区 -->
      <div class="content-area">
        <!-- 参数表格 -->
        <div class="table-area">
          <ag-grid-vue
            class="ag-theme-alpine"
            :rowData="testItems"
            :columnDefs="columnDefs"
            :defaultColDef="defaultColDef"
            rowSelection="multiple"
            :suppressRowClickSelection="true"
            style="width:100%;height:100%"
            @grid-ready="onGridReady"
            @cell-clicked="onCellClicked"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { AgGridVue } from 'ag-grid-vue3'
import * as echarts from 'echarts'
import api from '@/api'

const route = useRoute()
const router = useRouter()
const lotId = ref<number>(Number(route.params.id))

const lotInfo = ref<any>(null)
const testItems = ref<any[]>([])
const itemCount = ref(0)
const gridApi = ref<any>(null)

function onGridReady(params: any) {
  gridApi.value = params.api
}

const options = ref({
  filter_type: 'all',
  data_range: 'final',
  sigma: 3,
  chars_row: 3,
})

const exporting = ref(false)
const exportProgress = ref(0)

const defaultColDef = {
  resizable: true,
  sortable: true,
  filter: true,
  minWidth: 80,
}

const columnDefs: any[] = [
  { 
    headerName: '#', 
    field: 'item_number', 
    width: 90, 
    pinned: 'left',
    checkboxSelection: true,
    headerCheckboxSelection: true,
    filter: true,
    floatingFilter: true,
    suppressMenu: false,
    suppressHeaderMenuButton: false,
    suppressHeaderFilterButton: false,
    floatingFilterComponentParams: { suppressFilterButton: true }
  },
  {
    headerName: 'TestItem',
    field: 'item_name',
    width: 200,
    pinned: 'left',
    cellStyle: { color: '#1890ff', cursor: 'pointer' },
    filter: true,
    floatingFilter: true,
    suppressMenu: false,
    suppressHeaderMenuButton: false,
    suppressHeaderFilterButton: false,
    floatingFilterComponentParams: { suppressFilterButton: true }
  },
  { headerName: 'L.Limit', field: 'lower_limit', width: 100 },
  { headerName: 'U.Limit', field: 'upper_limit', width: 100 },
  { headerName: 'Units', field: 'unit', width: 80 },
  { headerName: 'Min', field: 'min_val', width: 100 },
  { headerName: 'Max', field: 'max_val', width: 100 },
  { headerName: 'Exec Qty', field: 'exec_qty', width: 90 },
  { headerName: 'Failures', field: 'fail_count', width: 90 },
  {
    headerName: 'Fail Rate',
    field: 'fail_rate',
    width: 90,
    valueFormatter: (p: any) => p.value ? (p.value * 100).toFixed(3) + '%' : '0%'
  },
  {
    headerName: 'Yield',
    field: 'yield_rate',
    width: 90,
    valueFormatter: (p: any) => p.value ? (p.value * 100).toFixed(2) + '%' : '-'
  },
  { headerName: 'Mean', field: 'mean', width: 100, valueFormatter: (p: any) => p.value?.toFixed(4) ?? '-' },
  { headerName: 'Stdev', field: 'stdev', width: 100, valueFormatter: (p: any) => p.value?.toFixed(4) ?? '-' },
  { headerName: 'CPU', field: 'cpu', width: 90, valueFormatter: (p: any) => p.value?.toFixed(4) ?? '-' },
  { headerName: 'CPL', field: 'cpl', width: 90, valueFormatter: (p: any) => p.value?.toFixed(4) ?? '-' },
  {
    headerName: 'CPK',
    field: 'cpk',
    width: 90,
    valueFormatter: (p: any) => p.value?.toFixed(4) ?? '-',
    cellStyle: (p: any) => {
      if (p.value === null || p.value === undefined) return {}
      if (p.value < 1.0) return { color: 'red', fontWeight: 'bold' }
      if (p.value < 1.33) return { color: 'orange' }
      return {}
    }
  },
]

async function fetchLotInfo() {
  lotInfo.value = await api.get(`/analysis/lot/${lotId.value}/info`)
}

async function fetchItems() {
  const data: any[] = await api.get(`/analysis/lot/${lotId.value}/items_summary`, {
    params: { 
      filter_type: options.value.filter_type,
      sigma: options.value.sigma,
      data_range: options.value.data_range
    }
  })
  testItems.value = data
  itemCount.value = data.length
}

async function handleExport() {
  if (exporting.value) return
  
  let selectedItems = ''
  if (gridApi.value) {
    const selectedNodes = gridApi.value.getSelectedNodes()
    if (selectedNodes.length > 0) {
      selectedItems = selectedNodes.map((node: any) => node.data.item_number).join(',')
    }
  }

  exporting.value = true
  exportProgress.value = 0
  
  // 模拟进度（因为后端是同步生成的）
  const timer = setInterval(() => {
    if (exportProgress.value < 95) {
      exportProgress.value += Math.floor(Math.random() * 5) + 1
    }
  }, 500)

  try {
    const response: any = await api.get(`/analysis/lot/${lotId.value}/export_items`, {
      params: { 
        filter_type: options.value.filter_type,
        sigma: options.value.sigma,
        data_range: options.value.data_range,
        chars_row: options.value.chars_row,
        selected_items: selectedItems
      },
      responseType: 'blob'
    })
    
    exportProgress.value = 100
    setTimeout(() => {
      const url = window.URL.createObjectURL(new Blob([response.data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `LOT_${lotId.value}_stats_${options.value.filter_type}.xlsx`)
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
      exporting.value = false
    }, 200)
  } catch (error) {
    console.error('Export failed', error)
    exporting.value = false
  } finally {
    clearInterval(timer)
  }
}


function onCellClicked(params: any) {
  if (params.colDef.field === 'item_number') {
    const target = params.event.target as HTMLElement;
    if (target && !target.closest('.ag-checkbox')) {
      params.node.setSelected(!params.node.isSelected());
    }
    return;
  }

  const paramName = params.data.item_name;
  if (paramName) {
    const url = router.resolve(`/lot/${lotId.value}/param/${encodeURIComponent(paramName)}`).href;
    window.open(url, '_blank');
  }
}

watch([
  () => options.value.filter_type,
  () => options.value.sigma,
  () => options.value.data_range
], () => {
  fetchItems()
})

function yieldColor(val: number) {
  if (!val) return {}
  if (val < 0.8) return { color: 'red' }
  if (val < 0.95) return { color: 'orange' }
  return { color: 'green' }
}

function formatDate(d: string) {
  if (!d) return '-'
  return new Date(d).toLocaleString()
}

onMounted(async () => {
  await fetchLotInfo()
  await fetchItems()
})
</script>

<style scoped>
.analysis-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.lot-info-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.info-actions {
  flex-shrink: 0;
}

.btn-bin {
  background: #52c41a;
  color: white;
  border: none;
  border-radius: 4px;
  padding: 6px 16px;
  cursor: pointer;
  font-size: 13px;
}

.btn-bin:hover { background: #73d13d; }

.lot-info-bar {
  background: white;
  padding: 12px 16px;
  border-radius: 6px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  flex-shrink: 0;
}

.info-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.label {
  font-size: 11px;
  color: #999;
}

.value {
  font-size: 13px;
  color: #333;
  font-weight: 500;
}

.main-body {
  flex: 1;
  display: flex;
  gap: 12px;
  overflow: hidden;
}

.options-panel {
  width: 180px;
  background: white;
  border-radius: 6px;
  padding: 12px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow-y: auto;
}

.options-title {
  font-size: 13px;
  font-weight: 600;
  color: #333;
  border-bottom: 1px solid #f0f0f0;
  padding-bottom: 8px;
}

.option-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.option-group label {
  font-size: 12px;
  color: #666;
}

.option-group select,
.option-group input[type="number"] {
  padding: 4px 8px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  font-size: 12px;
}

.radio-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.radio-group.row {
  flex-direction: row;
  gap: 12px;
}

.radio-group label {
  font-size: 12px;
  color: #444;
  display: flex;
  align-items: center;
  gap: 4px;
}

.export-btn {
  background: white;
  color: #1890ff;
  border: 1px solid #1890ff;
  border-radius: 4px;
  padding: 8px;
  cursor: pointer;
  font-size: 13px;
  margin-top: auto;
}

.export-btn:hover { background: #f0faff; }
.export-btn:disabled { opacity: 0.8; cursor: not-allowed; }

.progress-circle {
  width: 28px;
  height: 28px;
  margin: 0 auto;
}
.progress-circle svg {
  width: 100%;
  height: 100%;
}
.circle-bg {
  fill: none;
  stroke: #eee;
  stroke-width: 3.8;
}
.circle {
  fill: none;
  stroke: #1890ff;
  stroke-width: 3.8;
  stroke-linecap: round;
  transition: stroke-dasharray 0.3s ease;
}
.percentage {
  fill: #1890ff;
  font-family: sans-serif;
  font-size: 0.5em;
  text-anchor: middle;
  font-weight: bold;
}

.content-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: hidden;
}

.top-charts {
  display: flex;
  gap: 12px;
  flex-shrink: 0;
}

.chart-box {
  flex: 1;
  background: white;
  border-radius: 6px;
  padding: 8px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}

.table-area {
  flex: 1;
  background: white;
  border-radius: 6px;
  overflow: hidden;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}

:deep(.ag-floating-filter-button) {
  display: none !important;
}
</style>