

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
            <option value="custom">Custom</option>
          </select>
        </div>

        <div class="option-group" v-if="options.filter_type === 'filter_by_sigma'">
          <label>Sigma</label>
          <input v-model.number="options.sigma" type="number" step="0.5" min="1" max="6" />
        </div>

        <div class="option-group">
          <label>DataRange</label>
          <div class="radio-group">
            <label><input type="radio" v-model="options.data_range" value="final" /> Final</label>
            <label><input type="radio" v-model="options.data_range" value="original" /> Original</label>
            <label><input type="radio" v-model="options.data_range" value="all" /> All</label>
          </div>
        </div>

        <div class="option-group">
          <label>Top Fail</label>
          <input v-model.number="options.top_n" type="number" min="3" max="20" />
        </div>

        <div class="option-group">
          <label>CPK &lt;</label>
          <input v-model.number="options.cpk_filter" type="number" step="0.1" placeholder="1.33" />
        </div>

        <button class="submit-btn" @click="handleSubmit">提交</button>
      </div>

      <!-- 右侧内容区 -->
      <div class="content-area">
        <!-- 顶部双图 -->
        <div class="top-charts" v-if="topFail">
          <div class="chart-box">
            <div ref="topFailChartRef" style="width:100%;height:220px"></div>
          </div>
          <div class="chart-box">
            <div ref="topFailSiteChartRef" style="width:100%;height:220px"></div>
          </div>
        </div>

        <!-- 参数表格 -->
        <div class="table-area">
          <ag-grid-vue
            class="ag-theme-alpine"
            :rowData="testItems"
            :columnDefs="columnDefs"
            :defaultColDef="defaultColDef"
            style="width:100%;height:100%"
            @row-clicked="onRowClicked"
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
const topFail = ref<any>(null)
const itemCount = ref(0)


const topFailChartRef = ref<HTMLElement>()
const topFailSiteChartRef = ref<HTMLElement>()
let topFailChart: echarts.ECharts | null = null
let topFailSiteChart: echarts.ECharts | null = null

const options = ref({
  filter_type: 'all',
  data_range: 'final',
  sigma: 3,
  top_n: 5,
  cpk_filter: null as number | null,
})

const defaultColDef = {
  resizable: true,
  sortable: true,
  filter: true,
  minWidth: 80,
}

const columnDefs = [
  { headerName: '#', field: 'item_number', width: 70, pinned: 'left' },
  {
    headerName: 'TestItem',
    field: 'item_name',
    width: 200,
    pinned: 'left',
    cellStyle: { color: '#1890ff', cursor: 'pointer' },
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
  const data: any[] = await api.get(`/analysis/lot/${lotId.value}/items`, {
    params: { site: 0 }
  })
  let filtered = data
  if (options.value.cpk_filter !== null) {
    filtered = data.filter(item =>
      item.cpk === null || item.cpk < options.value.cpk_filter!
    )
  }
  testItems.value = filtered
  itemCount.value = data.length
}

async function fetchTopFail() {
  topFail.value = await api.get(`/analysis/lot/${lotId.value}/top_fail`, {
    params: { top_n: options.value.top_n }
  })
  await nextTick()
  renderTopFailCharts()
}

function renderTopFailCharts() {
  if (!topFail.value || !topFailChartRef.value) return

  const items = topFail.value.items
  const names = items.map((i: any) => i.item_name)
  const counts = items.map((i: any) => i.fail_count)

  // 左图：All Sites柱状图
  if (!topFailChart) {
    topFailChart = echarts.init(topFailChartRef.value)
  }
  topFailChart.setOption({
    title: { text: 'TOP Fail TestItem Analysis', left: 'center', textStyle: { fontSize: 13 } },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: names, axisLabel: { rotate: 30, fontSize: 11 } },
    yAxis: [
      { type: 'value', name: 'Count' },
      { type: 'value', name: '(%)', max: 100 }
    ],
    series: [
      { type: 'bar', data: counts, itemStyle: { color: '#ff6b6b' } }
    ]
  })

  // 右图：分Site堆叠柱状图
  if (!topFailSiteChart) {
    topFailSiteChart = echarts.init(topFailSiteChartRef.value)
  }
  const sites = topFail.value.sites
  const siteSeries = sites.map((site: number, idx: number) => ({
    type: 'bar',
    name: `Site${site}`,
    stack: 'total',
    data: items.map((item: any) => item.sites[`site${site}`] || 0),
  }))
  topFailSiteChart.setOption({
    title: { text: 'Top Fail TestItem Analysis Per Site', left: 'center', textStyle: { fontSize: 13 } },
    tooltip: { trigger: 'axis' },
    legend: { bottom: 0 },
    xAxis: { type: 'category', data: names, axisLabel: { rotate: 30, fontSize: 11 } },
    yAxis: { type: 'value', name: 'Count' },
    series: siteSeries
  })
}

function onRowClicked(params: any) {
  const paramName = params.data.item_name
  router.push(`/lot/${lotId.value}/param/${encodeURIComponent(paramName)}`)
}

function handleSubmit() {
  fetchItems()
  fetchTopFail()
}

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
  await fetchTopFail()
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

.radio-group label {
  font-size: 12px;
  color: #444;
  display: flex;
  align-items: center;
  gap: 4px;
}

.submit-btn {
  background: #1890ff;
  color: white;
  border: none;
  border-radius: 4px;
  padding: 8px;
  cursor: pointer;
  font-size: 13px;
  margin-top: auto;
}

.submit-btn:hover { background: #40a9ff; }

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
</style>