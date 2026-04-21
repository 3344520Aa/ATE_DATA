<template>
  <div class="param-view">
    <!-- Tab栏 -->
    <div class="tab-bar">
      <div
        v-for="tab in tabs"
        :key="tab.id"
        :class="['tab', { active: activeTab === tab.id }]"
        @click="activeTab = tab.id"
      >
        {{ tab.title }}
        <span class="tab-close" @click.stop="closeTab(tab.id)">×</span>
      </div>
    </div>

    <!-- Tab内容 -->
    <div class="tab-content" v-if="currentTab">
      <!-- 顶部Options -->
      <div class="options-bar">
        <div class="options-left">
          <div class="nav-group">
            <button @click="prevParam">◀ PREV</button>
            <select v-model="currentParamName" @change="addTab">
              <option v-for="item in paramList" :key="item.item_name" :value="item.item_name">
                {{ item.item_number }}:{{ item.item_name }}
              </option>
            </select>
            <button @click="nextParam">NEXT ▶</button>
          </div>

          <div class="option-item">
            <label>Filter</label>
            <select v-model="draftOptions.filter_type">
              <option value="all">All Data</option>
              <option value="robust">Robust Data</option>
              <option value="filter_by_limit">Filter By Limit</option>
              <option value="filter_by_sigma">Filter by Sigma</option>
            </select>
          </div>

          <div class="option-item" v-if="draftOptions.filter_type === 'filter_by_sigma'">
            <label>Sigma</label>
            <input v-model.number="draftOptions.sigma" type="number" step="0.5" min="1" max="6" style="width:60px" />
          </div>

          <div class="option-item">
            <label>DataRange</label>
            <label><input type="radio" v-model="draftOptions.data_range" value="final" /> Final</label>
            <label><input type="radio" v-model="draftOptions.data_range" value="original" /> Original</label>
            <label><input type="radio" v-model="draftOptions.data_range" value="all" /> All</label>
          </div>

          <div class="option-item">
            <label>Chart</label>
            <label><input type="checkbox" v-model="draftOptions.show_histogram" /> Histogram</label>
            <label><input type="checkbox" v-model="draftOptions.show_scatter" /> Scatter</label>
            <label><input type="checkbox" v-model="draftOptions.show_map" /> Map Chart</label>
          </div>
        </div>

        <button class="submit-btn" @click="handleSubmit">提交</button>
      </div>

      <!-- Pass Bin 表 -->
      <div class="content-row">
        <div class="charts-area">
          <!-- 统计汇总行 -->
          <div class="stats-table" v-if="currentTab.data">
            <table>
              <thead>
                <tr>
                  <th>SITE</th>
                  <th>Passes</th>
                  <th>Failures</th>
                  <th>Exec Qty</th>
                  <th>Yield</th>
                  <th>Min</th>
                  <th>Max</th>
                  <th>Mean</th>
                  <th>Stdev</th>
                  <th>CPK</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="s in currentTab.data.sites" :key="s.site">
                  <td>{{ s.site === 0 ? 'ALL' : `Site${s.site}` }}</td>
                  <td>{{ s.stats.exec_qty - s.stats.fail_count }}</td>
                  <td>{{ s.stats.fail_count }}</td>
                  <td>{{ s.stats.exec_qty }}</td>
                  <td>{{ s.stats.yield_rate ? (s.stats.yield_rate * 100).toFixed(2) + '%' : '-' }}</td>
                  <td>{{ s.stats.min_val?.toFixed(4) ?? '-' }}</td>
                  <td>{{ s.stats.max_val?.toFixed(4) ?? '-' }}</td>
                  <td>{{ s.stats.mean?.toFixed(4) ?? '-' }}</td>
                  <td>{{ s.stats.stdev?.toFixed(4) ?? '-' }}</td>
                  <td :style="cpkColor(s.stats.cpk)">{{ s.stats.cpk?.toFixed(4) ?? '-' }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- 直方图 -->
          <div v-if="currentTab.options.show_histogram && currentTab.data" class="chart-container">
            <div :ref="el => setChartRef(currentTab.id, 'hist', el)" style="width:800px;height:320px"></div>
          </div>

          <!-- Scatter图 -->
          <div v-if="currentTab.options.show_scatter && currentTab.data" class="chart-container">
            <div :ref="el => setChartRef(currentTab.id, 'scatter', el)" style="width:800px;height:260px"></div>
          </div>

          <!-- Wafer Map -->
          <div v-if="currentTab.options.show_map && currentTab.data" class="chart-container">
            <canvas
              :ref="el => setChartRef(currentTab.id, 'wafer', el)"
              width="600"
              height="600"
              style="width:600px;height:600px"
            ></canvas>
          </div>
        </div>

        <!-- Pass Bin 表（右侧） -->
        <div class="bin-table">
          <div class="bin-title">Pass Bin</div>
          <table v-if="binSummary">
            <thead>
              <tr><th>Bin</th><th>Name</th><th>Count</th></tr>
            </thead>
            <tbody>
              <tr v-for="b in binSummary" :key="b.bin_number">
                <td>{{ b.bin_number }}</td>
                <td>{{ b.bin_name }}</td>
                <td>{{ b.all_site_count }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import * as echarts from 'echarts'
import api from '@/api'

const route = useRoute()
const lotId = ref(Number(route.params.id))
const initialParam = ref(decodeURIComponent(route.params.param as string))

const paramList = ref<any[]>([])
const binSummary = ref<any[]>([])
const currentParamName = ref(initialParam.value)
const activeTab = ref('')
const tabCounter = ref(0)

interface Tab {
  id: string
  title: string
  param_name: string
  options: any
  data: any
}

const tabs = ref<Tab[]>([])
const currentTab = computed(() => tabs.value.find(t => t.id === activeTab.value))

const draftOptions = ref({
  filter_type: 'all',
  data_range: 'final',
  sigma: 3,
  show_histogram: true,
  show_scatter: true,
  show_map: true,
})

// 图表实例存储
const chartInstances: Record<string, any> = {}

function setChartRef(tabId: string, type: string, el: any) {
  if (!el) return
  const key = `${tabId}_${type}`
  if (type === 'wafer') {
    chartInstances[key] = el
    nextTick(() => renderWaferMap(tabId, el))
  } else {
    if (!chartInstances[key]) {
      chartInstances[key] = echarts.init(el)
    }
    nextTick(() => {
      if (type === 'hist') renderHistogram(tabId)
      if (type === 'scatter') renderScatter(tabId)
    })
  }
}

async function fetchParamList() {
  paramList.value = await api.get(`/analysis/lot/${lotId.value}/items`, { params: { site: 0 } })
}

async function fetchBinSummary() {
  const data: any = await api.get(`/analysis/lot/${lotId.value}/bin_summary`)
  binSummary.value = data.bins
}

async function fetchParamData(paramName: string, options: any) {
  return await api.get(`/analysis/lot/${lotId.value}/param_data`, {
    params: {
      param_name: paramName,
      filter_type: options.filter_type,
      sigma: options.sigma,
      data_range: options.data_range,
    }
  })
}

function addTab() {
  const paramName = currentParamName.value
  tabCounter.value++
  const tabId = `tab_${tabCounter.value}`
  const paramItem = paramList.value.find(p => p.item_name === paramName)
  const title = `${paramItem?.item_number ?? ''}:${paramName} #${tabCounter.value}`

  const newTab: Tab = {
    id: tabId,
    title,
    param_name: paramName,
    options: { ...draftOptions.value },
    data: null,
  }

  // 最多10个Tab
  if (tabs.value.length >= 10) {
    tabs.value.shift()
  }

  tabs.value.push(newTab)
  activeTab.value = tabId

  loadTabData(tabId)
}

async function loadTabData(tabId: string) {
  const tab = tabs.value.find(t => t.id === tabId)
  if (!tab) return
  const data = await fetchParamData(tab.param_name, tab.options)
  tab.data = data
  await nextTick()
  renderCharts(tabId)
}

function handleSubmit() {
  addTab()
}

function closeTab(tabId: string) {
  const idx = tabs.value.findIndex(t => t.id === tabId)
  tabs.value.splice(idx, 1)
  if (activeTab.value === tabId) {
    activeTab.value = tabs.value[tabs.value.length - 1]?.id ?? ''
  }
  // 清理图表实例
  Object.keys(chartInstances).filter(k => k.startsWith(tabId)).forEach(k => {
    if (chartInstances[k]?.dispose) chartInstances[k].dispose()
    delete chartInstances[k]
  })
}

function prevParam() {
  const idx = paramList.value.findIndex(p => p.item_name === currentParamName.value)
  if (idx > 0) {
    currentParamName.value = paramList.value[idx - 1].item_name
    addTab()
  }
}

function nextParam() {
  const idx = paramList.value.findIndex(p => p.item_name === currentParamName.value)
  if (idx < paramList.value.length - 1) {
    currentParamName.value = paramList.value[idx + 1].item_name
    addTab()
  }
}

// ── 图表渲染 ──────────────────────────────────────────
const SITE_COLORS = ['#ff6b6b', '#4dabf7', '#69db7c', '#ffd43b', '#e599f7', '#74c0fc', '#a9e34b', '#ffa94d']

function renderCharts(tabId: string) {
  renderHistogram(tabId)
  renderScatter(tabId)
}

function renderHistogram(tabId: string) {
  const tab = tabs.value.find(t => t.id === tabId)
  if (!tab?.data) return
  const chart = chartInstances[`${tabId}_hist`]
  if (!chart) return

  const { sites, param_name, unit, lower_limit, upper_limit } = tab.data
  const allSites = sites.filter((s: any) => s.site > 0)

  const series = allSites.map((s: any, idx: number) => ({
    type: 'bar',
    name: `Site${s.site}`,
    data: s.histogram.counts,
    itemStyle: {
      color: SITE_COLORS[idx % SITE_COLORS.length],
      opacity: 0.7
    },
    barGap: '-100%',
  }))

  // X轴标签（用bin中心值）
  const edges = allSites[0]?.histogram.edges ?? []
  const xLabels = edges.slice(0, -1).map((e: number, i: number) =>
    ((e + edges[i + 1]) / 2).toFixed(2)
  )

  // 找LL/UL对应的bin索引
  //const edges = allSites[0]?.histogram.edges ?? []
  function findBinIndex(val: number): number {
    for (let i = 0; i < edges.length - 1; i++) {
      if (val >= edges[i] && val <= edges[i + 1]) return i
    }
    if (val < edges[0]) return 0
    return edges.length - 2
  }

  const markLines: any[] = []
  if (lower_limit !== null) markLines.push({
    xAxis: findBinIndex(lower_limit),
    label: { formatter: `LL:${lower_limit}`, position: 'insideStartTop' },
    lineStyle: { color: 'red', type: 'dashed', width: 1.5 }
  })
  if (upper_limit !== null) markLines.push({
    xAxis: findBinIndex(upper_limit),
    label: { formatter: `UL:${upper_limit}`, position: 'insideStartTop' },
    lineStyle: { color: 'red', type: 'dashed', width: 1.5 }
  })

  // All Sites统计信息
  const allStats = sites.find((s: any) => s.site === 0)?.stats ?? sites[0]?.stats

  chart.setOption({
    title: {
      text: `${param_name}`,
      subtext: allStats ? `Min=${allStats.min_val?.toFixed(4)} Max=${allStats.max_val?.toFixed(4)} Mean=${allStats.mean?.toFixed(4)} Stdev=${allStats.stdev?.toFixed(4)} CPK=${allStats.cpk?.toFixed(4)}` : '',
      left: 'center',
      textStyle: { fontSize: 13 },
      subtextStyle: { fontSize: 11, color: '#666' }
    },
    tooltip: { trigger: 'axis' },
    legend: { bottom: 0, data: allSites.map((s: any) => `Site${s.site}`) },
    xAxis: {
      type: 'category',
      data: xLabels,
      name: unit,
      axisLabel: { rotate: 30, fontSize: 10 }
    },
    yAxis: [
      { type: 'value', name: 'Parts' },
      { type: 'value', name: 'Percent(%)', max: 100 }
    ],
    series: [
      ...series,
      {
        type: 'line',
        data: [],
        markLine: {
          silent: true,
          symbol: 'none',
          data: markLines
        }
      }
    ]
  })
}

function renderScatter(tabId: string) {
  const tab = tabs.value.find(t => t.id === tabId)
  if (!tab?.data) return
  const chart = chartInstances[`${tabId}_scatter`]
  if (!chart) return

  const { sites, unit, lower_limit, upper_limit } = tab.data
  const allSites = sites.filter((s: any) => s.site > 0)

  const series: any[] = allSites.map((s: any, idx: number) => ({
    type: 'scatter',
    name: `Site${s.site}`,
    data: s.scatter.map((p: any) => [p.idx, p.val]),
    symbolSize: 3,
    itemStyle: { color: SITE_COLORS[idx % SITE_COLORS.length], opacity: 0.6 }
  }))

  // 加一个空的line系列用于markLine
  series.push({
    type: 'line',
    data: [],
    markLine: {
      silent: true,
      symbol: 'none',
      data: [
        ...(lower_limit !== null ? [{
          yAxis: lower_limit,
          label: { formatter: `LL:${lower_limit}`, position: 'end' },
          lineStyle: { color: 'red', type: 'dashed' }
        }] : []),
        ...(upper_limit !== null ? [{
          yAxis: upper_limit,
          label: { formatter: `UL:${upper_limit}`, position: 'end' },
          lineStyle: { color: 'red', type: 'dashed' }
        }] : []),
      ]
    }
  })

 // 计算Y轴范围，留10%余量
  const allVals = allSites.flatMap((s: any) => s.scatter.map((p: any) => p.val))
  const dataMin = Math.min(...allVals)
  const dataMax = Math.max(...allVals)
  const padding = (dataMax - dataMin) * 0.1 || 0.1

  // Y轴范围取数据范围和Limit范围的并集，再加余量
  const yMin = Math.min(dataMin, lower_limit ?? dataMin) - padding
  const yMax = Math.max(dataMax, upper_limit ?? dataMax) + padding

  chart.setOption({
    tooltip: { trigger: 'item' },
    legend: { bottom: 0 },
    xAxis: { type: 'value', name: 'Index' },
    yAxis: {
      type: 'value',
      name: unit,
      min: parseFloat(yMin.toFixed(4)),
      max: parseFloat(yMax.toFixed(4)),
    },
    series
  })
}

function renderWaferMap(tabId: string, canvas: HTMLCanvasElement) {
  const tab = tabs.value.find(t => t.id === tabId)
  if (!tab?.data) return

  const allData: any[] = []
  tab.data.sites.forEach((s: any) => {
    if (s.wafer_map) allData.push(...s.wafer_map)
  })
  if (allData.length === 0) return

  const ctx = canvas.getContext('2d')
  if (!ctx) return

  const vals = allData.map(d => d.val)
  const minVal = Math.min(...vals)
  const maxVal = Math.max(...vals)

  const xs = allData.map(d => d.x)
  const ys = allData.map(d => d.y)
  const minX = Math.min(...xs), maxX = Math.max(...xs)
  const minY = Math.min(...ys), maxY = Math.max(...ys)

  const W = canvas.width
  const H = canvas.height
  const margin = 30
  const cellW = (W - margin * 2) / (maxX - minX + 1)
  const cellH = (H - margin * 2) / (maxY - minY + 1)
  const cellSize = Math.min(cellW, cellH) - 1

  ctx.clearRect(0, 0, W, H)

  // 找最外圈die
  const coordSet = new Set(allData.map(d => `${d.x},${d.y}`))
  function isEdge(x: number, y: number): boolean {
    return !coordSet.has(`${x-1},${y}`) || !coordSet.has(`${x+1},${y}`) ||
           !coordSet.has(`${x},${y-1}`) || !coordSet.has(`${x},${y+1}`)
  }

  function valToColor(val: number, alpha: number = 1): string {
    const ratio = maxVal === minVal ? 0.5 : (val - minVal) / (maxVal - minVal)
    // 蓝→绿→红
    let r, g, b
    if (ratio < 0.5) {
      r = 0; g = Math.round(ratio * 2 * 255); b = Math.round((1 - ratio * 2) * 255)
    } else {
      r = Math.round((ratio - 0.5) * 2 * 255); g = Math.round((1 - (ratio - 0.5) * 2) * 255); b = 0
    }
    return `rgba(${r},${g},${b},${alpha})`
  }

  allData.forEach(d => {
    const px = margin + (d.x - minX) * cellW + cellW / 2 - cellSize / 2
    const py = margin + (d.y - minY) * cellH + cellH / 2 - cellSize / 2
    ctx.fillStyle = valToColor(d.val)
    ctx.fillRect(px, py, cellSize, cellSize)
  })
}

function cpkColor(val: number | null) {
  if (val === null || val === undefined) return {}
  if (val < 1.0) return { color: 'red', fontWeight: 'bold' }
  if (val < 1.33) return { color: 'orange' }
  return {}
}

onMounted(async () => {
  await fetchParamList()
  await fetchBinSummary()
  addTab()
})
</script>

<style scoped>
.param-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tab-bar {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
  background: white;
  padding: 8px 12px 0;
  border-radius: 6px 6px 0 0;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  overflow-x: auto;
}

.tab {
  padding: 6px 16px;
  border: 1px solid #d9d9d9;
  border-bottom: none;
  border-radius: 4px 4px 0 0;
  cursor: pointer;
  font-size: 12px;
  white-space: nowrap;
  background: #f5f5f5;
  display: flex;
  align-items: center;
  gap: 8px;
}

.tab.active {
  background: white;
  border-color: #1890ff;
  color: #1890ff;
}

.tab-close {
  font-size: 14px;
  color: #999;
  line-height: 1;
}

.tab-close:hover { color: red; }

.tab-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow: hidden;
  background: white;
  border-radius: 0 6px 6px 6px;
  padding: 12px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}

.options-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-shrink: 0;
  flex-wrap: wrap;
  border-bottom: 1px solid #f0f0f0;
  padding-bottom: 10px;
}

.options-left {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
  flex: 1;
}

.nav-group {
  display: flex;
  align-items: center;
  gap: 6px;
}

.nav-group button {
  padding: 4px 10px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  background: white;
  cursor: pointer;
  font-size: 12px;
}

.nav-group select {
  padding: 4px 8px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  font-size: 12px;
  max-width: 300px;
}

.option-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}

.option-item label { color: #666; }

.option-item select, .option-item input[type="number"] {
  padding: 3px 6px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  font-size: 12px;
}

.submit-btn {
  background: #1890ff;
  color: white;
  border: none;
  border-radius: 4px;
  padding: 6px 20px;
  cursor: pointer;
  font-size: 13px;
  flex-shrink: 0;
}

.content-row {
  flex: 1;
  display: flex;
  gap: 12px;
  overflow-y: auto;
  overflow-x: hidden;
}

.charts-area {
  width: 820px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.stats-table table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.stats-table th, .stats-table td {
  border: 1px solid #f0f0f0;
  padding: 4px 8px;
  text-align: center;
}

.stats-table th {
  background: #fafafa;
  color: #666;
}

.chart-container {
  background: #fafafa;
  border-radius: 4px;
  padding: 8px;
  flex-shrink: 0;
  display: flex;
  justify-content: center;
}

.bin-table {
  width: 200px;
  flex-shrink: 0;
}

.bin-title {
  font-size: 12px;
  font-weight: 600;
  color: #333;
  margin-bottom: 6px;
}

.bin-table table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}

.bin-table th, .bin-table td {
  border: 1px solid #f0f0f0;
  padding: 3px 6px;
}

.bin-table th { background: #fafafa; }
</style>