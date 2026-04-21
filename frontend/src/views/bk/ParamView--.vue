<template>
  <div class="param-view">
    <!-- 顶部汇总信息栏 -->
    <div class="lot-header-info" v-if="lotInfo">
      <div class="info-item"><strong>文件名:</strong> {{ lotInfo.filename }}</div>
      <div class="info-item"><strong>产品名:</strong> {{ lotInfo.product_name || '-' }}</div>
      <div class="info-item"><strong>批号:</strong> {{ lotInfo.lot_id || '-' }}</div>
      <div class="info-item"><strong>程序:</strong> {{ lotInfo.program || '-' }}</div>
      <div class="info-item"><strong>良率:</strong> {{ lotInfo.yield_rate ? (lotInfo.yield_rate * 100).toFixed(2) + '%' : '-' }}</div>
      <div class="info-item"><strong>测试机:</strong> {{ lotInfo.test_machine || '-' }}</div>
    </div>

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
            <button class="nav-btn" @click="prevParam">◀ PREV</button>
            <select class="spc-select" v-model="currentParamName" @change="addTab">
              <option v-for="item in paramList" :key="item.item_name" :value="item.item_name">
                {{ item.item_number }}:{{ item.item_name }}
              </option>
            </select>
            <button class="nav-btn" @click="nextParam">NEXT ▶</button>
          </div>

          <div class="option-item">
            <label class="opt-label">Filter</label>
            <select class="spc-select" v-model="draftOptions.filter_type">
              <option value="all">All Data</option>
              <option value="robust">Robust Data</option>
              <option value="filter_by_limit">Filter By Limit</option>
              <option value="filter_by_sigma">Filter by Sigma</option>
            </select>
          </div>

          <div class="option-item" v-if="draftOptions.filter_type === 'filter_by_sigma'">
            <label class="opt-label">Sigma</label>
            <input class="spc-input" v-model.number="draftOptions.sigma" type="number" step="0.5" min="1" max="6" style="width:60px" />
          </div>

          <div class="option-item">
            <label class="opt-label">DataRange</label>
            <label class="radio-label"><input type="radio" v-model="draftOptions.data_range" value="final" /> Final</label>
            <label class="radio-label"><input type="radio" v-model="draftOptions.data_range" value="original" /> Original</label>
            <label class="radio-label"><input type="radio" v-model="draftOptions.data_range" value="all" /> All</label>
          </div>

          <div class="option-item">
            <label class="opt-label">Chart</label>
            <label class="radio-label"><input type="checkbox" v-model="draftOptions.show_histogram" /> Histogram</label>
            <label class="radio-label"><input type="checkbox" v-model="draftOptions.show_scatter" /> Scatter</label>
            <label class="radio-label"><input type="checkbox" v-model="draftOptions.show_map" /> Map Chart</label>
          </div>
        </div>

        <button class="submit-btn" @click="handleSubmit">提交</button>
      </div>

      <!-- 内容区 -->
      <div class="content-row">
        <div class="charts-area">

          <!-- 统计汇总表：亮黄色背景，仿SPC工具风格 -->
          <div class="stats-table" v-if="currentTab.data">
            <table>
              <thead>
                <tr>
                  <th>SITE</th>
                  <th>Passes</th>
                  <th>Failures</th>
                  <th>Exec Qty</th>
                  <th>Yield</th>
                  <th>Limit_L</th>
                  <th>Limit_H</th>
                  <th>Min</th>
                  <th>Max</th>
                  <th>Mean</th>
                  <th>Stdev</th>
                  <th>CPK</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="s in currentTab.data.sites" :key="s.site">
                  <td class="site-cell">{{ s.site === 0 ? 'ALL' : `Site${s.site}` }}</td>
                  <td>{{ s.stats.exec_qty - s.stats.fail_count }}</td>
                  <td>{{ s.stats.fail_count }}</td>
                  <td>{{ s.stats.exec_qty }}</td>
                  <td>{{ s.stats.yield_rate ? (s.stats.yield_rate * 100).toFixed(2) + '%' : '-' }}</td>
                  <td class="limit-cell">{{ currentTab.data.lower_limit ?? '-' }}</td>
                  <td class="limit-cell">{{ currentTab.data.upper_limit ?? '-' }}</td>
                  <td :style="valColor(s.stats.min_val, currentTab.data.lower_limit, currentTab.data.upper_limit)">{{ s.stats.min_val?.toFixed(4) ?? '-' }}</td>
                  <td :style="valColor(s.stats.max_val, currentTab.data.lower_limit, currentTab.data.upper_limit)">{{ s.stats.max_val?.toFixed(4) ?? '-' }}</td>
                  <td>{{ s.stats.mean?.toFixed(4) ?? '-' }}</td>
                  <td>{{ s.stats.stdev?.toFixed(4) ?? '-' }}</td>
                  <td :style="cpkColor(s.stats.cpk)">{{ s.stats.cpk?.toFixed(4) ?? '-' }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- 直方图 -->
          <div v-if="currentTab.options.show_histogram && currentTab.data" class="chart-container hist-container">
            <div :ref="el => setChartRef(currentTab!.id, 'hist', el)" style="width:800px;height:420px"></div>
          </div>

          <!-- Scatter图 -->
          <div v-if="currentTab.options.show_scatter && currentTab.data" class="chart-container">
            <div :ref="el => setChartRef(currentTab!.id, 'scatter', el)" style="width:800px;height:260px"></div>
          </div>

          <!-- Wafer Map -->
          <div v-if="currentTab.options.show_map && currentTab.data" class="chart-container wafer-container">
            <div class="wafer-title">Wafer Map</div>
            <canvas
              :ref="el => setChartRef(currentTab!.id, 'wafer', el)"
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
const lotInfo = ref<any>(null)

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

async function fetchLotInfo() {
  lotInfo.value = await api.get(`/analysis/lot/${lotId.value}/info`)
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
    id: tabId, title, param_name: paramName, options: { ...draftOptions.value }, data: null
  }
  if (tabs.value.length >= 10) tabs.value.shift()
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

function handleSubmit() { addTab() }

function closeTab(tabId: string) {
  const idx = tabs.value.findIndex(t => t.id === tabId)
  tabs.value.splice(idx, 1)
  if (activeTab.value === tabId) activeTab.value = tabs.value[tabs.value.length - 1]?.id ?? ''
  Object.keys(chartInstances).filter(k => k.startsWith(tabId)).forEach(k => {
    if (chartInstances[k]?.dispose) chartInstances[k].dispose()
    delete chartInstances[k]
  })
}

function prevParam() {
  const idx = paramList.value.findIndex(p => p.item_name === currentParamName.value)
  if (idx > 0) { currentParamName.value = paramList.value[idx - 1].item_name; addTab() }
}

function nextParam() {
  const idx = paramList.value.findIndex(p => p.item_name === currentParamName.value)
  if (idx < paramList.value.length - 1) { currentParamName.value = paramList.value[idx + 1].item_name; addTab() }
}

// =====================================================
// 颜色工具：hex 变暗/变亮（替代 echarts.color.lerp，后者只接受 [r,g,b] 数组）
// =====================================================
function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace('#', '')
  return [parseInt(h.substring(0,2),16), parseInt(h.substring(2,4),16), parseInt(h.substring(4,6),16)]
}
function rgbToHex(r: number, g: number, b: number): string {
  return '#' + [r,g,b].map(v => Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2,'0')).join('')
}
function hexDarken(hex: string, ratio: number): string {
  const [r,g,b] = hexToRgb(hex); return rgbToHex(r*(1-ratio), g*(1-ratio), b*(1-ratio))
}
function hexLighten(hex: string, ratio: number): string {
  const [r,g,b] = hexToRgb(hex); return rgbToHex(r+(255-r)*ratio, g+(255-g)*ratio, b+(255-b)*ratio)
}

// =====================================================
// 颜色系统 - 仿参考图风格
// Site1: 红色系, Site2: 蓝色系，与参考图完全一致
// =====================================================
const SITE_COLORS = [
  '#cc3333',  // Site1: 深红
  '#3366cc',  // Site2: 深蓝
  '#229922',  // Site3: 深绿
  '#cc8800',  // Site4: 深橙
  '#884499',  // Site5: 深紫
  '#008888',  // Site6: 深青
  '#aa4422',  // Site7: 棕红
  '#555599',  // Site8: 深蓝紫
]

function renderCharts(tabId: string) {
  renderHistogram(tabId)
  renderScatter(tabId)
}

// =====================================================
// 3D Bar 渲染函数（仿参考图 isometric 伪3D 风格）
// =====================================================
function make3DBar(params: any, api: any, color: string, siteIndex: number, totalSites: number) {
  const valX = api.value(0)
  const valY = api.value(1)
  const valWidth = api.value(2) || 0

  if (valY === 0 || isNaN(valX) || isNaN(valY)) return

  const location = api.coord([valX, valY])
  const coordBase = api.coord([valX, 0])

  const xLeft = api.coord([valX - valWidth / 2, valY])[0]
  const xRight = api.coord([valX + valWidth / 2, valY])[0]
  let width = Math.abs(xRight - xLeft) * 0.88
  if (width < 1) width = 1

  // 纵深偏移：模拟透视。后面的 site 偏移量大
  const depthIdx = totalSites - siteIndex - 1
  const offsetX = depthIdx * 7
  const offsetY = -depthIdx * 6

  const x = location[0] - width / 2 + offsetX
  const y = location[1] + offsetY
  let height = coordBase[1] - location[1]

  if (height > 0 && height < 2) height = 2
  if (height < 0) height = 0

  // 3D 顶面/侧面的倾斜量（与参考图视角匹配）
  const tilt = 6

  // 颜色计算：手动 hex 变暗/变亮，避免 echarts.color.lerp 不接受 hex 字符串的问题
  const faceColor = color
  const sideColor = hexDarken(color, 0.35)
  const topColor = hexLighten(color, 0.25)

  return {
    type: 'group',
    children: [
      {
        // 正面
        type: 'rect',
        shape: { x, y, width, height },
        style: api.style({ fill: faceColor, stroke: '#333333', lineWidth: 0.5, opacity: 0.92 })
      },
      {
        // 右侧面
        type: 'path',
        shape: {
          d: `M ${x + width} ${y} L ${x + width + tilt} ${y - tilt} L ${x + width + tilt} ${y + height - tilt} L ${x + width} ${y + height} Z`
        },
        style: api.style({ fill: sideColor, stroke: '#333333', lineWidth: 0.5, opacity: 0.92 })
      },
      {
        // 顶面
        type: 'path',
        shape: {
          d: `M ${x} ${y} L ${x + tilt} ${y - tilt} L ${x + width + tilt} ${y - tilt} L ${x + width} ${y} Z`
        },
        style: api.style({ fill: topColor, stroke: '#333333', lineWidth: 0.5, opacity: 0.92 })
      }
    ]
  }
}

// =====================================================
// Histogram 渲染 - 完整仿参考图风格
// =====================================================
function renderHistogram(tabId: string) {
  const tab = tabs.value.find(t => t.id === tabId)
  if (!tab?.data) return
  const chart = chartInstances[`${tabId}_hist`]
  if (!chart) return

  const { sites, param_name, unit, lower_limit, upper_limit } = tab.data
  const allSites = sites.filter((s: any) => s.site > 0)
  if (allSites.length === 0) return

  const baseHist = allSites[0]?.histogram || { edges: [], kde_x: [] }
  const edges = baseHist.edges || []
  const kde_x = baseHist.kde_x || []
  const binWidth = edges.length > 1 ? (edges[1] - edges[0]) : 0

  // X 轴范围
  const allVals = allSites.flatMap((s: any) => s.stats.min_val !== null ? [s.stats.min_val, s.stats.max_val] : [])
  const validVals = allVals.filter((v: any) => v !== null && !isNaN(v))
  let dataMin = validVals.length > 0 ? Math.min(...validVals) : 0
  let dataMax = validVals.length > 0 ? Math.max(...validVals) : 100

  if (lower_limit !== null) dataMin = Math.min(dataMin, lower_limit)
  if (upper_limit !== null) dataMax = Math.max(dataMax, upper_limit)

  let xMin: number, xMax: number
  if (lower_limit !== null && upper_limit !== null && dataMin >= lower_limit && dataMax <= upper_limit) {
    const span = upper_limit - lower_limit || 1
    xMin = lower_limit - span / 3
    xMax = upper_limit + span / 3
  } else {
    const span = (dataMax - dataMin) || 1
    xMin = dataMin - span * 0.1
    xMax = dataMax + span * 0.1
  }

  // Y2 轴最大值
  const maxCount = Math.max(...allSites.flatMap((s: any) => s.histogram?.counts || []))
  const totalExecQty = Math.max(...allSites.map((s: any) => s.stats?.exec_qty || 1))
  const maxPercent = (maxCount / totalExecQty) * 100

  // 统计信息字符串（仿参考图黄色框内文字）
  const firstSiteAll = sites.find((s: any) => s.site === 0) || allSites[0]
  const st = firstSiteAll?.stats
  const statLine1 = st
    ? `Min=${st.min_val?.toFixed(4) ?? '-'}; Max=${st.max_val?.toFixed(4) ?? '-'}; Mean=${st.mean?.toFixed(5) ?? '-'}`
    : ''
  const statLine2 = st
    ? `Stdev=${st.stdev?.toFixed(8) ?? '-'}; CPK=${st.cpk?.toFixed(5) ?? '-'}; CP=${st.cp?.toFixed(5) ?? '-'}`
    : ''

  const series: any[] = []

  // 柱状图系列（伪3D）
  allSites.forEach((s: any, idx: number) => {
    const counts = s.histogram?.counts || []
    const color = SITE_COLORS[idx % SITE_COLORS.length]!

    series.push({
      type: 'custom',
      name: `SITE${s.site}`,
      renderItem: (params: any, api: any) => make3DBar(params, api, color, idx, allSites.length),
      data: counts.map((count: number, i: number) => {
        const center = (edges[i] + edges[i + 1]) / 2
        return [center, count, binWidth]
      }),
      encode: { x: 0, y: 1 },
      yAxisIndex: 0,
      z: 10 - idx,
      legendHoverLink: true,
    })
  })

  // KDE 曲线（与柱子同色，覆盖在顶部）
  allSites.forEach((s: any, idx: number) => {
    const kde_y = s.histogram?.kde_y || []
    if (kde_x.length > 0 && kde_y.length > 0) {
      series.push({
        type: 'line',
        name: `SITE${s.site}_kde`,
        data: kde_x.map((x: number, i: number) => [x, kde_y[i]]),
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 2, color: SITE_COLORS[idx % SITE_COLORS.length] },
        yAxisIndex: 0,
        z: 20,
        showInLegend: false,
        legendHoverLink: false,
        silent: true,
      })
    }
  })

  // Limit 竖虚线 + 标注值（仿参考图：灰色虚线，顶部有数值标注）
  const markLines: any[] = []
  if (lower_limit !== null) markLines.push({
    xAxis: lower_limit,
    label: {
      formatter: `${lower_limit}`,
      position: 'insideStartTop',
      color: '#333',
      fontSize: 10,
      fontWeight: 'bold',
      backgroundColor: 'transparent',
    },
    lineStyle: { color: '#666666', type: 'dashed', width: 1.5 }
  })
  if (upper_limit !== null) markLines.push({
    xAxis: upper_limit,
    label: {
      formatter: `${upper_limit}`,
      position: 'insideStartTop',
      color: '#333',
      fontSize: 10,
      fontWeight: 'bold',
      backgroundColor: 'transparent',
    },
    lineStyle: { color: '#666666', type: 'dashed', width: 1.5 }
  })

  series.push({
    type: 'line',
    data: [],
    name: '_limits',
    showInLegend: false,
    markLine: {
      silent: true,
      symbol: 'none',
      data: markLines,
      z: 5,
      animation: false,
    }
  })

  chart.setOption({
    backgroundColor: '#ffffff',

    // 标题：参数名，粗黑字体，居中
    title: {
      text: `${param_name}`,
      left: 'center',
      top: 6,
      textStyle: {
        fontSize: 16,
        fontWeight: 'bold',
        color: '#111111',
        fontFamily: 'Arial, sans-serif',
      }
    },

    // 统计信息标注（仿黄色框，使用 graphic 元素叠加）
    graphic: statLine1 ? [
      {
        type: 'rect',
        left: 'center',
        top: 36,
        z: 100,
        shape: { width: 500, height: 34 },
        style: { fill: '#ffffc0', stroke: '#ccaa00', lineWidth: 1 }
      },
      {
        type: 'text',
        left: 'center',
        top: 40,
        z: 101,
        style: {
          text: statLine1,
          font: '11px Arial, monospace',
          fill: '#000000',
          textAlign: 'center',
        }
      },
      {
        type: 'text',
        left: 'center',
        top: 54,
        z: 101,
        style: {
          text: statLine2,
          font: '11px Arial, monospace',
          fill: '#000000',
          textAlign: 'center',
        }
      }
    ] : [],

    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: 'rgba(255,255,240,0.95)',
      borderColor: '#999',
      borderWidth: 1,
      textStyle: { color: '#000', fontSize: 11, fontFamily: 'monospace' }
    },

    // 图例：底部，方块色标 + SITE 标签，仿参考图样式
    legend: [
      {
        data: allSites.map((s: any) => ({ name: `SITE${s.site}`, icon: 'rect' })),
        bottom: 8,
        left: 'center',
        orient: 'horizontal',
        itemWidth: 18,
        itemHeight: 10,
        itemGap: 20,
        textStyle: { fontSize: 11, color: '#000', fontFamily: 'Arial' },
        formatter: (name: string) => name,
      }
    ],

    // grid：有背景色，带边框线，仿参考图立体箱效果
    grid: {
      top: 85,
      bottom: 55,
      left: 65,
      right: 65,
      show: true,
      backgroundColor: '#f4f4f4',
      borderColor: '#aaaaaa',
      borderWidth: 1,
      shadowColor: 'rgba(0,0,0,0.08)',
      shadowBlur: 2,
    },

    xAxis: {
      type: 'value',
      name: unit || 'V',
      nameLocation: 'middle',
      nameGap: 28,
      nameTextStyle: { fontSize: 12, fontWeight: 'bold', color: '#222' },
      min: xMin,
      max: xMax,
      scale: true,
      splitLine: {
        show: true,
        lineStyle: { type: 'dashed', color: '#cccccc', width: 1 }
      },
      axisLine: { show: true, lineStyle: { color: '#333333', width: 1.5 } },
      axisTick: { show: true, lineStyle: { color: '#333333' } },
      axisLabel: {
        rotate: -45,
        fontSize: 9,
        color: '#111',
        fontFamily: 'monospace',
        formatter: (val: number) => val.toFixed(4),
        margin: 10,
      }
    },

    yAxis: [
      {
        type: 'value',
        name: 'Parts',
        nameLocation: 'middle',
        nameGap: 45,
        nameRotate: 90,
        nameTextStyle: { fontSize: 11, fontWeight: 'bold', color: '#222' },
        scale: true,
        min: 0,
        splitLine: {
          show: true,
          lineStyle: { type: 'dashed', color: '#cccccc', width: 1 }
        },
        axisLine: { show: true, lineStyle: { color: '#333333', width: 1.5 } },
        axisTick: { show: true, lineStyle: { color: '#333333' } },
        axisLabel: { color: '#111', fontSize: 10 }
      },
      {
        type: 'value',
        name: 'Percent (%)',
        nameLocation: 'middle',
        nameGap: 45,
        nameRotate: -90,
        nameTextStyle: { fontSize: 11, fontWeight: 'bold', color: '#222' },
        min: 0,
        max: Math.ceil(maxPercent * 1.2) || 10,
        splitLine: { show: false },
        axisLine: { show: true, lineStyle: { color: '#333333', width: 1.5 } },
        axisTick: { show: true, lineStyle: { color: '#333333' } },
        axisLabel: {
          color: '#111',
          fontSize: 10,
          formatter: (val: number) => val.toFixed(0)
        }
      }
    ],

    series
  }, true)
}

// =====================================================
// Scatter 图渲染 - 仿工业风格
// =====================================================
function renderScatter(tabId: string) {
  const tab = tabs.value.find(t => t.id === tabId)
  if (!tab?.data) return
  const chart = chartInstances[`${tabId}_scatter`]
  if (!chart) return
  const { sites, unit, lower_limit, upper_limit } = tab.data
  const allSites = sites.filter((s: any) => s.site > 0)

  const series: any[] = allSites.map((s: any, idx: number) => ({
    type: 'scatter',
    name: `SITE${s.site}`,
    data: (s.scatter || []).map((p: any) => [p.idx, p.val]),
    symbolSize: 3,
    itemStyle: {
      color: SITE_COLORS[idx % SITE_COLORS.length],
      opacity: 0.65
    }
  }))

  series.push({
    type: 'line',
    data: [],
    name: '_limits',
    showInLegend: false,
    markLine: {
      silent: true,
      symbol: 'none',
      data: [
        ...(lower_limit !== null ? [{
          yAxis: lower_limit,
          label: { formatter: `LL:${lower_limit}`, color: '#333', fontSize: 10 },
          lineStyle: { color: '#cc0000', type: 'dashed', width: 1.5 }
        }] : []),
        ...(upper_limit !== null ? [{
          yAxis: upper_limit,
          label: { formatter: `UL:${upper_limit}`, color: '#333', fontSize: 10 },
          lineStyle: { color: '#cc0000', type: 'dashed', width: 1.5 }
        }] : []),
      ]
    }
  })

  const allVals = allSites.flatMap((s: any) => (s.scatter || []).map((p: any) => p.val))
  const validVals = allVals.filter((v: any) => v !== null && v !== undefined && !isNaN(v))
  let dataMin = validVals.length > 0 ? Math.min(...validVals) : 0
  let dataMax = validVals.length > 0 ? Math.max(...validVals) : 100

  if (lower_limit !== null) dataMin = Math.min(dataMin, lower_limit)
  if (upper_limit !== null) dataMax = Math.max(dataMax, upper_limit)

  const padding = (dataMax - dataMin) * 0.1 || 0.1
  const yMin = dataMin - padding
  const yMax = dataMax + padding

  chart.setOption({
    backgroundColor: '#ffffff',
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(255,255,240,0.95)',
      borderColor: '#999',
      textStyle: { fontSize: 11, fontFamily: 'monospace', color: '#000' }
    },
    legend: {
      bottom: 4,
      left: 'center',
      itemWidth: 12,
      itemHeight: 8,
      textStyle: { fontSize: 10, color: '#000' }
    },
    grid: {
      top: 30, bottom: 40, left: 65, right: 30,
      show: true,
      backgroundColor: '#f4f4f4',
      borderColor: '#aaaaaa',
      borderWidth: 1,
    },
    xAxis: {
      type: 'value',
      name: 'Index',
      nameLocation: 'middle',
      nameGap: 22,
      nameTextStyle: { fontSize: 11, fontWeight: 'bold', color: '#222' },
      splitLine: { show: true, lineStyle: { type: 'dashed', color: '#cccccc' } },
      axisLine: { show: true, lineStyle: { color: '#333', width: 1.5 } },
      axisLabel: { color: '#111', fontSize: 10 }
    },
    yAxis: {
      type: 'value',
      name: unit,
      nameLocation: 'middle',
      nameGap: 45,
      nameRotate: 90,
      nameTextStyle: { fontSize: 11, fontWeight: 'bold', color: '#222' },
      min: parseFloat(yMin.toFixed(4)),
      max: parseFloat(yMax.toFixed(4)),
      splitLine: { show: true, lineStyle: { type: 'dashed', color: '#cccccc' } },
      axisLine: { show: true, lineStyle: { color: '#333', width: 1.5 } },
      axisLabel: { color: '#111', fontSize: 9, fontFamily: 'monospace' }
    },
    series
  })
}

// =====================================================
// Wafer Map 渲染 - 热力图色阶，蓝→绿→红
// =====================================================
function renderWaferMap(tabId: string, canvas: HTMLCanvasElement) {
  const tab = tabs.value.find(t => t.id === tabId)
  if (!tab?.data) return
  const allData: any[] = []
  tab.data.sites.forEach((s: any) => { if (s.wafer_map) allData.push(...s.wafer_map) })
  if (allData.length === 0) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  const vals = allData.map(d => d.val)
  const minVal = Math.min(...vals)
  const maxVal = Math.max(...vals)
  const xs = allData.map(d => d.x)
  const ys = allData.map(d => d.y)
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minY = Math.min(...ys)
  const maxY = Math.max(...ys)
  const W = canvas.width
  const H = canvas.height
  const margin = 30
  const cellW = (W - margin * 2) / (maxX - minX + 1)
  const cellH = (H - margin * 2) / (maxY - minY + 1)
  const cellSize = Math.min(cellW, cellH) - 1

  ctx.clearRect(0, 0, W, H)

  // 背景
  ctx.fillStyle = '#f4f4f4'
  ctx.fillRect(0, 0, W, H)
  ctx.strokeStyle = '#aaaaaa'
  ctx.lineWidth = 1
  ctx.strokeRect(margin - 2, margin - 2, W - margin * 2 + 4, H - margin * 2 + 4)

  function valToColor(val: number): string {
    const ratio = maxVal === minVal ? 0.5 : (val - minVal) / (maxVal - minVal)
    let r, g, b
    if (ratio < 0.5) {
      r = 0
      g = Math.round(ratio * 2 * 255)
      b = Math.round((1 - ratio * 2) * 255)
    } else {
      r = Math.round((ratio - 0.5) * 2 * 255)
      g = Math.round((1 - (ratio - 0.5) * 2) * 255)
      b = 0
    }
    return `rgb(${r},${g},${b})`
  }

  allData.forEach(d => {
    const px = margin + (d.x - minX) * cellW + cellW / 2 - cellSize / 2
    const py = margin + (d.y - minY) * cellH + cellH / 2 - cellSize / 2
    ctx.fillStyle = valToColor(d.val)
    ctx.fillRect(px, py, cellSize, cellSize)
    ctx.strokeStyle = 'rgba(0,0,0,0.08)'
    ctx.lineWidth = 0.3
    ctx.strokeRect(px, py, cellSize, cellSize)
  })

  // 绘制色阶条（右侧）
  const legendX = W - margin + 5
  const legendH = H - margin * 2
  const gradient = ctx.createLinearGradient(0, margin, 0, margin + legendH)
  gradient.addColorStop(0, 'rgb(255,0,0)')
  gradient.addColorStop(0.5, 'rgb(0,255,0)')
  gradient.addColorStop(1, 'rgb(0,0,255)')
  ctx.fillStyle = gradient
  ctx.fillRect(legendX, margin, 10, legendH)
  ctx.strokeStyle = '#666'
  ctx.lineWidth = 0.5
  ctx.strokeRect(legendX, margin, 10, legendH)

  // 色阶标注
  ctx.fillStyle = '#111'
  ctx.font = '9px monospace'
  ctx.textAlign = 'left'
  ctx.fillText(maxVal.toFixed(4), legendX + 13, margin + 8)
  ctx.fillText(((maxVal + minVal) / 2).toFixed(4), legendX + 13, margin + legendH / 2 + 4)
  ctx.fillText(minVal.toFixed(4), legendX + 13, margin + legendH)
}

// =====================================================
// 辅助：值/CPK 颜色
// =====================================================
function valColor(val: number | null, ll: number | null, ul: number | null) {
  if (val === null || val === undefined) return {}
  if ((ll !== null && val < ll) || (ul !== null && val > ul)) return { color: '#cc0000', fontWeight: 'bold' }
  return {}
}

function cpkColor(val: number | null) {
  if (val === null || val === undefined) return {}
  if (val < 1.0) return { color: '#cc0000', fontWeight: 'bold' }
  if (val < 1.33) return { color: '#cc6600' }
  return {}
}

onMounted(async () => {
  await fetchLotInfo()
  await fetchParamList()
  await fetchBinSummary()
  addTab()
})
</script>

<style scoped>
/* =====================================================
   整体布局
   ===================================================== */
.param-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: #ebebeb;
  padding: 6px;
  font-family: Arial, Helvetica, sans-serif;
}

/* =====================================================
   顶部批次信息栏 - 浅灰背景，小字紧凑
   ===================================================== */
.lot-header-info {
  display: flex;
  gap: 16px;
  background: #f0f0f0;
  padding: 6px 12px;
  border: 1px solid #cccccc;
  border-radius: 2px;
  font-size: 12px;
  flex-wrap: wrap;
  color: #222;
}

.info-item strong {
  color: #555;
  margin-right: 3px;
}

/* =====================================================
   Tab 栏 - 工业感，扁平+边框
   ===================================================== */
.tab-bar {
  display: flex;
  gap: 2px;
  flex-shrink: 0;
  background: #d4d4d4;
  padding: 4px 8px 0;
  border: 1px solid #bbbbbb;
  border-bottom: none;
  overflow-x: auto;
}

.tab {
  padding: 4px 14px;
  border: 1px solid #aaaaaa;
  border-bottom: none;
  cursor: pointer;
  font-size: 11px;
  white-space: nowrap;
  background: #e8e8e8;
  display: flex;
  align-items: center;
  gap: 6px;
  color: #333;
  user-select: none;
}

.tab.active {
  background: #ffffff;
  border-color: #3366cc;
  color: #1144aa;
  font-weight: bold;
}

.tab-close {
  font-size: 13px;
  color: #888;
  line-height: 1;
  cursor: pointer;
}

.tab-close:hover {
  color: #cc0000;
}

/* =====================================================
   Tab 内容容器
   ===================================================== */
.tab-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
  overflow: hidden;
  background: #ffffff;
  border: 1px solid #bbbbbb;
  border-top: 2px solid #3366cc;
  padding: 10px;
}

/* =====================================================
   Options 工具栏
   ===================================================== */
.options-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
  flex-wrap: wrap;
  border-bottom: 1px solid #cccccc;
  padding-bottom: 8px;
  background: #fafafa;
}

.options-left {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  flex: 1;
}

.nav-group {
  display: flex;
  align-items: center;
  gap: 4px;
}

.nav-btn {
  padding: 3px 10px;
  border: 1px solid #999999;
  border-radius: 2px;
  background: #e8e8e8;
  cursor: pointer;
  font-size: 11px;
  color: #222;
  font-family: Arial, sans-serif;
}

.nav-btn:hover {
  background: #d0d8e8;
  border-color: #3366cc;
}

.spc-select {
  padding: 3px 6px;
  border: 1px solid #999;
  border-radius: 2px;
  font-size: 11px;
  background: #ffffff;
  color: #111;
  max-width: 280px;
}

.spc-input {
  padding: 2px 5px;
  border: 1px solid #999;
  border-radius: 2px;
  font-size: 11px;
  background: #ffffff;
  color: #111;
}

.option-item {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
}

.opt-label {
  color: #444;
  font-weight: bold;
  white-space: nowrap;
}

.radio-label {
  color: #333;
  cursor: pointer;
  white-space: nowrap;
}

.submit-btn {
  background: #3366cc;
  color: white;
  border: 1px solid #224488;
  border-radius: 2px;
  padding: 5px 18px;
  cursor: pointer;
  font-size: 12px;
  font-weight: bold;
  flex-shrink: 0;
  letter-spacing: 0.5px;
}

.submit-btn:hover {
  background: #2255bb;
}

/* =====================================================
   内容行
   ===================================================== */
.content-row {
  flex: 1;
  display: flex;
  gap: 10px;
  overflow-y: auto;
  overflow-x: hidden;
}

.charts-area {
  width: 836px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* =====================================================
   统计汇总表 - 亮黄色背景，仿 SPC 工具
   ===================================================== */
.stats-table {
  background: #ffffc0;   /* 明亮黄色，与参考图完全一致 */
  border: 1.5px solid #aaaaaa;
  padding: 3px;
  border-radius: 0;
  flex-shrink: 0;
}

.stats-table table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
  color: #000;
  font-family: 'Courier New', monospace;
}

.stats-table th,
.stats-table td {
  border: 1px solid #bbbbbb;
  padding: 2px 5px;
  text-align: right;
  white-space: nowrap;
}

.stats-table th {
  background: #e8e8d0;
  color: #000;
  font-weight: bold;
  text-align: center;
  font-family: Arial, sans-serif;
  font-size: 11px;
}

.stats-table td.site-cell {
  font-weight: bold;
  text-align: center;
  background: #f0f0d0;
}

.stats-table td.limit-cell {
  color: #666666;
  font-style: italic;
}

/* =====================================================
   图表容器 - 灰色边框，工业感
   ===================================================== */
.chart-container {
  background: #ffffff;
  border: 1px solid #cccccc;
  padding: 4px;
  flex-shrink: 0;
  display: flex;
  justify-content: center;
  position: relative;
}

.hist-container {
  border-top: 2px solid #aaaaaa;
}

.wafer-container {
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.wafer-title {
  font-size: 12px;
  font-weight: bold;
  color: #222;
  align-self: flex-start;
  padding-left: 4px;
}

/* =====================================================
   Pass Bin 表（右侧）
   ===================================================== */
.bin-table {
  width: 200px;
  flex-shrink: 0;
  border: 1px solid #cccccc;
  padding: 6px;
  background: #fafafa;
  align-self: flex-start;
}

.bin-title {
  font-size: 12px;
  font-weight: bold;
  color: #111;
  margin-bottom: 5px;
  padding-bottom: 4px;
  border-bottom: 1px solid #cccccc;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.bin-table table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
  font-family: 'Courier New', monospace;
}

.bin-table th,
.bin-table td {
  border: 1px solid #dddddd;
  padding: 2px 5px;
  text-align: center;
}

.bin-table th {
  background: #e8e8e8;
  font-weight: bold;
  color: #222;
  font-family: Arial, sans-serif;
}

.bin-table tr:nth-child(even) td {
  background: #f5f5f5;
}
</style>