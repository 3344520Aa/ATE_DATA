<template>
  <div class="bin-view">
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

    <!-- Options栏 -->
    <div class="options-bar">
      <div class="opt-group">
        <span class="opt-label">DataRange</span>
        <label><input type="radio" v-model="options.data_range" value="final" @change="onDataRangeChange" /> Final</label>
        <label><input type="radio" v-model="options.data_range" value="original" @change="onDataRangeChange" /> Original</label>
      </div>

      <div class="opt-group">
        <span class="opt-label">Site</span>
        <label>
          <input type="checkbox" :checked="isAllSiteSelected" @change="toggleAllSite" /> All
        </label>
        <label v-for="s in allSites" :key="s">
          <input type="checkbox" :checked="options.selected_sites.includes(s)" @change="toggleSite(s)" />
          Site{{ s }}
        </label>
      </div>

      <div class="opt-group">
        <span class="opt-label">Map旋转</span>
        <select v-model="options.rotate" @change="renderBinMap()" style="font-size:12px;padding:2px 6px;border:1px solid #d9d9d9;border-radius:4px">
          <option value="0">0°</option>
          <option value="90">90°</option>
          <option value="180">180°</option>
          <option value="270">270°</option>
        </select>
      </div>

      <div class="opt-group">
        <label><input type="checkbox" v-model="options.show_yield_plot" @change="renderYieldPlot" /> Yield Plot</label>
        <label><input type="checkbox" v-model="options.show_fail_bin" @change="renderFailBinChart" /> Fail Bin Analysis</label>
      </div>

      <button class="export-btn" @click="handleExport">Export Report</button>
    </div>

    <!-- Bin汇总表格 -->
    <div class="bin-table-area">
      <table class="bin-table">
        <thead>
          <tr>
            <th>Bin</th>
            <th>Name</th>
            <th v-for="s in options.selected_sites" :key="s">Site{{ s }}</th>
            <th>All Site</th>
            <th>% of total</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="b in binData.bins" :key="b.bin_number" :class="{ 'pass-row': isPassBin(b.bin_number) }">
            <td>
              <span class="bin-link" @click="openBinDetail(b.bin_number, b.bin_name)">{{ b.bin_number }}</span>
            </td>
            <td>{{ b.bin_name }}</td>
            <td v-for="s in options.selected_sites" :key="s">
              {{ b.sites[`site${s}`]?.count ?? 0 }}
            </td>
            <td>{{ b.all_site_count }}</td>
            <td>{{ b.all_site_pct?.toFixed(2) }}%</td>
          </tr>
        </tbody>
        <tfoot>
          <tr class="summary-row">
            <td colspan="2">Passes</td>
            <td v-for="s in options.selected_sites" :key="s">{{ getSitePass(s) }}</td>
            <td>{{ getTotalPass() }}</td>
            <td>{{ getTotalAll() > 0 ? (getTotalPass() / getTotalAll() * 100).toFixed(2) + '%' : '-' }}</td>
          </tr>
          <tr class="summary-row">
            <td colspan="2">Fails</td>
            <td v-for="s in options.selected_sites" :key="s">{{ getSiteFail(s) }}</td>
            <td>{{ getTotalFail() }}</td>
            <td>{{ getTotalAll() > 0 ? (getTotalFail() / getTotalAll() * 100).toFixed(2) + '%' : '-' }}</td>
          </tr>
          <tr class="summary-row">
            <td colspan="2">Sum</td>
            <td v-for="s in options.selected_sites" :key="s">{{ getSiteTotal(s) }}</td>
            <td>{{ getTotalAll() }}</td>
            <td>100.00%</td>
          </tr>
        </tfoot>
      </table>
    </div>

    <!-- 底部三栏 -->
    <div class="bottom-area">
      <!-- 左：Bin Map -->
      <div class="map-section">
        <div class="section-title">Bin Map</div>
        <div class="map-with-legend">
          <canvas ref="binMapCanvas" width="480" height="520"
            style="width:480px;height:520px;border:1px solid #eee;flex-shrink:0"></canvas>
          <div class="bin-legend">
            <div :class="['bin-icon', { selected: selectedBin === null }]"
              @click="selectedBin = null; renderBinMap()">
              <span class="bin-dot" style="background:#aaa"></span>
              <span>ALL</span>
            </div>
            <div v-for="b in failBins" :key="b.bin_number"
              :class="['bin-icon', { selected: selectedBin === b.bin_number }]"
              @click="toggleBinHighlight(b.bin_number)">
              <span class="bin-dot" :style="{ background: getBinColor(b.bin_number) }"></span>
              <span>Bin{{ b.bin_number }}({{ b.all_site_count }})</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 中：Yield Plot -->
      <div class="chart-section" v-if="options.show_yield_plot">
        <div class="section-title">Yield Plot</div>
        <canvas ref="yieldPlotCanvas" width="400" height="400"
          style="width:400px;height:400px"></canvas>
      </div>

      <!-- 右：Fail Bin Analysis -->
      <div class="chart-section" v-if="options.show_fail_bin">
        <div class="section-title">Fail Bin Analysis</div>
        <div ref="failBinChartRef" style="width:100%;height:400px"></div>
      </div>
    </div>

    <!-- 复测分析（折叠） -->
    <div class="retest-section" v-if="hasCoords">
      <div class="retest-header" @click="retestExpanded = !retestExpanded">
        <span>复测分析</span>
        <span>{{ retestExpanded ? '▲' : '▼' }}</span>
      </div>
      <div v-if="retestExpanded && retestData">
        <!-- 总计统计 -->
        <div class="retest-totals">
          <span class="total-item pass">✅ Fail→Pass: {{ retestData.totals.fail_to_pass }}个</span>
          <span class="total-item fail">❌ Pass→Fail: {{ retestData.totals.pass_to_fail }}个</span>
          <span class="total-item change">🔄 Fail→Fail(换Bin): {{ retestData.totals.fail_to_fail }}个</span>
          <span class="total-item same">➖ Pass→Pass: {{ retestData.totals.pass_to_pass }}个</span>
          <span class="total-item">总复测Die: {{ retestData.totals.total_retest_dies }}个</span>
        </div>

        <!-- 转移汇总表 -->
        <div class="retest-tables">
          <div class="retest-table-wrap">
            <div class="table-title">Bin转移汇总</div>
            <table class="retest-table">
              <thead>
                <tr>
                  <th class="sortable" @click="toggleRetestSort('from_bin')">
                    首次Bin
                    <span>{{ retestSortKey === 'from_bin' ? (retestSortDir === 'asc' ? '↑' : '↓') : '↕' }}</span>
                  </th>
                  <th>转移到</th>
                  <th class="sortable" @click="toggleRetestSort('count')">
                    数量
                    <span>{{ retestSortKey === 'count' ? (retestSortDir === 'asc' ? '↑' : '↓') : '↕' }}</span>
                  </th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="s in sortedRetestSummary" :key="`${s.from_bin}-${s.to_bin}`"
                  :class="directionClass(s.direction, s.no_change)">
                  <td>Bin{{ s.from_bin }}</td>
                  <td>Bin{{ s.to_bin }}</td>
                  <td>{{ s.count }}</td>
                  <td>{{ directionLabel(s.direction, s.no_change) }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- 逐坐标明细表 -->
          <div class="retest-table-wrap">
            <div class="table-title">逐坐标明细（最多500条）</div>
            <div style="max-height:300px;overflow-y:auto">
              <table class="retest-table">
                <thead>
                  <tr><th>X</th><th>Y</th><th>首次Site</th><th>首次Bin</th><th>末次Site</th><th>末次Bin</th><th>复测次数</th><th>Site变化</th></tr>
                </thead>
                <tbody>
                  <tr v-for="d in retestData.details" :key="`${d.x}-${d.y}`"
                    :class="directionClass(getDirection(d.first_bin, d.last_bin), d.first_bin === d.last_bin)">
                    <td>{{ d.x }}</td>
                    <td>{{ d.y }}</td>
                    <td>Site{{ d.first_site }}</td>
                    <td>Bin{{ d.first_bin }}</td>
                    <td>Site{{ d.last_site }}</td>
                    <td>Bin{{ d.last_bin }}</td>
                    <td>{{ d.retest_count }}</td>
                    <td>{{ d.site_changed ? '✓' : '' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Bin详情弹窗 -->
    <div v-if="binDetailVisible" class="modal-overlay" @click.self="binDetailVisible = false">
      <div class="modal">
        <div class="modal-header">
          <span>Bin{{ binDetailNum }} - {{ binDetailName }} 分布</span>
          <span class="modal-close" @click="binDetailVisible = false">×</span>
        </div>
        <canvas ref="binDetailCanvas" width="500" height="500"
          style="width:500px;height:500px"></canvas>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { useRoute } from 'vue-router'
import * as echarts from 'echarts'
import api from '@/api'

const route = useRoute()
const lotId = ref(Number(route.params.id))

const binMapCanvas = ref<HTMLCanvasElement>()
const yieldPlotCanvas = ref<HTMLCanvasElement>()
const failBinChartRef = ref<HTMLElement>()
const binDetailCanvas = ref<HTMLCanvasElement>()
let failBinChart: echarts.ECharts | null = null

const lotInfo = ref<any>(null)
const binData = ref<any>({ bins: [], sites: [], all_sites: [] })
const allSites = ref<number[]>([])
const passBins = ref<number[]>([])
const selectedBin = ref<number | null>(null)
const retestData = ref<any>(null)
const retestExpanded = ref(false)
const hasCoords = ref(false)
const binDetailVisible = ref(false)
const binDetailNum = ref(0)
const binDetailName = ref('')
const mapCache = ref<any[]>([])

const options = ref({
  data_range: 'final',
  selected_sites: [] as number[],
  rotate: '0',
  show_yield_plot: false,
  show_fail_bin: false,
})

const BIN_COLORS: Record<number, string> = {}
const FAIL_COLORS = [
  '#ff6b6b', '#4dabf7', '#ffd43b', '#e599f7', '#74c0fc',
  '#ffa94d', '#da77f2', '#ff8787', '#339af0', '#fcc419',
  '#cc5de8', '#22b8cf', '#ff922b', '#845ef7', '#f06595', '#66d9e8'
]



function getBinColor(binNum: number): string {
  if (isPassBin(binNum)) return '#69db7c'
  if (!BIN_COLORS[binNum]) {
    const idx = Object.keys(BIN_COLORS).length % FAIL_COLORS.length
    BIN_COLORS[binNum] = FAIL_COLORS[idx]
  }
  return BIN_COLORS[binNum]
}

function isPassBin(binNum: number): boolean {
  return passBins.value.includes(binNum)
}

const failBins = computed(() => {
  if (!binData.value?.bins) return []
  return binData.value.bins
    .filter((b: any) => !isPassBin(b.bin_number))
    .sort((a: any, b: any) => b.all_site_count - a.all_site_count)
})

const isAllSiteSelected = computed(() =>
  allSites.value.length > 0 &&
  allSites.value.every(s => options.value.selected_sites.includes(s))
)

function toggleAllSite() {
  if (isAllSiteSelected.value) {
    options.value.selected_sites = []
  } else {
    options.value.selected_sites = [...allSites.value]
  }
  refreshAll()
}

function toggleSite(site: number) {
  const idx = options.value.selected_sites.indexOf(site)
  if (idx >= 0) {
    if (options.value.selected_sites.length === 1) return // 至少保留一个
    options.value.selected_sites.splice(idx, 1)
  } else {
    options.value.selected_sites.push(site)
    options.value.selected_sites.sort((a, b) => a - b)
  }
  refreshAll()
}

function getSitePass(site: number) {
  return binData.value.bins
    .filter((b: any) => isPassBin(b.bin_number))
    .reduce((sum: number, b: any) => sum + (b.sites[`site${site}`]?.count ?? 0), 0)
}
function getSiteFail(site: number) {
  return binData.value.bins
    .filter((b: any) => !isPassBin(b.bin_number))
    .reduce((sum: number, b: any) => sum + (b.sites[`site${site}`]?.count ?? 0), 0)
}
function getSiteTotal(site: number) {
  return binData.value.bins
    .reduce((sum: number, b: any) => sum + (b.sites[`site${site}`]?.count ?? 0), 0)
}
function getTotalPass() {
  return binData.value.bins
    .filter((b: any) => isPassBin(b.bin_number))
    .reduce((sum: number, b: any) => sum + b.all_site_count, 0)
}
function getTotalFail() {
  return binData.value.bins
    .filter((b: any) => !isPassBin(b.bin_number))
    .reduce((sum: number, b: any) => sum + b.all_site_count, 0)
}
function getTotalAll() {
  return binData.value.bins.reduce((sum: number, b: any) => sum + b.all_site_count, 0)
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

// 复测汇总排序
const retestSortKey = ref<'from_bin' | 'count'>('count')
const retestSortDir = ref<'asc' | 'desc'>('desc')

const sortedRetestSummary = computed(() => {
  if (!retestData.value?.summary) return []
  return [...retestData.value.summary].sort((a, b) => {
    const dir = retestSortDir.value === 'asc' ? 1 : -1
    return (a[retestSortKey.value] - b[retestSortKey.value]) * dir
  })
})

function toggleRetestSort(key: 'from_bin' | 'count') {
  if (retestSortKey.value === key) {
    retestSortDir.value = retestSortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    retestSortKey.value = key
    retestSortDir.value = key === 'count' ? 'desc' : 'asc'
  }
}

async function fetchLotInfo() {
  lotInfo.value = await api.get(`/analysis/lot/${lotId.value}/info`)
}

async function fetchBinData() {
  const sitesParam = options.value.selected_sites.join(',') || 'all'
  const data: any = await api.get(`/analysis/lot/${lotId.value}/bin_summary`, {
    params: { data_range: options.value.data_range, sites: sitesParam }
  })
  binData.value = data

  if (allSites.value.length === 0 && data.all_sites?.length > 0) {
    allSites.value = data.all_sites
    options.value.selected_sites = [...data.all_sites]
  }
}

async function fetchPassBins() {
  const data: any = await api.get(`/analysis/lot/${lotId.value}/bin_definitions`)
  passBins.value = data.pass_bins ?? [1, 2]
}

async function fetchMapData() {
  try {
    const sitesParam = options.value.selected_sites.join(',') || 'all'
    const mapData: any = await api.get(`/analysis/lot/${lotId.value}/wafer_bin_map`, {
      params: {
        data_range: options.value.data_range,
        sites: sitesParam
      }
    })
    mapCache.value = mapData.data ?? []
    hasCoords.value = mapData.has_map
  } catch (e) {
    mapCache.value = []
    hasCoords.value = false
  }
}

async function fetchRetestData() {
  if (!hasCoords.value) return
  const sitesParam = options.value.selected_sites.join(',') || 'all'
  try {
    retestData.value = await api.get(`/analysis/lot/${lotId.value}/retest_analysis`, {
      params: { sites: sitesParam }
    })
  } catch (e) {
    retestData.value = null
  }
}



async function refreshAll() {
  await fetchBinData()
  await fetchMapData()
  renderBinMap()
  if (options.value.show_yield_plot) renderYieldPlot()
  if (options.value.show_fail_bin) renderFailBinChart()
  if (retestExpanded.value) await fetchRetestData()
}

async function onDataRangeChange() {
  await refreshAll()
}

watch(retestExpanded, async (val) => {
  if (val && !retestData.value) {
    await fetchRetestData()
  }
})

// ── Bin Map ───────────────────────────────────────────
function renderBinMap() {
  const canvas = binMapCanvas.value
  if (!canvas || !mapCache.value.length) return

  // Site过滤
  let data = mapCache.value
  if (options.value.selected_sites.length < allSites.value.length) {
    // 需要按site过滤，但mapCache没有site信息，需要从parquet读
    // 暂时显示全部
  }

  drawBinMap(canvas, data, selectedBin.value)
}

function applyRotation(x: number, y: number, minX: number, maxX: number, minY: number, maxY: number) {
  switch (options.value.rotate) {
    case '90':  return { x: maxY - y + minX, y: x - minX + minY }
    case '180': return { x: maxX - x + minX, y: maxY - y + minY }
    case '270': return { x: y - minY + minX, y: maxX - x + minY }
    default:    return { x, y }
  }
}

function drawBinMap(canvas: HTMLCanvasElement, data: any[], highlightBin: number | null, singleBin?: number) {
  const ctx = canvas.getContext('2d')
  if (!ctx || !data.length) return

  const xs = data.map(d => d.x), ys = data.map(d => d.y)
  const minX = Math.min(...xs), maxX = Math.max(...xs)
  const minY = Math.min(...ys), maxY = Math.max(...ys)

  const rotated = data.map(d => {
    const r = applyRotation(d.x, d.y, minX, maxX, minY, maxY)
    return { ...d, rx: r.x, ry: r.y }
  })

  const rxs = rotated.map(d => d.rx), rys = rotated.map(d => d.ry)
  const rMinX = Math.min(...rxs), rMaxX = Math.max(...rxs)
  const rMinY = Math.min(...rys), rMaxY = Math.max(...rys)

  const W = canvas.width, H = canvas.height, margin = 24
  const cellW = (W - margin * 2) / (rMaxX - rMinX + 1)
  const cellH = (H - margin * 2) / (rMaxY - rMinY + 1)
  const cellSize = Math.min(cellW, cellH) - 0.5

  ctx.clearRect(0, 0, W, H)

  const coordSet = new Set(rotated.map(d => `${d.rx},${d.ry}`))
  const isEdge = (rx: number, ry: number) =>
    !coordSet.has(`${rx-1},${ry}`) || !coordSet.has(`${rx+1},${ry}`) ||
    !coordSet.has(`${rx},${ry-1}`) || !coordSet.has(`${rx},${ry+1}`)

  rotated.forEach(d => {
    const px = margin + (d.rx - rMinX) * cellW + (cellW - cellSize) / 2
    const py = margin + (d.ry - rMinY) * cellH + (cellH - cellSize) / 2

    let color = ''
    if (highlightBin !== null) {
      if (d.bin === highlightBin) color = getBinColor(d.bin)
      else if (isEdge(d.rx, d.ry)) color = 'rgba(200,200,200,0.25)'
      else return
    } else if (singleBin !== undefined) {
      if (d.bin === singleBin) color = getBinColor(d.bin)
      else if (isEdge(d.rx, d.ry)) color = 'rgba(200,200,200,0.25)'
      else return
    } else {
      color = getBinColor(d.bin)
    }

    ctx.fillStyle = color
    ctx.fillRect(px, py, cellSize, cellSize)

    if (d.retest) {
      ctx.fillStyle = 'rgba(0,0,0,0.2)'
      const cx = px + cellSize / 2, cy = py + cellSize / 2
      const arm = cellSize * 0.3, thick = Math.max(1, cellSize * 0.15)
      ctx.fillRect(cx - thick / 2, cy - arm, thick, arm * 2)
      ctx.fillRect(cx - arm, cy - thick / 2, arm * 2, thick)
    }
  })

  // 坐标标注
  ctx.fillStyle = '#aaa'
  ctx.font = `${Math.max(8, Math.min(11, cellSize))}px sans-serif`
  ctx.textAlign = 'center'
  const xStep = Math.ceil((rMaxX - rMinX + 1) / 8)
  for (let rx = rMinX; rx <= rMaxX; rx += xStep) {
    ctx.fillText(String(rx), margin + (rx - rMinX) * cellW + cellW / 2, margin - 4)
  }
  ctx.textAlign = 'right'
  const yStep = Math.ceil((rMaxY - rMinY + 1) / 8)
  for (let ry = rMinY; ry <= rMaxY; ry += yStep) {
    ctx.fillText(String(ry), margin - 4, margin + (ry - rMinY) * cellH + cellH / 2 + 4)
  }
}

// ── Yield Plot（12区域晶圆良率图）───────────────────────
function renderYieldPlot() {
  const canvas = yieldPlotCanvas.value
  if (!canvas || !mapCache.value.length) return

  const data = mapCache.value
  const xs = data.map(d => d.x), ys = data.map(d => d.y)
  const minX = Math.min(...xs), maxX = Math.max(...xs)
  const minY = Math.min(...ys), maxY = Math.max(...ys)
  const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2

  // 计算每个die到圆心的距离和角度
  const maxR = Math.max(...data.map(d => Math.sqrt((d.x - cx) ** 2 + (d.y - cy) ** 2)))

  // 3环 × 4象限 = 12区域
  const rings = 3, sectors = 4
  const zones: { pass: number, total: number }[][] = Array.from(
    { length: rings }, () => Array.from({ length: sectors }, () => ({ pass: 0, total: 0 }))
  )

  data.forEach(d => {
    const dx = d.x - cx, dy = d.y - cy
    const r = Math.sqrt(dx ** 2 + dy ** 2)
    const angle = Math.atan2(dy, dx)

    const ringIdx = Math.min(Math.floor(r / maxR * rings), rings - 1)
    const sectorIdx = Math.floor(((angle + Math.PI) / (2 * Math.PI)) * sectors) % sectors

    zones[ringIdx][sectorIdx].total++
    if (isPassBin(d.bin)) zones[ringIdx][sectorIdx].pass++
  })

  const ctx = canvas.getContext('2d')
  if (!ctx) return
  const W = canvas.width, H = canvas.height
  const centerX = W / 2, centerY = H / 2
  const maxRadius = Math.min(W, H) / 2 - 20

  ctx.clearRect(0, 0, W, H)

  for (let ri = rings - 1; ri >= 0; ri--) {
    const outerR = maxRadius * (ri + 1) / rings
    const innerR = maxRadius * ri / rings

    for (let si = 0; si < sectors; si++) {
      const startAngle = (si / sectors) * 2 * Math.PI - Math.PI / 2
      const endAngle = ((si + 1) / sectors) * 2 * Math.PI - Math.PI / 2
      const zone = zones[ri][si]
      const yield_ = zone.total > 0 ? zone.pass / zone.total : 0

      // 颜色：低良率红→高良率绿
      const r = Math.round(255 * (1 - yield_))
      const g = Math.round(255 * yield_)
      ctx.fillStyle = `rgba(${r},${g},0,0.8)`

      ctx.beginPath()
      ctx.arc(centerX, centerY, outerR, startAngle, endAngle)
      ctx.arc(centerX, centerY, innerR, endAngle, startAngle, true)
      ctx.closePath()
      ctx.fill()
      ctx.strokeStyle = 'white'
      ctx.lineWidth = 1.5
      ctx.stroke()

      // 显示良率文字
      const midR = (innerR + outerR) / 2
      const midAngle = (startAngle + endAngle) / 2
      const tx = centerX + midR * Math.cos(midAngle)
      const ty = centerY + midR * Math.sin(midAngle)
      ctx.fillStyle = 'white'
      ctx.font = 'bold 11px sans-serif'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillText((yield_ * 100).toFixed(1) + '%', tx, ty)
    }
  }
}

// ── Fail Bin 柱状图 ───────────────────────────────────
function renderFailBinChart() {
  if (!options.value.show_fail_bin) return
  nextTick(() => {
    if (!failBinChart && failBinChartRef.value) {
      failBinChart = echarts.init(failBinChartRef.value)
    }
    const failBinList = binData.value.bins.filter((b: any) => !isPassBin(b.bin_number))
    failBinChart?.setOption({
      title: { text: 'Fail Bin Analysis', left: 'center', textStyle: { fontSize: 12 } },
      tooltip: { trigger: 'axis' },
      xAxis: {
        type: 'category',
        data: failBinList.map((b: any) => `Bin${b.bin_number}\n${b.bin_name}`),
        axisLabel: { rotate: 45, fontSize: 10 }
      },
      yAxis: { type: 'value', name: 'Count' },
      series: [{
        type: 'bar',
        data: failBinList.map((b: any) => b.all_site_count),
        itemStyle: { color: (params: any) => getBinColor(failBinList[params.dataIndex].bin_number) },
        label: { show: true, position: 'top', fontSize: 10 }
      }]
    })
  })
}

function toggleBinHighlight(binNum: number) {
  selectedBin.value = selectedBin.value === binNum ? null : binNum
  renderBinMap()
}

async function openBinDetail(binNum: number, binName: string) {
  binDetailNum.value = binNum
  binDetailName.value = binName
  binDetailVisible.value = true
  await nextTick()
  if (binDetailCanvas.value) {
    drawBinMap(binDetailCanvas.value, mapCache.value, null, binNum)
  }
}

// ── 复测分析辅助函数 ──────────────────────────────────
function getDirection(fb: number, lb: number): string {
  const fbPass = isPassBin(fb), lbPass = isPassBin(lb)
  if (fbPass && lbPass) return 'pass_pass'
  if (!fbPass && lbPass) return 'fail_pass'
  if (fbPass && !lbPass) return 'pass_fail'
  return 'fail_fail'
}

function directionClass(direction: string, noChange: boolean) {
  if (noChange) return 'row-same'
  if (direction === 'fail_pass') return 'row-improve'
  if (direction === 'pass_fail') return 'row-drop'
  if (direction === 'fail_fail') return 'row-change'
  return ''
}

function directionLabel(direction: string, noChange: boolean) {
  if (noChange) return '无变化'
  if (direction === 'fail_pass') return '✅ Fail→Pass'
  if (direction === 'pass_fail') return '❌ Pass→Fail'
  if (direction === 'fail_fail') return '🔄 Fail→Fail'
  return 'Pass→Pass'
}

function handleExport() {
  alert('导出功能开发中')
}

onMounted(async () => {
  await fetchLotInfo()
  await fetchPassBins()
  await fetchBinData()
  await fetchMapData()
  await nextTick()
  renderBinMap()
})
</script>

<style scoped>
.bin-view {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-bottom: 20px;
}

.sortable {
  cursor: pointer;
  user-select: none;
}
.sortable:hover { background: #f0f0f0; }

.lot-info-bar {
  background: white;
  padding: 10px 16px;
  border-radius: 6px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}

.info-grid { display: flex; flex-wrap: wrap; gap: 16px; }
.info-item { display: flex; flex-direction: column; gap: 2px; }
.label { font-size: 11px; color: #999; }
.value { font-size: 13px; color: #333; font-weight: 500; }

.options-bar {
  background: white;
  padding: 8px 16px;
  border-radius: 6px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  display: flex;
  align-items: center;
  gap: 20px;
  flex-wrap: wrap;
  font-size: 12px;
}

.opt-group { display: flex; align-items: center; gap: 8px; }
.opt-label { color: #666; font-weight: 500; white-space: nowrap; }

.export-btn {
  margin-left: auto;
  background: white;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  padding: 5px 14px;
  cursor: pointer;
  font-size: 12px;
}

.bin-table-area {
  background: white;
  border-radius: 6px;
  padding: 12px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  overflow-x: auto;
}

.bin-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.bin-table th, .bin-table td {
  border: 1px solid #f0f0f0;
  padding: 5px 10px;
  text-align: center;
  white-space: nowrap;
}
.bin-table th { background: #fafafa; color: #666; }
.pass-row { background: #f6ffed; }
.summary-row { background: #fafafa; font-weight: 500; }
.bin-link { color: #1890ff; cursor: pointer; text-decoration: underline; }

.bottom-area {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  background: white;
  border-radius: 6px;
  padding: 12px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}

.map-section { flex-shrink: 0; display: flex; flex-direction: column; gap: 8px; }
.chart-section { flex: 1; display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.section-title { font-size: 13px; font-weight: 600; text-align: center; }

.map-with-legend { display: flex; gap: 8px; align-items: flex-start; }

.bin-legend {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 520px;
  overflow-y: auto;
  padding-right: 4px;
}

.bin-icon {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 1px 4px;
  border-radius: 3px;
  cursor: pointer;
  font-size: 10px;
  white-space: nowrap;
}
.bin-icon.selected { background: #e6f7ff; }
.bin-icon:hover { background: #f5f5f5; }

.bin-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

/* 复测分析 */
.retest-section {
  background: white;
  border-radius: 6px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  overflow: hidden;
}

.retest-header {
  display: flex;
  justify-content: space-between;
  padding: 10px 16px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  background: #fafafa;
  border-bottom: 1px solid #f0f0f0;
}
.retest-header:hover { background: #f0f0f0; }

.retest-totals {
  display: flex;
  gap: 16px;
  padding: 10px 16px;
  flex-wrap: wrap;
  font-size: 12px;
  border-bottom: 1px solid #f0f0f0;
}

.total-item { padding: 4px 10px; border-radius: 4px; background: #f5f5f5; }
.total-item.pass { background: #f6ffed; color: #52c41a; }
.total-item.fail { background: #fff2f0; color: #ff4d4f; }
.total-item.change { background: #fff7e6; color: #fa8c16; }

.retest-tables {
  display: flex;
  gap: 16px;
  padding: 12px 16px;
}

.retest-table-wrap { flex: 1; }
.table-title { font-size: 12px; font-weight: 600; margin-bottom: 6px; color: #666; }

.retest-table { width: 100%; border-collapse: collapse; font-size: 11px; }
.retest-table th, .retest-table td {
  border: 1px solid #f0f0f0;
  padding: 4px 8px;
  text-align: center;
}
.retest-table th { background: #fafafa; }

.row-improve { background: #f6ffed; }
.row-drop { background: #fff2f0; }
.row-change { background: #fff7e6; }
.row-same { color: #999; }

/* Bin详情弹窗 */
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
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.2);
}
.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 600;
}
.modal-close { cursor: pointer; color: #999; font-size: 18px; }
.modal-close:hover { color: red; }
</style>