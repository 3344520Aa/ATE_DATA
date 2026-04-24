<template>
  <div class="multi-bin-view">
    <!-- Options栏 -->
    <div class="options-bar">
      <div class="opt-group">
        <span class="opt-label">DataRange</span>
        <label><input type="radio" v-model="dataRange" value="final" @change="fetchAll" /> Final</label>
        <label><input type="radio" v-model="dataRange" value="original" @change="fetchAll" /> Original</label>
      </div>
    </div>

    <!-- Bin汇总表 -->
    <div class="table-wrap" v-if="bins.length">
      <table class="bin-table">
        <thead>
          <!-- 第一行：LOT名 colspan=2 -->
          <tr>
            <th rowspan="2">Bin</th>
            <th rowspan="2">Name</th>
            <th
              v-for="lot in lots"
              :key="lot.id"
              colspan="2"
              class="lot-header"
            >{{ lot.filename }}</th>
          </tr>
          <!-- 第二行：Count / % -->
          <tr>
            <template v-for="lot in lots" :key="lot.id">
              <th>Count</th>
              <th>%</th>
            </template>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="b in bins"
            :key="b.bin_number"
            :class="{ 'pass-row': isPassBin(b.bin_number) }"
          >
            <td>{{ b.bin_number }}</td>
            <td>{{ b.bin_name }}</td>
            <template v-for="lot in lots" :key="lot.id">
              <td>{{ b.lots[String(lot.id)]?.count ?? 0 }}</td>
              <td>{{ (b.lots[String(lot.id)]?.pct ?? 0).toFixed(2) }}%</td>
            </template>
          </tr>
        </tbody>
        <tfoot>
          <tr class="summary-row">
            <td colspan="2">Total</td>
            <template v-for="lot in lots" :key="lot.id">
              <td>{{ getLotTotal(lot.id) }}</td>
              <td>100%</td>
            </template>
          </tr>
          <tr class="summary-row pass-row">
            <td colspan="2">Pass</td>
            <template v-for="lot in lots" :key="lot.id">
              <td>{{ getLotPass(lot.id) }}</td>
              <td>{{ getLotTotal(lot.id) > 0 ? (getLotPass(lot.id) / getLotTotal(lot.id) * 100).toFixed(2) + '%' : '-' }}</td>
            </template>
          </tr>
          <tr class="summary-row">
            <td colspan="2">Fail</td>
            <template v-for="lot in lots" :key="lot.id">
              <td>{{ getLotFail(lot.id) }}</td>
              <td>{{ getLotTotal(lot.id) > 0 ? (getLotFail(lot.id) / getLotTotal(lot.id) * 100).toFixed(2) + '%' : '-' }}</td>
            </template>
          </tr>
        </tfoot>
      </table>
    </div>
    <div v-else-if="loading" class="loading">加载中...</div>

    <!-- 各LOT Wafer Map 横向并排 -->
    <div class="maps-section" v-if="mapDataList.some(m => m.has_map)">
      <div class="section-title">Wafer Bin Map</div>
      <div class="maps-row">
        <div
          v-for="(mapItem, idx) in mapDataList"
          :key="mapItem.lot_id"
          class="map-block"
          v-show="mapItem.has_map"
        >
          <div class="map-label">{{ mapItem.filename }}</div>
          <div class="map-with-legend">
            <canvas
              :ref="el => setCanvasRef(idx, el)"
              width="500"
              height="500"
              style="width:500px;height:500px;border:1px solid #eee"
            ></canvas>
            <div class="bin-legend">
              <div
                class="bin-icon"
                :class="{ selected: selectedBins[idx] === null }"
                @click="toggleHighlight(idx, null)"
              >
                <span class="bin-dot" style="background:#aaa"></span>
                <span>ALL</span>
              </div>
              <div
                v-for="b in getMapBins(mapItem)"
                :key="b.bin_number"
                class="bin-icon"
                :class="{ selected: selectedBins[idx] === b.bin_number }"
                @click="toggleHighlight(idx, b.bin_number)"
              >
                <span class="bin-dot" :style="{ background: getBinColor(b.bin_number) }"></span>
                <span>Bin{{ b.bin_number }}({{ b.count }})</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import api from '@/api'

const route = useRoute()
const lotIdsStr = route.query.lot_ids as string

const lots = ref<any[]>([])
const bins = ref<any[]>([])
const mapDataList = ref<any[]>([])
const loading = ref(true)
const dataRange = ref('final')
const passBins = ref<number[]>([1, 2])
const selectedBins = ref<Record<number, number | null>>({})

// canvas refs per map index
const canvasRefs: Record<number, HTMLCanvasElement | null> = {}

function setCanvasRef(idx: number, el: any) {
  canvasRefs[idx] = el
  if (el && mapDataList.value[idx]?.has_map) {
    nextTick(() => drawMap(idx))
  }
}

const BIN_COLORS: Record<number, string> = {}
const FAIL_COLORS = [
  '#ff6b6b', '#4dabf7', '#ffd43b', '#e599f7', '#74c0fc',
  '#ffa94d', '#da77f2', '#ff8787', '#339af0', '#fcc419',
  '#cc5de8', '#22b8cf', '#ff922b', '#845ef7', '#f06595',
]

function getBinColor(binNum: number): string {
  if (isPassBin(binNum)) return '#69db7c'
  if (!BIN_COLORS[binNum]) {
    const idx = Object.keys(BIN_COLORS).filter(k => !isPassBin(Number(k))).length % FAIL_COLORS.length
    BIN_COLORS[binNum] = FAIL_COLORS[idx]!
  }
  return BIN_COLORS[binNum]!
}

function isPassBin(binNum: number) {
  return passBins.value.includes(binNum)
}

function getLotTotal(lotId: number) {
  return bins.value.reduce((s, b) => s + (b.lots[String(lotId)]?.count ?? 0), 0)
}
function getLotPass(lotId: number) {
  return bins.value
    .filter(b => isPassBin(b.bin_number))
    .reduce((s, b) => s + (b.lots[String(lotId)]?.count ?? 0), 0)
}
function getLotFail(lotId: number) {
  return getLotTotal(lotId) - getLotPass(lotId)
}

function getMapBins(mapItem: any) {
  const binCounts: Record<number, number> = {}
  mapItem.data.forEach((d: any) => {
    binCounts[d.bin] = (binCounts[d.bin] || 0) + 1
  })
  return Object.entries(binCounts)
    .map(([bn, cnt]) => ({ bin_number: Number(bn), count: cnt }))
    .sort((a, b) => a.bin_number - b.bin_number)
}

function toggleHighlight(idx: number, binNum: number) {
  selectedBins.value[idx] = selectedBins.value[idx] === binNum ? null : binNum
  drawMap(idx)
}

function drawMap(idx: number) {
  const canvas = canvasRefs[idx]
  const mapItem = mapDataList.value[idx]
  if (!canvas || !mapItem?.has_map || !mapItem.data.length) return

  const ctx = canvas.getContext('2d')
  if (!ctx) return

  const data = mapItem.data
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
  for (const d of data) {
    if (d.x < minX) minX = d.x; if (d.x > maxX) maxX = d.x
    if (d.y < minY) minY = d.y; if (d.y > maxY) maxY = d.y
  }

  const W = canvas.width, H = canvas.height, margin = 24
  const gridW = maxX - minX + 1, gridH = maxY - minY + 1
  const cellSize = Math.max(1, Math.min((W - margin * 2) / gridW, (H - margin * 2) / gridH) - 1)
  const mapWidth = gridW * (cellSize + 1)
  const mapHeight = gridH * (cellSize + 1)
  const offsetX = (W - mapWidth) / 2
  const offsetY = (H - mapHeight) / 2

  ctx.clearRect(0, 0, W, H)

  const highlight = selectedBins.value[idx] ?? null
  const coordSet = new Set(data.map((d: any) => `${d.x},${d.y}`))
  const isEdge = (x: number, y: number) =>
    !coordSet.has(`${x-1},${y}`) || !coordSet.has(`${x+1},${y}`) ||
    !coordSet.has(`${x},${y-1}`) || !coordSet.has(`${x},${y+1}`)

  for (const d of data) {
    const px = offsetX + (d.x - minX) * (cellSize + 1)
    const py = offsetY + (d.y - minY) * (cellSize + 1)

    let color: string
    if (highlight !== null) {
      if (d.bin === highlight) color = getBinColor(d.bin)
      else if (isEdge(d.x, d.y)) color = 'rgba(200,200,200,0.25)'
      else continue
    } else {
      color = getBinColor(d.bin)
    }
    ctx.fillStyle = color
    ctx.fillRect(px, py, cellSize, cellSize)
  }

  // 坐标标注
  ctx.fillStyle = '#aaa'
  ctx.font = `${Math.max(8, Math.min(11, cellSize))}px sans-serif`
  ctx.textAlign = 'center'
  const xStep = Math.ceil(gridW / 10) || 1
  for (let x = minX; x <= maxX; x += xStep) {
    ctx.fillText(String(x), offsetX + (x - minX) * (cellSize + 1) + cellSize / 2, offsetY - 6)
  }
  ctx.textAlign = 'right'
  const yStep = Math.ceil(gridH / 10) || 1
  for (let y = minY; y <= maxY; y += yStep) {
    ctx.fillText(String(y), offsetX - 6, offsetY + (y - minY) * (cellSize + 1) + cellSize / 2 + 4)
  }
}

async function fetchAll() {
  loading.value = true
  try {
    const [binRes, mapRes]: any[] = await Promise.all([
      api.get('/analysis/multi/bin_summary', { params: { lot_ids: lotIdsStr, data_range: dataRange.value } }),
      api.get('/analysis/multi/wafer_bin_maps', { params: { lot_ids: lotIdsStr, data_range: dataRange.value } }),
    ])
    lots.value = binRes.lots
    bins.value = binRes.bins
    mapDataList.value = mapRes.maps

    // 初始化 selectedBins
    mapRes.maps.forEach((_: any, i: number) => {
      if (selectedBins.value[i] === undefined) selectedBins.value[i] = null
    })

    await nextTick()
    mapDataList.value.forEach((_, i) => drawMap(i))
  } finally {
    loading.value = false
  }
}

onMounted(fetchAll)
</script>

<style scoped>
.multi-bin-view {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  background: #f0f2f5;
  min-height: 100%;
}

.options-bar {
  background: white;
  padding: 8px 16px;
  border-radius: 6px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  display: flex;
  align-items: center;
  gap: 20px;
  font-size: 12px;
  flex-shrink: 0;
}

.opt-group { display: flex; align-items: center; gap: 8px; }
.opt-label { color: #666; font-weight: 500; }

.table-wrap {
  background: white;
  border-radius: 6px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  overflow-x: auto;
}

.bin-table { border-collapse: collapse; font-size: 12px; white-space: nowrap; }
.bin-table th, .bin-table td {
  border: 1px solid #f0f0f0;
  padding: 5px 12px;
  text-align: center;
  min-width: 60px;
}
.bin-table th { background: #fafafa; color: #555; }
.lot-header {
  background: #e6f7ff !important;
  color: #1890ff !important;
  font-weight: 600;
  border-bottom: 2px solid #91d5ff !important;
}
.pass-row { background: #f6ffed; }
.summary-row { background: #fafafa; font-weight: 500; }

.maps-section {
  background: white;
  border-radius: 6px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  padding: 12px;
}

.section-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 10px;
  text-align: center;
}

.maps-row {
  display: flex;
  gap: 20px;
  overflow-x: auto;
  align-items: flex-start;
}

.map-block {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.map-label {
  font-size: 12px;
  font-weight: 600;
  color: #333;
  text-align: center;
}

.map-with-legend {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.bin-legend {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 500px;
  overflow-y: auto;
}

.bin-icon {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 2px 6px;
  border-radius: 3px;
  cursor: pointer;
  font-size: 12px;
  white-space: nowrap;
  border: 1px solid transparent;
}
.bin-icon:hover { background: #f5f5f5; }
.bin-icon.selected { background: #e6f7ff; border-color: #91d5ff; }

.bin-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.loading {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
  color: #999;
  font-size: 14px;
}
</style>
