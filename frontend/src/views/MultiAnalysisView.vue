<template>
  <div class="multi-analysis-view">
    <!-- 顶部LOT信息栏 -->
    <div class="lot-info-bar">
      <div class="info-grid">
        <div class="info-item">
          <span class="label">名称</span>
          <div class="editable-name">
            <input 
              v-model="options.single_lot_name" 
              class="name-input" 
              placeholder="all_lot"
            />
          </div>
        </div>
        <div class="info-item">
          <span class="label">LOT数量</span>
          <span class="value">{{ lots.length }}</span>
        </div>
        <div class="info-item">
          <span class="label">测试项数</span>
          <span class="value">{{ params.length }}</span>
        </div>
        <div class="info-item">
          <span class="label">测试数量</span>
          <span class="value">{{ totalDieCount }}</span>
        </div>
        <div class="info-item">
          <span class="label">PASS数量</span>
          <span class="value">{{ totalPassCount }}</span>
        </div>
        <div class="info-item">
          <span class="label">平均良率</span>
          <span class="value" :style="yieldColor(averageYield)">
            {{ averageYield ? (averageYield * 100).toFixed(2) + '%' : '-' }}
          </span>
        </div>
        <div class="info-item-actions">
          <button 
            class="btn-export" 
            :disabled="exporting" 
            @click="handleExport"
            :style="exporting ? { 
              background: `linear-gradient(to right, #52c41a ${exportProgress}%, #73d13d ${exportProgress}%)`,
              transition: 'background 0.3s'
            } : {}"
          >
            <template v-if="!exporting">📁 导出 Excel</template>
            <template v-else>导出中 {{ exportProgress }}%</template>
          </button>
        </div>
      </div>
    </div>

    <!-- 主体：左侧Options + 右侧表格 -->
    <div class="main-body">
      <!-- 左侧Options面板 -->
      <div class="options-panel">
        <div class="options-title">Options</div>

        <div class="option-group">
          <label>Filter</label>
          <div class="radio-group">
            <label><input type="radio" v-model="options.filter_type" value="all" /> ALL_DATA</label>
            <label><input type="radio" v-model="options.filter_type" value="filter_by_limit" /> Filter by limit</label>
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
      </div>

      <!-- 右侧内容区 -->
      <div class="content-area">
        <div class="table-area">
          <ag-grid-vue
            class="ag-theme-alpine"
            :rowData="gridData"
            :columnDefs="columnDefs"
            :defaultColDef="defaultColDef"
            rowSelection="multiple"
            :suppressRowClickSelection="true"
            style="width:100%;height:100%"
            @grid-ready="onGridReady"
            @cell-clicked="onCellClicked"
          />
        </div>
        <div v-if="loading && !gridData.length" class="loading-overlay">加载中...</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { AgGridVue } from 'ag-grid-vue3'
import api from '@/api'

const route = useRoute()
const router = useRouter()
const lotIdsStr = route.query.lot_ids as string

const lots = ref<any[]>([])
const params = ref<any[]>([])
const lotDetails = ref<any[]>([])
const loading = ref(true)
const gridApi = ref<any>(null)

const options = ref({
  filter_type: 'all',
  sigma: 3,
  chars_row: 3,
  single_lot_name: 'all_lot'
})

const exporting = ref(false)
const exportProgress = ref(0)

// 转换数据为 ag-grid 格式 (合并后的统计数据)
const gridData = computed(() => {
  return params.value.map(p => ({
    item_number: p.item_number,
    item_name: p.item_name,
    unit: p.unit,
    lower_limit: p.lower_limit,
    upper_limit: p.upper_limit,
    ...(p.overall_stats || {})
  }))
})

const totalDieCount = computed(() => {
  if (lotDetails.value.length) {
    return lotDetails.value.reduce((sum, lot) => sum + (lot.die_count || 0), 0)
  }
  return 0
})

const totalPassCount = computed(() => {
  if (lotDetails.value.length) {
    return lotDetails.value.reduce((sum, lot) => sum + (lot.pass_count || 0), 0)
  }
  return 0
})

const averageYield = computed(() => {
  if (lotDetails.value.length) {
    const totalPass = totalPassCount.value
    const totalDie = totalDieCount.value
    return totalDie > 0 ? totalPass / totalDie : 0
  }
  return 0
})

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
  { headerName: 'Min', field: 'min_val', width: 100, valueFormatter: (p: any) => p.value?.toFixed(4) ?? '-' },
  { headerName: 'Max', field: 'max_val', width: 100, valueFormatter: (p: any) => p.value?.toFixed(4) ?? '-' },
  { headerName: 'Exec Qty', field: 'exec_qty', width: 90 },
  { headerName: 'Failures', field: 'fail_count', width: 90 },
  {
    headerName: 'Fail Rate',
    field: 'fail_rate',
    width: 90,
    valueFormatter: (p: any) => {
      const val = p.data.fail_count / p.data.exec_qty
      return isNaN(val) ? '0%' : (val * 100).toFixed(3) + '%'
    }
  },
  {
    headerName: 'Yield',
    field: 'yield_rate',
    width: 90,
    valueFormatter: (p: any) => p.value ? (p.value * 100).toFixed(2) + '%' : '-'
  },
  { headerName: 'Mean', field: 'mean', width: 100, valueFormatter: (p: any) => p.value?.toFixed(4) ?? '-' },
  { headerName: 'Stdev', field: 'stdev', width: 100, valueFormatter: (p: any) => p.value?.toFixed(4) ?? '-' },
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

function onGridReady(params: any) {
  gridApi.value = params.api
}

async function fetchData() {
  loading.value = true
  try {
    const data: any = await api.get('/analysis/multi/items', {
      params: { 
        lot_ids: lotIdsStr,
        filter_type: options.value.filter_type,
        sigma: options.value.sigma,
        data_range: 'final'
      }
    })
    lots.value = data.lots || []
    params.value = data.params || []

    // 首次加载或LOT变化时获取LOT详细信息用于汇总
    if (!lotDetails.value.length && lots.value.length) {
      const details = await Promise.all(
        lots.value.map(l => api.get(`/analysis/lot/${l.id}/info`))
      )
      lotDetails.value = details
    }
  } catch (err: any) {
    console.error('Fetch failed:', err)
    alert('获取数据失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    loading.value = false
  }
}

// 监听选项变化，自动刷新
watch(
  [
    () => options.value.filter_type,
    () => options.value.sigma
  ],
  () => {
    fetchData()
  }
)

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
  
  try {
    const startRes: any = await api.post('/analysis/multi/export_items/start', null, {
      params: { 
        lot_ids: lotIdsStr,
        filter_type: options.value.filter_type,
        sigma: options.value.sigma,
        data_range: 'final',
        chars_row: options.value.chars_row,
        selected_items: selectedItems,
        single_lot_name: options.value.single_lot_name
      }
    })
    
    const taskId = startRes.task_id

    const pollInterval = setInterval(async () => {
      try {
        const statusRes: any = await api.get(`/analysis/export_items/status/${taskId}`)
        const { status, progress, error } = statusRes
        
        if (status === 'completed') {
          clearInterval(pollInterval)
          exportProgress.value = 100
          
          const downloadRes: any = await api.get(`/analysis/export_items/download/${taskId}`, {
            responseType: 'blob'
          })
          
          const url = window.URL.createObjectURL(new Blob([downloadRes.data]))
          const link = document.createElement('a')
          link.href = url
          link.setAttribute('download', `${options.value.single_lot_name}_Report.xlsx`)
          document.body.appendChild(link)
          link.click()
          document.body.removeChild(link)
          window.URL.revokeObjectURL(url)
          
          setTimeout(() => {
            exporting.value = false
          }, 1000)
        } else if (status === 'failed') {
          clearInterval(pollInterval)
          alert('导出失败: ' + error)
          exporting.value = false
        } else {
          exportProgress.value = progress
        }
      } catch (err) {
        clearInterval(pollInterval)
        exporting.value = false
      }
    }, 1000)

  } catch (error) {
    alert('启动导出失败')
    exporting.value = false
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

  // 只有 TestItem 列才跳转
  if (params.colDef.field !== 'item_name') return;

  const paramName = params.data.item_name;
  if (paramName) {
    const url = router.resolve(
      `/multi-param?lot_ids=${lotIdsStr}&param_name=${encodeURIComponent(paramName)}`
    ).href
    window.open(url, '_blank')
  }
}

function yieldColor(val: number) {
  if (!val) return {}
  if (val < 0.8) return { color: 'red' }
  if (val < 0.95) return { color: 'orange' }
  return { color: 'green' }
}

onMounted(fetchData)
</script>

<style scoped>
.multi-analysis-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px;
  background: #f0f2f5;
  overflow: hidden;
}

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
  align-items: center;
  gap: 24px;
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

.editable-name {
  position: relative;
  display: inline-block;
}

.name-input {
  border: 1px solid transparent;
  background: transparent;
  font-size: 13px;
  color: #333;
  font-weight: 500;
  padding: 2px 4px;
  border-radius: 4px;
  width: 120px;
  transition: all 0.2s;
}

.name-input:hover, .name-input:focus {
  border-color: #d9d9d9;
  background: white;
}

.info-item-actions {
  margin-left: auto;
}

.btn-export {
  background: #52c41a;
  color: white;
  border: none;
  border-radius: 4px;
  padding: 6px 16px;
  cursor: pointer;
  font-size: 13px;
}
.btn-export:hover { background: #73d13d; }
.btn-export:disabled { cursor: not-allowed; opacity: 0.8; }

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

.content-area {
  flex: 1;
  background: white;
  border-radius: 6px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  position: relative;
}

.table-area {
  flex: 1;
}

.loading-overlay {
  position: absolute;
  inset: 0;
  background: rgba(255,255,255,0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10;
  color: #999;
  font-size: 14px;
}

:deep(.ag-floating-filter-button) {
  display: none !important;
}
</style>


