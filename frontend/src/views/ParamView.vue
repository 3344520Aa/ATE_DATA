<template>
  <div class="param-view">
    <!-- LOT基本信息栏 -->
    <div class="lot-info-bar" v-if="lotInfo">
      <div class="info-grid">
        <div class="info-item"><span class="label">名称</span><span class="value">{{ lotInfo.filename }}</span></div>
        <div class="info-item"><span class="label">程序</span><span class="value">{{ lotInfo.program }}</span></div>
        <div class="info-item"><span class="label">测试机</span><span class="value">{{ lotInfo.test_machine }}</span></div>
        <div class="info-item"><span class="label">工位数</span><span class="value">{{ lotInfo.station_count }}</span></div>
        <div class="info-item"><span class="label">测试数量</span><span class="value">{{ lotInfo.die_count }}</span></div>
        <div class="info-item">
          <span class="label">良率</span>
          <span class="value" :style="yieldColor(lotInfo.yield_rate)">
            {{ lotInfo.yield_rate ? (lotInfo.yield_rate * 100).toFixed(2) + '%' : '-' }}
          </span>
        </div>
        <div class="info-item"><span class="label">测试阶段</span><span class="value">{{ lotInfo.data_type }}</span></div>
        <div class="info-item"><span class="label">测试日期</span><span class="value">{{ formatDate(lotInfo.test_date) }}</span></div>
      </div>
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
            <select :value="currentTab?.options.filter_type" @change="updateFilterType(($event.target as HTMLSelectElement).value)">
              <option value="all">All Data</option>
              <option value="robust">Robust Data</option>
              <option value="filter_by_limit">Filter By Limit</option>
              <option value="filter_by_sigma">Filter by Sigma</option>
              <option value="custom">Custom</option>
            </select>
          </div>

          <div class="option-item" v-if="currentTab?.options.filter_type === 'filter_by_sigma'">
            <label>Sigma</label>
            <input v-model.number="sigmaInputValue" type="number" step="0.5" min="1" max="6" style="width:60px" />
            <button @click="applySigma">Apply</button>
          </div>

          <div class="option-item" v-if="currentTab?.options.filter_type === 'custom'">
            <label>Min</label>
            <input v-model.number="customMinInput" type="number" step="any" style="width:90px" />
            <label>Max</label>
            <input v-model.number="customMaxInput" type="number" step="any" style="width:90px" />
            <button @click="applyCustomRange">Apply</button>
          </div>

          <div class="option-item">
            <label>DataRange</label>
            <label><input type="radio" :checked="currentTab?.options.data_range === 'final'" @change="updateOption('data_range', 'final')" /> Final</label>
            <label><input type="radio" :checked="currentTab?.options.data_range === 'original'" @change="updateOption('data_range', 'original')" /> Original</label>
            <label><input type="radio" :checked="currentTab?.options.data_range === 'all'" @change="updateOption('data_range', 'all')" /> All</label>
          </div>

          <div class="option-item">
            <label>Chart</label>
            <label><input type="checkbox" :checked="currentTab?.options.show_histogram" @change="updateOption('show_histogram', ($event.target as HTMLInputElement).checked)" /> Histogram</label>
            <label><input type="checkbox" :checked="currentTab?.options.show_scatter" @change="updateOption('show_scatter', ($event.target as HTMLInputElement).checked)" /> Scatter</label>
            <label><input type="checkbox" :checked="currentTab?.options.show_map" @change="updateOption('show_map', ($event.target as HTMLInputElement).checked)" /> Map Chart</label>
          </div>
        </div>
      </div>

      <!-- 内容区 -->
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
                  <td>{{ s.site === 0 ? 'ALL' : `Site${s.site}` }}</td>
                  <td>{{ s.stats.exec_qty - s.stats.fail_count }}</td>
                  <td>{{ s.stats.fail_count }}</td>
                  <td>{{ s.stats.exec_qty }}</td>
                  <td>{{ s.stats.yield_rate ? (s.stats.yield_rate * 100).toFixed(2) + '%' : '-' }}</td>
                  <td>{{ currentTab.data.lower_limit ?? '-' }}</td>
                  <td>{{ currentTab.data.upper_limit ?? '-' }}</td>
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
            <div :ref="el => setChartRef(currentTab?.id, 'hist', el)" style="width:600px;height:400px"></div>
          </div>

          <!-- Scatter图 -->
          <div v-if="currentTab.options.show_scatter && currentTab.data" class="chart-container">
            <div :ref="el => setChartRef(currentTab?.id, 'scatter', el)" style="width:800px;height:260px"></div>
          </div>

          <!-- Wafer Map -->
          <div v-if="currentTab.options.show_map && currentTab.data" class="chart-container" style="flex-direction:column;align-items:center">
            <div style="position:relative">
              <canvas
                :ref="el => setChartRef(currentTab?.id, 'wafer', el)"
                width="820"
                height="600"
                style="width:820px;height:600px;display:block"
              ></canvas>
              <!-- Tooltip: pure DOM, no Vue reactivity -->
              <div ref="waferTooltipEl" class="wafer-tooltip" style="display:none"></div>
            </div>
            <!-- Site图例（下方，点击切换显示/隐藏） -->
            <div class="wafer-legend" v-if="currentTab.data">
              <span
                v-for="(s, idx) in currentTab.data.sites.filter((s:any) => s.site > 0)"
                :key="s.site"
                class="wafer-legend-item"
                :class="{ hidden: hiddenSites.has(s.site) }"
                @click="toggleSite(s.site)"
              >
                <span class="wafer-legend-dot" :style="{ background: SITE_COLORS[idx % SITE_COLORS.length] }"></span>
                Site{{ s.site }}
              </span>
            </div>
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

// Wafer tooltip DOM ref (直接操作DOM，不用Vue响应式，避免触发全局重渲染)
const waferTooltipEl = ref<HTMLDivElement | null>(null)

// 隐藏的Site集合（响应式，用于图例点击切换，仅重绘wafer canvas）
const hiddenSites = ref<Set<number>>(new Set())

// Wafer map state per tab (for hit-testing on hover)
const waferMapState: Record<string, {
  dies: { px: number; py: number; size: number; dieX: number; dieY: number; val: number; site: number }[]
  canvasEl: HTMLCanvasElement | null
}> = {}

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
  custom_min: null as number | null,
  custom_max: null as number | null,
  show_histogram: true,
  show_scatter: true,
  show_map: true,
})

const sigmaInputValue = ref(draftOptions.value.sigma)
const customMinInput = ref<number | null>(null)
const customMaxInput = ref<number | null>(null)

watch(currentTab, (newTab) => {
  if (newTab) {
    sigmaInputValue.value = newTab.options.sigma
    customMinInput.value = newTab.options.custom_min
    customMaxInput.value = newTab.options.custom_max
  }
}, { immediate: true })

// 切换tab时重置hiddenSites
watch(activeTab, () => {
  hiddenSites.value = new Set()
})

async function updateOption(key: string, value: any) {
  if (!currentTab.value) return
  currentTab.value.options[key] = value
  await loadTabData(currentTab.value.id)
}

async function updateFilterType(value: string) {
  if (!currentTab.value) return
  currentTab.value.options.filter_type = value
  if (value !== 'filter_by_sigma') {
    sigmaInputValue.value = draftOptions.value.sigma
  }
  if (value === 'custom' && currentTab.value.data) {
    const allSite = currentTab.value.data.sites.find((s: any) => s.site === 0)
    if (allSite?.stats) {
      customMinInput.value = allSite.stats.min_val
      customMaxInput.value = allSite.stats.max_val
      currentTab.value.options.custom_min = allSite.stats.min_val
      currentTab.value.options.custom_max = allSite.stats.max_val
    }
  }
  await loadTabData(currentTab.value.id)
}

function applySigma() {
  if (!currentTab.value) return
  currentTab.value.options.sigma = sigmaInputValue.value
  loadTabData(currentTab.value.id)
}

function applyCustomRange() {
  if (!currentTab.value) return
  currentTab.value.options.custom_min = customMinInput.value
  currentTab.value.options.custom_max = customMaxInput.value
  loadTabData(currentTab.value.id)
}

function toggleSite(siteNum: number) {
  const s = new Set(hiddenSites.value)
  if (s.has(siteNum)) s.delete(siteNum)
  else s.add(siteNum)
  hiddenSites.value = s
  // 只重绘wafer，不触发hist/scatter
  if (currentTab.value) {
    const key = `${currentTab.value.id}_wafer`
    const canvas = chartInstances[key]
    if (canvas) renderWaferMap(currentTab.value.id, canvas)
  }
}

// 图表实例存储
const chartInstances: Record<string, any> = {}

function setChartRef(tabId: string | undefined, type: string, el: any) {
  if (!tabId) return
  const key = `${tabId}_${type}`

  if (el) {
    if (type === 'wafer') {
      if (waferMapState[tabId]?.canvasEl) {
        waferMapState[tabId].canvasEl!.onmousemove = null
        waferMapState[tabId].canvasEl!.onmouseleave = null
      }
      chartInstances[key] = el
      waferMapState[tabId] = { dies: [], canvasEl: el }
      el.onmousemove = (evt: MouseEvent) => onWaferMouseMove(tabId, evt)
      el.onmouseleave = () => {
        // 直接操作DOM，不触发Vue响应式
        if (waferTooltipEl.value) waferTooltipEl.value.style.display = 'none'
      }
      nextTick(() => renderWaferMap(tabId, el))
    } else {
      if (chartInstances[key]?.dispose) {
        chartInstances[key].dispose()
      }
      chartInstances[key] = echarts.init(el)
      nextTick(() => {
        if (type === 'hist') renderHistogram(tabId)
        if (type === 'scatter') renderScatter(tabId)
      })
    }
  } else {
    if (type === 'wafer') {
      if (waferMapState[tabId]?.canvasEl) {
        waferMapState[tabId].canvasEl!.onmousemove = null
        waferMapState[tabId].canvasEl!.onmouseleave = null
      }
      delete waferMapState[tabId]
    } else if (chartInstances[key]?.dispose) {
      chartInstances[key].dispose()
      delete chartInstances[key]
    }
  }
}

function onWaferMouseMove(tabId: string, evt: MouseEvent) {
  const state = waferMapState[tabId]
  const tooltipEl = waferTooltipEl.value
  if (!state?.canvasEl || !tooltipEl) return

  const rect = state.canvasEl.getBoundingClientRect()
  const scaleX = state.canvasEl.width / rect.width
  const scaleY = state.canvasEl.height / rect.height
  const mx = (evt.clientX - rect.left) * scaleX
  const my = (evt.clientY - rect.top) * scaleY

  let found: typeof state.dies[0] | null = null
  for (const d of state.dies) {
    if (mx >= d.px && mx <= d.px + d.size && my >= d.py && my <= d.py + d.size) {
      found = d
      break
    }
  }

  // 直接操作DOM，完全绕开Vue响应式，不触发重渲染
  if (found) {
    tooltipEl.innerHTML = `<div>X: ${found.dieX}, Y: ${found.dieY}</div><div>Val: ${found.val.toFixed(6)}</div><div>Site: ${found.site}</div>`
    tooltipEl.style.display = 'block'
    tooltipEl.style.left = (evt.offsetX + 14) + 'px'
    tooltipEl.style.top = (evt.offsetY + 14) + 'px'
  } else {
    tooltipEl.style.display = 'none'
  }
}

async function fetchParamList() {
  paramList.value = await api.get(`/analysis/lot/${lotId.value}/items`, { params: { site: 0 } })
}

async function fetchBinSummary() {
  const data: any = await api.get(`/analysis/lot/${lotId.value}/bin_summary`)
  binSummary.value = data.bins
}

async function fetchLotInfo() {
  lotInfo.value = await api.get(`/analysis/lot/${lotId.value}/info`)
}

async function fetchParamData(paramName: string, options: any) {
  return await api.get(`/analysis/lot/${lotId.value}/param_data`, {
    params: {
      param_name: paramName,
      filter_type: options.filter_type,
      sigma: options.sigma,
      data_range: options.data_range,
      custom_min: options.filter_type === 'custom' ? options.custom_min : undefined,
      custom_max: options.filter_type === 'custom' ? options.custom_max : undefined,
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

  if (tab.options.filter_type === 'custom' &&
      tab.options.custom_min == null && tab.options.custom_max == null) {
    const allSite = data.sites.find((s: any) => s.site === 0)
    if (allSite?.stats) {
      tab.options.custom_min = allSite.stats.min_val
      tab.options.custom_max = allSite.stats.max_val
      customMinInput.value = allSite.stats.min_val
      customMaxInput.value = allSite.stats.max_val
    }
  }

  await nextTick()
  renderCharts(tabId)
}

function closeTab(tabId: string) {
  const idx = tabs.value.findIndex(t => t.id === tabId)
  tabs.value.splice(idx, 1)
  if (activeTab.value === tabId) {
    activeTab.value = tabs.value[tabs.value.length - 1]?.id ?? ''
  }
  Object.keys(chartInstances).filter(k => k.startsWith(tabId)).forEach(k => {
    if (chartInstances[k]?.dispose) chartInstances[k].dispose()
    delete chartInstances[k]
  })
  if (waferMapState[tabId]) {
    if (waferMapState[tabId].canvasEl) {
      waferMapState[tabId].canvasEl!.onmousemove = null
      waferMapState[tabId].canvasEl!.onmouseleave = null
    }
    delete waferMapState[tabId]
  }
}

function prevParam() {
  const idx = paramList.value.findIndex(p => p.item_name === currentParamName.value)
  if (idx > 0) { currentParamName.value = paramList.value[idx - 1].item_name; addTab() }
}

function nextParam() {
  const idx = paramList.value.findIndex(p => p.item_name === currentParamName.value)
  if (idx < paramList.value.length - 1) { currentParamName.value = paramList.value[idx + 1].item_name; addTab() }
}

// ── 常量 ──────────────────────────────────────────────
const SITE_COLORS = ['#ff6b6b', '#4dabf7', '#69db7c', '#ffd43b', '#e599f7', '#74c0fc', '#a9e34b', '#ffa94d']
const NUM_COLOR_LEVELS = 20

function renderCharts(tabId: string) {
  renderHistogram(tabId)
  renderScatter(tabId)
  const key = `${tabId}_wafer`
  if (chartInstances[key]) renderWaferMap(tabId, chartInstances[key])
}

// 全局数据范围（来自global_edges，用于scatter Y轴和wafer颜色比例尺）
function getGlobalRange(tab: any): { min: number; max: number } {
  const edges: number[] = tab.data.global_edges ?? []
  if (edges.length >= 2) return { min: edges[0], max: edges[edges.length - 1] }
  const allSite = tab.data.sites.find((s: any) => s.site === 0)
  return { min: allSite?.stats?.min_val ?? 0, max: allSite?.stats?.max_val ?? 1 }
}

// ── 直方图 X 轴范围计算 ────────────────────────────────
// 规则（按优先级）：
//   D: 固定值（LL==UL 且 数据无变化）→ 以中心值±50%展示
//   A: 双边Limit且数据在限内     → LL在10%处，UL在90%处
//   B: 双边Limit但数据超限       → LL在20%处，UL在80%处，两侧动态扩展到数据极值
//   E: 单边Limit               → 数据范围+padding，确保该Limit可见
//   C: 无Limit / LL==UL但数据有变化 → 数据min/max+padding
function calcHistXRange(
  dataMin: number, dataMax: number,
  ll: number | null, ul: number | null,
  edgesMin?: number, edgesMax?: number
): { xMin: number; xMax: number; ticks: number[] } {
  const hasLL = ll !== null && ll !== undefined
  const hasUL = ul !== null && ul !== undefined
  const hasBothLimits = hasLL && hasUL

  // Case D: 固定值 — 仅当 LL==UL 且 数据也无变化时
  if (dataMin === dataMax && (!hasBothLimits || ll === ul)) {
    const center = dataMin
    const half = Math.abs(center) * 0.5 || 0.5
    const xMin = center - half
    const xMax = center + half
    const ticks = buildTicks(xMin, xMax, 11)
    return { xMin, xMax, ticks }
  }

  // 当 LL==UL 时，Limit无意义，按数据范围走 Case C
  if (hasBothLimits && ll === ul) {
    const rangeMin = edgesMin ?? dataMin
    const rangeMax = edgesMax ?? dataMax
    const padding = (rangeMax - rangeMin) * 0.05 || Math.abs(rangeMax) * 0.01 || 0.1
    const xMin = rangeMin - padding
    const xMax = rangeMax + padding
    const ticks = buildTicks(xMin, xMax, 11)
    return { xMin, xMax, ticks }
  }

  if (hasBothLimits) {
    // 使用 edges 范围（后端已做 clamp）来判断是否超限
    const effMin = edgesMin ?? dataMin
    const effMax = edgesMax ?? dataMax
    const dataExceedsLimit = effMin < ll! || effMax > ul!

    if (!dataExceedsLimit) {
      // Case A: 数据全在限内，LL在1/10处，UL在9/10处
      const range = (ul! - ll!) / 0.8
      const xMin = ll! - range * 0.1
      const xMax = ul! + range * 0.1
      const ticks = buildTicks(xMin, xMax, 11)
      return { xMin, xMax, ticks }
    } else {
      // Case B: 数据超限
      // X轴中心 = LL/UL中点, LL放在20%位置, UL放在80%位置
      // LL~UL占据中间60%的区间，两侧各20%动态扩展到数据极值
      const limitRange = ul! - ll!
      // LL~UL对应x轴的 [0.2, 0.8]，即60%宽度 = limitRange
      // 总宽度 = limitRange / 0.6
      const totalRange = limitRange / 0.6
      const center = (ll! + ul!) / 2
      let xMin = center - totalRange / 2  // LL在20%处
      let xMax = center + totalRange / 2  // UL在80%处

      // 如果数据超出了默认20%区间，动态扩展到数据极值
      if (effMin < xMin) {
        // 数据最小值比默认下界还小，扩展左侧
        // 保持UL在80%处不变，LL从20%位置向左压缩
        // 新的xMin = effMin，但需要保证LL和UL的相对位置合理
        xMin = effMin - (effMin === ll! ? limitRange * 0.05 : (ll! - effMin) * 0.1)
      }
      if (effMax > xMax) {
        // 数据最大值比默认上界还大，扩展右侧
        xMax = effMax + (effMax === ul! ? limitRange * 0.05 : (effMax - ul!) * 0.1)
      }

      const ticks = buildTicks(xMin, xMax, 11)
      return { xMin, xMax, ticks }
    }
  }

  if (hasLL || hasUL) {
    // Case E: 单边Limit，确保Limit在可见范围内
    const effMin = edgesMin ?? dataMin
    const effMax = edgesMax ?? dataMax
    const rangeMin = hasLL ? Math.min(effMin, ll!) : effMin
    const rangeMax = hasUL ? Math.max(effMax, ul!) : effMax
    const padding = (rangeMax - rangeMin) * 0.05 || Math.abs(rangeMax) * 0.01 || 0.1
    const xMin = rangeMin - padding
    const xMax = rangeMax + padding
    const ticks = buildTicks(xMin, xMax, 11)
    return { xMin, xMax, ticks }
  }

  // Case C: 无Limit，纯数据范围
  const effMin = edgesMin ?? dataMin
  const effMax = edgesMax ?? dataMax
  const padding = (effMax - effMin) * 0.05 || Math.abs(effMax) * 0.01 || 0.1
  const xMin = effMin - padding
  const xMax = effMax + padding
  const ticks = buildTicks(xMin, xMax, 11)
  return { xMin, xMax, ticks }
}

function buildTicks(xMin: number, xMax: number, count: number): number[] {
  const step = (xMax - xMin) / (count - 1)
  return Array.from({ length: count }, (_, i) => xMin + i * step)
}

// ── 直方图渲染 ─────────────────────────────────────────
function renderHistogram(tabId: string) {
  const tab = tabs.value.find(t => t.id === tabId)
  if (!tab?.data) return
  const chart = chartInstances[`${tabId}_hist`]
  if (!chart) return

  const { sites, param_name, unit, lower_limit: ll, upper_limit: ul,
          global_edges, exceeds_limit, ll_bin_index, ul_bin_index } = tab.data
  const allSites = sites.filter((s: any) => s.site > 0)
  const edges: number[] = global_edges ?? allSites[0]?.histogram.edges ?? []
  if (edges.length < 2) return

  const allSiteStats = sites.find((s: any) => s.site === 0)?.stats
  const numBins = edges.length - 1

  // ── 判断渲染模式 ──
  if (exceeds_limit && ll_bin_index != null && ul_bin_index != null) {
    // ═══ 超限模式：使用 category 轴，每个 bin 等宽 ═══
    // 生成 category 标签（bin 中心值）
    const binLabels: string[] = []
    for (let i = 0; i < numBins; i++) {
      binLabels.push(((edges[i] + edges[i + 1]) / 2).toFixed(3))
    }

    const series: any[] = []
    allSites.forEach((s: any, idx: number) => {
      const siteStats = s.stats || allSiteStats
      const sigma6L = siteStats?.mean != null && siteStats?.stdev != null ? siteStats.mean - 6 * siteStats.stdev : -Infinity
      const sigma6U = siteStats?.mean != null && siteStats?.stdev != null ? siteStats.mean + 6 * siteStats.stdev : Infinity

      const normalData = s.histogram.counts.map((cnt: number, i: number) => {
        const center = (edges[i] + edges[i + 1]) / 2
        if ((center < sigma6L || center > sigma6U) && cnt > 0 && cnt < 5) return '-'
        return cnt
      })
      const outlierData = s.histogram.counts.map((cnt: number, i: number) => {
        const center = (edges[i] + edges[i + 1]) / 2
        if ((center < sigma6L || center > sigma6U) && cnt > 0 && cnt < 5) return cnt
        return '-'
      })

      series.push({
        type: 'bar',
        name: `Site${s.site}`,
        data: normalData,
        itemStyle: { color: SITE_COLORS[idx % SITE_COLORS.length], opacity: 0.7 },
        barGap: '-100%',
        barWidth: '90%',
      })

      if (outlierData.some((d: any) => d !== '-')) {
        series.push({
          type: 'bar',
          name: `Site${s.site}`,
          data: outlierData,
          itemStyle: { color: SITE_COLORS[idx % SITE_COLORS.length], opacity: 0.7 },
          barGap: '-100%',
          barWidth: '90%',
          barMinHeight: 5,
        })
      }
    })

    // markLine：LL/UL 用 category index 定位
    const markLineData: any[] = []
    if (ll !== null && ll !== undefined) {
      markLineData.push({
        xAxis: ll_bin_index,
        label: { formatter: `LL:${ll}`, position: 'middle', align: 'left', padding: [0, 0, 0, 8], fontSize: 10, color: 'red', rotate: 0 },
        lineStyle: { color: 'red', type: 'dashed', width: 1.5 },
      })
    }
    if (ul !== null && ul !== undefined) {
      markLineData.push({
        xAxis: ul_bin_index,
        label: { formatter: `UL:${ul}`, position: 'middle', align: 'right', padding: [0, 8, 0, 0], fontSize: 10, color: 'red', rotate: 0 },
        lineStyle: { color: 'red', type: 'dashed', width: 1.5 },
      })
    }

    // sigma 线：找到最近的 category index
    if (tab.options.filter_type === 'filter_by_sigma' && allSiteStats?.mean != null && allSiteStats?.stdev != null) {
      const n = tab.options.sigma ?? 3
      const sigmaL = allSiteStats.mean - n * allSiteStats.stdev
      const sigmaU = allSiteStats.mean + n * allSiteStats.stdev
      const findBinIndex = (val: number) => {
        for (let i = 0; i < numBins; i++) {
          if (val >= edges[i] && val < edges[i + 1]) return i
        }
        return val < edges[0] ? 0 : numBins - 1
      }
      markLineData.push({
        xAxis: findBinIndex(sigmaL),
        label: { formatter: `${n}σL`, position: 'middle', align: 'left', padding: [0, 0, 0, 8], fontSize: 10, color: '#00c853', rotate: 0 },
        lineStyle: { color: '#00c853', type: 'dashed', width: 1.5 },
      })
      markLineData.push({
        xAxis: findBinIndex(sigmaU),
        label: { formatter: `${n}σU`, position: 'middle', align: 'right', padding: [0, 8, 0, 0], fontSize: 10, color: '#00c853', rotate: 0 },
        lineStyle: { color: '#00c853', type: 'dashed', width: 1.5 },
      })
    }

    if (series.length > 0) {
      series[0].markLine = { silent: true, symbol: 'none', animation: false, data: markLineData }
    }

    // X轴标签：只在关键位置显示（LL, UL, 起点, 终点, 中间几个）
    const labelPositions = new Set<number>([0, numBins - 1, ll_bin_index, ul_bin_index])
    // 在 LL~UL 区间内均匀加几个标签
    const midStep = Math.max(1, Math.floor((ul_bin_index - ll_bin_index) / 4))
    for (let i = ll_bin_index; i <= ul_bin_index; i += midStep) labelPositions.add(i)
    // 在 below/above 区间也各加一两个
    if (ll_bin_index > 2) labelPositions.add(Math.floor(ll_bin_index / 2))
    if (numBins - ul_bin_index > 2) labelPositions.add(ul_bin_index + Math.floor((numBins - ul_bin_index) / 2))

    chart.setOption({
      title: {
        text: `${param_name}`,
        subtext: allSiteStats
          ? `Min=${allSiteStats.min_val?.toFixed(4)} Max=${allSiteStats.max_val?.toFixed(4)} Mean=${allSiteStats.mean?.toFixed(4)} Stdev=${allSiteStats.stdev?.toFixed(4)} CPK=${allSiteStats.cpk?.toFixed(4)}`
          : '',
        left: 'center',
        textStyle: { fontSize: 13 },
        subtextStyle: { fontSize: 11, color: '#666' },
      },
      tooltip: {
        trigger: 'axis',
        formatter: (params: any) => {
          if (!params || params.length === 0) return ''
          const idx = params[0].dataIndex
          const lo = edges[idx]?.toFixed(4) ?? ''
          const hi = edges[idx + 1]?.toFixed(4) ?? ''
          let tip = `<div style="font-size:11px">[${lo}, ${hi})</div>`
          params.forEach((p: any) => {
            if (p.value > 0) tip += `<div>${p.marker} ${p.seriesName}: ${p.value}</div>`
          })
          return tip
        },
      },
      legend: { bottom: 0, data: allSites.map((s: any) => `Site${s.site}`) },
      xAxis: {
        type: 'category',
        data: binLabels,
        name: unit,
        axisLabel: {
          rotate: 30,
          fontSize: 10,
          interval: 0,
          formatter: (_: string, index: number) => {
            if (labelPositions.has(index)) {
              // 在 LL 和 UL 位置显示 limit 值
              if (index === ll_bin_index && ll != null) return `LL:${ll}`
              if (index === ul_bin_index && ul != null) return `UL:${ul}`
              return edges[index]?.toFixed(3) ?? ''
            }
            return ''
          },
        },
        axisTick: { alignWithLabel: true },
      },
      yAxis: [
        { type: 'value', name: 'Parts' },
        { type: 'value', name: 'Percent(%)', max: 100 },
      ],
      series,
    }, true)
  } else {
    // ═══ 正常模式：使用 value 轴 ═══
    const dataMin = allSiteStats?.min_val ?? edges[0]
    const dataMax = allSiteStats?.max_val ?? edges[edges.length - 1]
    const edgesMin = edges[0]
    const edgesMax = edges[edges.length - 1]
    const { xMin, xMax, ticks } = calcHistXRange(dataMin, dataMax, ll, ul, edgesMin, edgesMax)

    const binCenters = edges.slice(0, -1).map((e: number, i: number) => (e + edges[i + 1]) / 2)
    const xRange = xMax - xMin
    const binW = edges[1] - edges[0]
    const barWidthPct = Math.max(8, (binW / xRange) * 700)

    const series: any[] = []
    allSites.forEach((s: any, idx: number) => {
      const siteStats = s.stats || allSiteStats
      const sigma6L = siteStats?.mean != null && siteStats?.stdev != null ? siteStats.mean - 6 * siteStats.stdev : -Infinity
      const sigma6U = siteStats?.mean != null && siteStats?.stdev != null ? siteStats.mean + 6 * siteStats.stdev : Infinity

      const normalData: any[] = []
      const outlierData: any[] = []
      
      s.histogram.counts.forEach((cnt: number, i: number) => {
        const center = (edges[i] + edges[i + 1]) / 2
        if ((center < sigma6L || center > sigma6U) && cnt > 0 && cnt < 5) {
          outlierData.push([binCenters[i], cnt])
        } else {
          normalData.push([binCenters[i], cnt])
        }
      })

      series.push({
        type: 'bar',
        name: `Site${s.site}`,
        data: normalData,
        itemStyle: { color: SITE_COLORS[idx % SITE_COLORS.length], opacity: 0.7 },
        barGap: '-100%',
        barWidth: barWidthPct,
      })

      if (outlierData.length > 0) {
        series.push({
          type: 'bar',
          name: `Site${s.site}`,
          data: outlierData,
          itemStyle: { color: SITE_COLORS[idx % SITE_COLORS.length], opacity: 0.7 },
          barGap: '-100%',
          barWidth: barWidthPct,
          barMinHeight: 5,
        })
      }
    })

    const markLineData: any[] = []
    if (ll !== null && ll !== undefined) {
      markLineData.push({
        xAxis: ll,
        label: { formatter: `LL:${ll}`, position: 'middle', align: 'left', padding: [0, 0, 0, 8], fontSize: 10, color: 'red', rotate: 0 },
        lineStyle: { color: 'red', type: 'dashed', width: 1.5 },
      })
    }
    if (ul !== null && ul !== undefined) {
      markLineData.push({
        xAxis: ul,
        label: { formatter: `UL:${ul}`, position: 'middle', align: 'right', padding: [0, 8, 0, 0], fontSize: 10, color: 'red', rotate: 0 },
        lineStyle: { color: 'red', type: 'dashed', width: 1.5 },
      })
    }

    if (tab.options.filter_type === 'filter_by_sigma' && allSiteStats?.mean != null && allSiteStats?.stdev != null) {
      const n = tab.options.sigma ?? 3
      const sigmaL = allSiteStats.mean - n * allSiteStats.stdev
      const sigmaU = allSiteStats.mean + n * allSiteStats.stdev
      markLineData.push({
        xAxis: sigmaL,
        label: { formatter: `${n}σL`, position: 'middle', align: 'left', padding: [0, 0, 0, 8], fontSize: 10, color: '#00c853', rotate: 0 },
        lineStyle: { color: '#00c853', type: 'dashed', width: 1.5 },
      })
      markLineData.push({
        xAxis: sigmaU,
        label: { formatter: `${n}σU`, position: 'middle', align: 'right', padding: [0, 8, 0, 0], fontSize: 10, color: '#00c853', rotate: 0 },
        lineStyle: { color: '#00c853', type: 'dashed', width: 1.5 },
      })
    }

    if (series.length > 0) {
      series[0].markLine = { silent: true, symbol: 'none', animation: false, data: markLineData }
    }

    chart.setOption({
      title: {
        text: `${param_name}`,
        subtext: allSiteStats
          ? `Min=${allSiteStats.min_val?.toFixed(4)} Max=${allSiteStats.max_val?.toFixed(4)} Mean=${allSiteStats.mean?.toFixed(4)} Stdev=${allSiteStats.stdev?.toFixed(4)} CPK=${allSiteStats.cpk?.toFixed(4)}`
          : '',
        left: 'center',
        textStyle: { fontSize: 13 },
        subtextStyle: { fontSize: 11, color: '#666' },
      },
      tooltip: { trigger: 'axis' },
      legend: { bottom: 0, data: allSites.map((s: any) => `Site${s.site}`) },
      xAxis: {
        type: 'value',
        name: unit,
        min: xMin,
        max: xMax,
        interval: (xMax - xMin) / 10,
        axisLabel: {
          rotate: 30,
          fontSize: 10,
          formatter: (v: number) => {
            const isOnTick = ticks.some(t => Math.abs(t - v) < (xMax - xMin) / 100)
            return isOnTick ? v.toFixed(3) : ''
          },
        },
      },
      yAxis: [
        { type: 'value', name: 'Parts' },
        { type: 'value', name: 'Percent(%)', max: 100 },
      ],
      series,
    }, true)
  }
}

// ── Scatter渲染 ────────────────────────────────────────
function renderScatter(tabId: string) {
  const tab = tabs.value.find(t => t.id === tabId)
  if (!tab?.data) return
  const chart = chartInstances[`${tabId}_scatter`]
  if (!chart) return

  const { sites, unit, lower_limit: ll, upper_limit: ul } = tab.data
  const allSites = sites.filter((s: any) => s.site > 0)

  const series: any[] = allSites.map((s: any, idx: number) => ({
    type: 'scatter',
    name: `Site${s.site}`,
    data: s.scatter.map((p: any) => [p.idx, p.val]),
    symbolSize: 3,
    itemStyle: { color: SITE_COLORS[idx % SITE_COLORS.length], opacity: 0.6 },
  }))

  series.push({
    type: 'line',
    data: [],
    markLine: {
      silent: true,
      symbol: 'none',
      data: [
        ...(ll !== null && ll !== undefined ? [{
          yAxis: ll,
          label: { formatter: `LL:${ll}`, position: 'end' },
          lineStyle: { color: 'red', type: 'dashed' },
        }] : []),
        ...(ul !== null && ul !== undefined ? [{
          yAxis: ul,
          label: { formatter: `UL:${ul}`, position: 'end' },
          lineStyle: { color: 'red', type: 'dashed' },
        }] : []),
      ],
    },
  })

  const { min: globalMin, max: globalMax } = getGlobalRange(tab)
  const padding = (globalMax - globalMin) * 0.05 || 0.1
  const yMin = Math.min(globalMin, ll ?? globalMin) - padding
  const yMax = Math.max(globalMax, ul ?? globalMax) + padding

  chart.setOption({
    tooltip: { trigger: 'item' },
    legend: { bottom: 0 },
    xAxis: { type: 'value', name: 'Index' },
    yAxis: {
      type: 'value',
      name: unit,
      min: parseFloat(yMin.toFixed(6)),
      max: parseFloat(yMax.toFixed(6)),
    },
    series,
  })
}

// ── Wafer Map 渲染 ─────────────────────────────────────
function levelToColor(level: number, total: number): string {
  const ratio = total <= 1 ? 0.5 : level / (total - 1)
  let r, g, b
  if (ratio < 0.5) {
    r = 0; g = Math.round(ratio * 2 * 255); b = Math.round((1 - ratio * 2) * 255)
  } else {
    r = Math.round((ratio - 0.5) * 2 * 255); g = Math.round((1 - (ratio - 0.5) * 2) * 255); b = 0
  }
  return `rgb(${r},${g},${b})`
}

function valToLevel(val: number, minVal: number, maxVal: number, levels: number): number {
  if (maxVal === minVal) return Math.floor(levels / 2)
  const ratio = (val - minVal) / (maxVal - minVal)
  return Math.min(levels - 1, Math.floor(ratio * levels))
}

function renderWaferMap(tabId: string, canvas: HTMLCanvasElement) {
  const tab = tabs.value.find(t => t.id === tabId)
  if (!tab?.data) return

  // 只收集未被隐藏的site数据
  const siteDataMap: Map<number, any[]> = new Map()
  tab.data.sites.forEach((s: any) => {
    if (s.site > 0 && s.wafer_map && !hiddenSites.value.has(s.site)) {
      siteDataMap.set(s.site, s.wafer_map)
    }
  })

  const allData: any[] = []
  siteDataMap.forEach((dies, siteNum) => {
    dies.forEach(d => allData.push({ ...d, site: siteNum }))
  })

  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.clearRect(0, 0, canvas.width, canvas.height)

  if (allData.length === 0) {
    if (waferMapState[tabId]) waferMapState[tabId].dies = []
    return
  }

  const { min: minVal, max: maxVal } = getGlobalRange(tab)

  // 用全部site（含隐藏的）计算坐标范围，保持map位置稳定
  const allCoords: any[] = []
  tab.data.sites.forEach((s: any) => {
    if (s.site > 0 && s.wafer_map) allCoords.push(...s.wafer_map)
  })
  const xs = allCoords.map((d: any) => d.x)
  const ys = allCoords.map((d: any) => d.y)
  const minX = Math.min(...xs), maxX = Math.max(...xs)
  const minY = Math.min(...ys), maxY = Math.max(...ys)

  // 布局：左侧range文字区 | 色块 | 右侧count文字区
  const LEGEND_RANGE_W = 80   // 左侧range文字
  const LEGEND_BLOCK_W = 16   // 色块宽度
  const LEGEND_COUNT_W = 55   // 右侧count文字
  const LEGEND_TOTAL_W = LEGEND_RANGE_W + LEGEND_BLOCK_W + LEGEND_COUNT_W + 8
  const W = canvas.width
  const H = canvas.height
  const margin = 30
  const mapAreaW = W - LEGEND_TOTAL_W - margin  // 地图可用宽度

  const cellW = (mapAreaW - margin * 2) / (maxX - minX + 1)
  const cellH = (H - margin * 2) / (maxY - minY + 1)
  const cellSize = Math.min(cellW, cellH) - 1

  // 统计每个色阶die数量
  const levelCounts = new Array(NUM_COLOR_LEVELS).fill(0)
  allData.forEach(d => {
    levelCounts[valToLevel(d.val, minVal, maxVal, NUM_COLOR_LEVELS)]++
  })

  // 绘制die，记录位置供hover检测
  const dies: typeof waferMapState[string]['dies'] = []
  allData.forEach(d => {
    const px = margin + (d.x - minX) * cellW + cellW / 2 - cellSize / 2
    const py = margin + (d.y - minY) * cellH + cellH / 2 - cellSize / 2
    const lvl = valToLevel(d.val, minVal, maxVal, NUM_COLOR_LEVELS)
    ctx.fillStyle = levelToColor(lvl, NUM_COLOR_LEVELS)
    ctx.fillRect(px, py, cellSize, cellSize)
    dies.push({ px, py, size: cellSize, dieX: d.x, dieY: d.y, val: d.val, site: d.site })
  })
  if (waferMapState[tabId]) waferMapState[tabId].dies = dies

  // ── 绘制图例（三列：range | 色块 | count）────────────
  const legendStartX = mapAreaW + margin + 4
  const legendTopY = margin
  const totalLegendH = H - margin * 2
  const blockH = Math.floor(totalLegendH / NUM_COLOR_LEVELS)

  const blockX = legendStartX + LEGEND_RANGE_W + 4
  const countX = blockX + LEGEND_BLOCK_W + 4

  ctx.font = '9px Arial'

  for (let lvl = NUM_COLOR_LEVELS - 1; lvl >= 0; lvl--) {
    // 从顶部开始，顶部对应最高值
    const drawRow = NUM_COLOR_LEVELS - 1 - lvl
    const blockY = legendTopY + drawRow * blockH
    const midY = blockY + blockH / 2

    const rangeMin = minVal + (lvl / NUM_COLOR_LEVELS) * (maxVal - minVal)
    const rangeMax = minVal + ((lvl + 1) / NUM_COLOR_LEVELS) * (maxVal - minVal)

    // 左侧：range文字，右对齐到色块左边
    ctx.fillStyle = '#333'
    ctx.textAlign = 'right'
    ctx.textBaseline = 'bottom'
    ctx.fillText(rangeMax.toFixed(3), blockX - 4, midY + 1)
    ctx.fillStyle = '#999'
    ctx.textBaseline = 'top'
    ctx.fillText(rangeMin.toFixed(3), blockX - 4, midY)

    // 中间：色块
    ctx.fillStyle = levelToColor(lvl, NUM_COLOR_LEVELS)
    ctx.fillRect(blockX, blockY, LEGEND_BLOCK_W, blockH - 1)

    // 右侧：count
    ctx.fillStyle = '#444'
    ctx.textAlign = 'left'
    ctx.textBaseline = 'middle'
    ctx.fillText(`${levelCounts[lvl]}`, countX, midY)
  }

  // 图例标题
  ctx.fillStyle = '#555'
  ctx.font = 'bold 9px Arial'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'bottom'
  ctx.fillText('Range', blockX - 4 - LEGEND_RANGE_W / 2, legendTopY - 2)
  ctx.fillText('n', countX + 20, legendTopY - 2)
}

// ── 工具函数 ───────────────────────────────────────────
function cpkColor(val: number | null) {
  if (val === null || val === undefined) return {}
  if (val < 1.0) return { color: 'red', fontWeight: 'bold' }
  if (val < 1.33) return { color: 'orange' }
  return {}
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
  await fetchParamList()
  await fetchBinSummary()
  await fetchLotInfo()
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

.lot-info-bar {
  background: white;
  padding: 10px 16px;
  border-radius: 6px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  margin-bottom: 8px;
}

.info-grid { display: flex; flex-wrap: wrap; gap: 16px; }
.info-item { display: flex; flex-direction: column; gap: 2px; }
.label { font-size: 11px; color: #999; }
.value { font-size: 13px; color: #333; font-weight: 500; }

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

.tab-close { font-size: 14px; color: #999; line-height: 1; }
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

.option-item { display: flex; align-items: center; gap: 6px; font-size: 12px; }
.option-item label { color: #666; }
.option-item select, .option-item input[type="number"] {
  padding: 3px 6px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  font-size: 12px;
}
.option-item button {
  padding: 3px 10px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  background: white;
  cursor: pointer;
  font-size: 12px;
}

.content-row {
  flex: 1;
  display: flex;
  gap: 12px;
  overflow-y: auto;
  overflow-x: hidden;
}

.charts-area {
  width: 840px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.stats-table table { width: 100%; border-collapse: collapse; font-size: 12px; }
.stats-table th, .stats-table td {
  border: 1px solid #f0f0f0;
  padding: 4px 8px;
  text-align: center;
}
.stats-table th { background: #fafafa; color: #666; }

.chart-container {
  background: #fafafa;
  border-radius: 4px;
  padding: 8px;
  flex-shrink: 0;
  display: flex;
  justify-content: center;
}

.wafer-tooltip {
  position: absolute;
  background: rgba(0,0,0,0.78);
  color: white;
  padding: 5px 10px;
  border-radius: 4px;
  font-size: 12px;
  pointer-events: none;
  white-space: nowrap;
  z-index: 10;
  line-height: 1.6;
}

/* Map下方Site图例 */
.wafer-legend {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  padding: 6px 4px 2px;
  justify-content: center;
}

.wafer-legend-item {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  cursor: pointer;
  padding: 2px 8px;
  border-radius: 3px;
  border: 1px solid #e0e0e0;
  background: #fff;
  user-select: none;
  transition: opacity 0.15s;
}

.wafer-legend-item.hidden {
  opacity: 0.35;
  text-decoration: line-through;
}

.wafer-legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 2px;
  display: inline-block;
  flex-shrink: 0;
}

.bin-table { width: 200px; flex-shrink: 0; }
.bin-title { font-size: 12px; font-weight: 600; color: #333; margin-bottom: 6px; }
.bin-table table { width: 100%; border-collapse: collapse; font-size: 11px; }
.bin-table th, .bin-table td { border: 1px solid #f0f0f0; padding: 3px 6px; }
.bin-table th { background: #fafafa; }
</style>
