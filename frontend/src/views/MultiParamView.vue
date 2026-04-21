<template>
  <div class="multi-param-view">
    <!-- 顶部Options -->
    <div class="options-bar">
      <div class="nav-group">
        <button @click="prevParam">◀ PREV</button>
        <select v-model="currentParamName" @change="loadData">
          <option v-for="p in paramList" :key="p.item_name" :value="p.item_name">
            {{ p.item_number }}:{{ p.item_name }}
          </option>
        </select>
        <button @click="nextParam">NEXT ▶</button>
      </div>

      <div class="opt-item">
        <label>Filter</label>
        <select v-model="options.filter_type" @change="loadData">
          <option value="all">All Data</option>
          <option value="robust">Robust Data</option>
          <option value="filter_by_limit">Filter By Limit</option>
          <option value="filter_by_sigma">Filter by Sigma</option>
        </select>
      </div>

      <div class="opt-item" v-if="options.filter_type === 'filter_by_sigma'">
        <label>Sigma</label>
        <input v-model.number="options.sigma" type="number" step="0.5" min="1" max="6" style="width:60px" />
        <button @click="loadData">Apply</button>
      </div>

      <div class="opt-item">
        <label>DataRange</label>
        <label><input type="radio" v-model="options.data_range" value="final" @change="loadData" /> Final</label>
        <label><input type="radio" v-model="options.data_range" value="original" @change="loadData" /> Original</label>
      </div>

      <div class="opt-item">
        <label>Mode</label>
        <label><input type="radio" v-model="histMode" value="lot" @change="renderHist" /> LOT</label>
        <label><input type="radio" v-model="histMode" value="single" @change="renderHist" /> Single</label>
      </div>
    </div>

    <!-- 统计汇总表 -->
    <div class="stats-wrap" v-if="histData">
      <table class="stats-table">
        <thead>
          <tr>
            <th>LOT</th>
            <th>Exec Qty</th>
            <th>Failures</th>
            <th>Yield</th>
            <th>L.Limit</th>
            <th>U.Limit</th>
            <th>Min</th>
            <th>Max</th>
            <th>Mean</th>
            <th>Stdev</th>
            <th>CPK</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(lot, idx) in histData.lots" :key="lot.lot_id">
            <td>
              <span class="lot-dot" :style="{ background: LOT_COLORS[idx % LOT_COLORS.length] }"></span>
              {{ lot.filename }}
            </td>
            <td>{{ lot.stats?.exec_qty ?? '-' }}</td>
            <td>{{ lot.stats?.fail_count ?? '-' }}</td>
            <td>{{ lot.stats?.yield_rate != null ? (lot.stats.yield_rate * 100).toFixed(2) + '%' : '-' }}</td>
            <td>{{ histData.lower_limit ?? '-' }}</td>
            <td>{{ histData.upper_limit ?? '-' }}</td>
            <td>{{ fmtNum(lot.stats?.min_val) }}</td>
            <td>{{ fmtNum(lot.stats?.max_val) }}</td>
            <td>{{ fmtNum(lot.stats?.mean) }}</td>
            <td>{{ fmtNum(lot.stats?.stdev) }}</td>
            <td :style="cpkStyle(lot.stats?.cpk)">{{ fmtNum(lot.stats?.cpk) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 直方图 -->
    <div class="chart-wrap">
      <div ref="histChartRef" style="width:100%;height:400px"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import * as echarts from 'echarts'
import api from '@/api'

const route = useRoute()
const lotIdsStr = route.query.lot_ids as string
const initialParam = decodeURIComponent(route.query.param_name as string || '')

const currentParamName = ref(initialParam)
const paramList = ref<any[]>([])
const histData = ref<any>(null)
const histChartRef = ref<HTMLElement>()
let histChart: echarts.ECharts | null = null
const histMode = ref<'lot' | 'single'>('lot')

const LOT_COLORS = ['#4dabf7', '#ff6b6b', '#69db7c', '#ffd43b', '#e599f7', '#ffa94d', '#74c0fc', '#a9e34b']

const options = ref({
  filter_type: 'all',
  data_range: 'final',
  sigma: 3,
})

async function fetchParamList() {
  // 从第一个LOT拿参数列表
  const firstId = lotIdsStr.split(',')[0]
  paramList.value = await api.get(`/analysis/lot/${firstId}/items`, { params: { site: 0 } })
}

async function loadData() {
  if (!currentParamName.value) return
  const data: any = await api.get('/analysis/multi/param_hist', {
    params: {
      lot_ids: lotIdsStr,
      param_name: currentParamName.value,
      filter_type: options.value.filter_type,
      sigma: options.value.sigma,
      data_range: options.value.data_range,
    }
  })
  histData.value = data
  await nextTick()
  renderHist()
}

function renderHist() {
  if (!histData.value || !histChartRef.value) return
  if (!histChart) histChart = echarts.init(histChartRef.value)

  const { global_edges, lots, param_name, unit, lower_limit: ll, upper_limit: ul } = histData.value
  const edges: number[] = global_edges
  const binCenters = edges.slice(0, -1).map((e: number, i: number) => (e + edges[i + 1]) / 2)
  const xRange = edges[edges.length - 1] - edges[0]
  const binW = edges[1] - edges[0]
  const barWidthPct = Math.max(1, (binW / xRange) * 700)

  let series: any[] = []

  if (histMode.value === 'lot') {
    // 各LOT独立颜色
    series = lots.map((lot: any, idx: number) => ({
      type: 'bar',
      name: lot.filename,
      data: lot.counts.map((cnt: number, i: number) => [binCenters[i], cnt]),
      itemStyle: { color: LOT_COLORS[idx % LOT_COLORS.length], opacity: 0.75 },
      barGap: '-100%',
      barWidth: barWidthPct,
    }))
  } else {
    // Single：所有数据合并
    const combined = new Array(binCenters.length).fill(0)
    lots.forEach((lot: any) => {
      lot.counts.forEach((cnt: number, i: number) => { combined[i] += cnt })
    })
    series = [{
      type: 'bar',
      name: 'All LOTs',
      data: combined.map((cnt: number, i: number) => [binCenters[i], cnt]),
      itemStyle: { color: '#4dabf7', opacity: 0.8 },
      barWidth: barWidthPct,
    }]
  }

  // LL/UL 标线
  const markLineData: any[] = []
  if (ll != null) markLineData.push({
    xAxis: ll,
    label: { formatter: `LL:${ll}`, position: 'insideStartTop', fontSize: 10, color: 'red' },
    lineStyle: { color: 'red', type: 'dashed', width: 1.5 },
  })
  if (ul != null) markLineData.push({
    xAxis: ul,
    label: { formatter: `UL:${ul}`, position: 'insideStartTop', fontSize: 10, color: 'red' },
    lineStyle: { color: 'red', type: 'dashed', width: 1.5 },
  })
  if (series.length > 0 && markLineData.length > 0) {
    series[0].markLine = { silent: true, symbol: 'none', animation: false, data: markLineData }
  }

  histChart.setOption({
    title: {
      text: param_name,
      left: 'center',
      textStyle: { fontSize: 13 },
    },
    tooltip: { trigger: 'axis' },
    legend: {
      bottom: 0,
      data: histMode.value === 'lot' ? lots.map((l: any) => l.filename) : ['All LOTs'],
    },
    xAxis: {
      type: 'value',
      name: unit,
      min: edges[0],
      max: edges[edges.length - 1],
      axisLabel: { rotate: 30, fontSize: 10, formatter: (v: number) => v.toFixed(3) },
    },
    yAxis: { type: 'value', name: 'Parts' },
    series,
  }, true)
}

function prevParam() {
  const idx = paramList.value.findIndex(p => p.item_name === currentParamName.value)
  if (idx > 0) { currentParamName.value = paramList.value[idx - 1].item_name; loadData() }
}

function nextParam() {
  const idx = paramList.value.findIndex(p => p.item_name === currentParamName.value)
  if (idx < paramList.value.length - 1) { currentParamName.value = paramList.value[idx + 1].item_name; loadData() }
}

function fmtNum(v: number | null | undefined) {
  if (v === null || v === undefined) return '-'
  return v.toFixed(4)
}

function cpkStyle(v: number | null | undefined) {
  if (v === null || v === undefined) return {}
  if (v < 1.0) return { color: 'red', fontWeight: 'bold' }
  if (v < 1.33) return { color: 'orange' }
  return {}
}

onMounted(async () => {
  await fetchParamList()
  if (!currentParamName.value && paramList.value.length) {
    currentParamName.value = paramList.value[0].item_name
  }
  await loadData()
})
</script>

<style scoped>
.multi-param-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  background: #f0f2f5;
  overflow: hidden;
}

.options-bar {
  background: white;
  padding: 8px 16px;
  border-radius: 6px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
  flex-shrink: 0;
  font-size: 12px;
}

.nav-group { display: flex; align-items: center; gap: 6px; }
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

.opt-item { display: flex; align-items: center; gap: 6px; }
.opt-item label { color: #666; }
.opt-item select, .opt-item input[type="number"] {
  padding: 3px 6px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  font-size: 12px;
}
.opt-item button {
  padding: 3px 10px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  background: white;
  cursor: pointer;
  font-size: 12px;
}

.stats-wrap {
  background: white;
  border-radius: 6px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  overflow-x: auto;
  flex-shrink: 0;
}

.stats-table { border-collapse: collapse; font-size: 12px; width: 100%; }
.stats-table th, .stats-table td {
  border: 1px solid #f0f0f0;
  padding: 5px 10px;
  text-align: center;
  white-space: nowrap;
}
.stats-table th { background: #fafafa; color: #666; }

.lot-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 2px;
  margin-right: 5px;
  vertical-align: middle;
}

.chart-wrap {
  flex: 1;
  background: white;
  border-radius: 6px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  padding: 8px;
  min-height: 0;
}
</style>
