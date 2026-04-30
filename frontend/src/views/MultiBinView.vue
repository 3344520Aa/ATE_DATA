<template>
  <div class="multi-bin-view">
    <!-- Options栏 -->
    <div class="options-bar">
      <div class="opt-group">
        <span class="opt-label">DataRange</span>
        <label><input type="radio" v-model="dataRange" value="final" @change="fetchAll" /> Final</label>
        <label><input type="radio" v-model="dataRange" value="original" @change="fetchAll" /> Original</label>
      </div>
      <button class="export-btn" @click="handleExport">📁 导出 Excel</button>
    </div>

    <!-- Bin汇总表 -->
    <div class="table-wrap" v-if="bins.length">
      <table class="bin-table">
        <thead>
          <!-- 第一行：LOT名 colspan=2 -->
          <tr>
            <th rowspan="2" class="chk-col"></th>
            <th rowspan="2">Bin</th>
            <th rowspan="2">Name</th>
            <th colspan="2" class="lot-header">Total</th>
            <th
              v-for="lot in lots"
              :key="lot.id"
              colspan="2"
              class="lot-header"
            >{{ lot.wafer_id || lot.lot_id || lot.filename }}</th>
          </tr>
          <!-- 第二行：Count / % -->
          <tr>
            <th>Count</th>
            <th>%</th>
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
            :class="{ 'pass-row': isPassBin(b.bin_number), 'active-filter-row': globalBinFilter === b.bin_number }"
          >
            <td class="chk-col">
              <input
                type="checkbox"
                :checked="globalBinFilter === b.bin_number"
                @change="setGlobalBinFilter(b.bin_number)"
                class="bin-checkbox"
              />
            </td>
            <td>{{ b.bin_number }}</td>
            <td>{{ b.bin_name }}</td>
            <td>{{ getBinTotalCount(b) }}</td>
            <td>{{ getBinTotalPct(b) }}%</td>
            <template v-for="lot in lots" :key="lot.id">
              <td>{{ b.lots[String(lot.id)]?.count ?? 0 }}</td>
              <td>{{ (b.lots[String(lot.id)]?.pct ?? 0).toFixed(2) }}%</td>
            </template>
          </tr>
        </tbody>
        <tfoot>
          <tr class="summary-row" :class="{ 'active-filter-row': globalBinFilter === null }">
            <td class="chk-col">
              <input
                type="checkbox"
                :checked="globalBinFilter === null"
                @change="setGlobalBinFilter(null)"
                class="bin-checkbox"
              />
            </td>
            <td colspan="2">Total</td>
            <td>{{ getAllTotal() }}</td>
            <td>100%</td>
            <template v-for="lot in lots" :key="lot.id">
              <td>{{ getLotTotal(lot.id) }}</td>
              <td>100%</td>
            </template>
          </tr>
          <tr class="summary-row pass-row">
            <td class="chk-col"></td>
            <td colspan="2">Pass</td>
            <td>{{ getAllPass() }}</td>
            <td>{{ getAllTotal() > 0 ? (getAllPass() / getAllTotal() * 100).toFixed(2) + '%' : '-' }}</td>
            <template v-for="lot in lots" :key="lot.id">
              <td>{{ getLotPass(lot.id) }}</td>
              <td>{{ getLotTotal(lot.id) > 0 ? (getLotPass(lot.id) / getLotTotal(lot.id) * 100).toFixed(2) + '%' : '-' }}</td>
            </template>
          </tr>
          <tr class="summary-row">
            <td class="chk-col"></td>
            <td colspan="2">Fail</td>
            <td>{{ getAllFail() }}</td>
            <td>{{ getAllTotal() > 0 ? (getAllFail() / getAllTotal() * 100).toFixed(2) + '%' : '-' }}</td>
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
          <div class="map-label">{{ mapItem.wafer_id || mapItem.lot_id_str || mapItem.filename }}</div>
          <div class="map-with-legend">
            <canvas
              :ref="el => setCanvasRef(idx, el)"
              width="520"
              height="520"
              style="width:520px;height:520px;border:1px solid #eee"
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
import ExcelJS from 'exceljs'
import { saveAs } from 'file-saver'

const route = useRoute()
const lotIdsStr = route.query.lot_ids as string

const lots = ref<any[]>([])
const bins = ref<any[]>([])
const mapDataList = ref<any[]>([])
const loading = ref(true)
const dataRange = ref('final')
const passBins = ref<number[]>([1, 2])
const selectedBins = ref<Record<number, number | null>>({})
const globalBinFilter = ref<number | null>(null) // null = show all (Total)

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

function getBinTotalCount(b: any) {
  return lots.value.reduce((s, lot) => s + (b.lots[String(lot.id)]?.count ?? 0), 0)
}
function getBinTotalPct(b: any) {
  const total = getAllTotal()
  if (total === 0) return '0.00'
  return ((getBinTotalCount(b) / total) * 100).toFixed(2)
}
function getAllTotal() {
  return lots.value.reduce((s, lot) => s + getLotTotal(lot.id), 0)
}
function getAllPass() {
  return lots.value.reduce((s, lot) => s + getLotPass(lot.id), 0)
}
function getAllFail() {
  return getAllTotal() - getAllPass()
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

function setGlobalBinFilter(binNum: number | null) {
  globalBinFilter.value = binNum
  // Apply global filter to all maps
  mapDataList.value.forEach((mapItem, i) => {
    selectedBins.value[i] = binNum
    drawMap(i)
  })
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

  const coordSet = new Set(data.map((d: any) => `${d.x},${d.y}`))
  const isEdge = (x: number, y: number) =>
    !coordSet.has(`${x-1},${y}`) || !coordSet.has(`${x+1},${y}`) ||
    !coordSet.has(`${x},${y-1}`) || !coordSet.has(`${x},${y+1}`)

  const highlight = selectedBins.value[idx] ?? null

  // If a global bin filter is set and this map doesn't have that bin, show only outline
  if (highlight !== null) {
    const hasBin = data.some((d: any) => d.bin === highlight)
    if (!hasBin) {
      // Draw empty wafer outline only
      for (const d of data) {
        const px = offsetX + (d.x - minX) * (cellSize + 1)
        const py = offsetY + (d.y - minY) * (cellSize + 1)
        if (isEdge(d.x, d.y)) {
          ctx.fillStyle = 'rgba(200,200,200,0.25)'
          ctx.fillRect(px, py, cellSize, cellSize)
        }
      }
      // 坐标标注
      ctx.fillStyle = '#aaa'
      ctx.font = `${Math.max(8, Math.min(11, cellSize))}px sans-serif`
      ctx.textAlign = 'center'
      const xStep2 = Math.ceil(gridW / 10) || 1
      for (let x = minX; x <= maxX; x += xStep2) {
        ctx.fillText(String(x), offsetX + (x - minX) * (cellSize + 1) + cellSize / 2, offsetY - 6)
      }
      ctx.textAlign = 'right'
      const yStep2 = Math.ceil(gridH / 10) || 1
      for (let y = minY; y <= maxY; y += yStep2) {
        ctx.fillText(String(y), offsetX - 6, offsetY + (y - minY) * (cellSize + 1) + cellSize / 2 + 4)
      }
      return
    }
  }

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

async function handleExport() {
  if (!lots.value.length) return

  const workbook = new ExcelJS.Workbook()
  workbook.creator = 'Chip ATE System'
  const sheet = workbook.addWorksheet('Multi Bin Summary')

  // 1. 写表头
  const lotHeaders = lots.value.map(l => l.wafer_id || l.lot_id || l.filename)
  
  // 第一行：合并单元格
  const headerRow1 = sheet.addRow(['Bin', 'Name', 'Total', '', ...lotHeaders.flatMap(h => [h, ''])])
  sheet.mergeCells(1, 3, 1, 4) // Total
  lots.value.forEach((_, idx) => {
    sheet.mergeCells(1, 5 + idx * 2, 1, 6 + idx * 2)
  })
  
  // 第二行：Count / %
  const headerRow2 = sheet.addRow(['', '', 'Count', '%', ...lotHeaders.flatMap(() => ['Count', '%'])])
  
  // 样式
  ;[headerRow1, headerRow2].forEach(row => {
    row.font = { bold: true, color: { argb: 'FFFFFFFF' } }
    row.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FF808080' } }
    row.alignment = { horizontal: 'center', vertical: 'middle' }
  })
  
  sheet.mergeCells(1, 1, 2, 1) // Bin
  sheet.mergeCells(1, 2, 2, 2) // Name

  // 2. 写表格数据
  bins.value.forEach((b: any) => {
    const rowData = [
      b.bin_number,
      b.bin_name,
      getBinTotalCount(b),
      parseFloat(getBinTotalPct(b)) / 100
    ]
    lots.value.forEach(lot => {
      rowData.push(b.lots[String(lot.id)]?.count ?? 0)
      rowData.push((b.lots[String(lot.id)]?.pct ?? 0) / 100)
    })
    
    const row = sheet.addRow(rowData)
    row.alignment = { horizontal: 'center', vertical: 'middle' }
    row.getCell(2).alignment = { horizontal: 'left', vertical: 'middle' }
    if (isPassBin(b.bin_number)) {
      row.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFE6FFE6' } }
    }
  })

  // 写 Summary 行
  const totalRow = sheet.addRow(['Total', '', getAllTotal(), 1, ...lots.value.flatMap(lot => [getLotTotal(lot.id), 1])])
  const passRow = sheet.addRow(['Pass', '', getAllPass(), getAllTotal() > 0 ? getAllPass() / getAllTotal() : 0, ...lots.value.flatMap(lot => [getLotPass(lot.id), getLotTotal(lot.id) > 0 ? getLotPass(lot.id) / getLotTotal(lot.id) : 0])])
  const failRow = sheet.addRow(['Fail', '', getAllFail(), getAllTotal() > 0 ? getAllFail() / getAllTotal() : 0, ...lots.value.flatMap(lot => [getLotFail(lot.id), getLotTotal(lot.id) > 0 ? getLotFail(lot.id) / getLotTotal(lot.id) : 0])])
  
  sheet.mergeCells(sheet.rowCount - 2, 1, sheet.rowCount - 2, 2)
  sheet.mergeCells(sheet.rowCount - 1, 1, sheet.rowCount - 1, 2)
  sheet.mergeCells(sheet.rowCount, 1, sheet.rowCount, 2)

  ;[totalRow, passRow, failRow].forEach(row => {
    row.font = { bold: true }
    row.alignment = { horizontal: 'center', vertical: 'middle' }
  })
  passRow.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFE6FFE6' } }

  // 设置列宽
  sheet.getColumn(1).width = 10
  sheet.getColumn(2).width = 20
  for (let i = 3; i <= 4 + lots.value.length * 2; i++) {
    sheet.getColumn(i).width = 12
    if (i % 2 === 0) {
      sheet.getColumn(i).numFmt = '0.00%'
    }
  }

  // 3. 导出 Maps (每排4个)
  if (mapDataList.value.some(m => m.has_map)) {
    const validMaps = mapDataList.value.filter((m, i) => m.has_map && canvasRefs[i])
    if (validMaps.length > 0) {
      // 在表格下方留出空行
      let currentRow = sheet.rowCount + 3

      // 每行4个map
      for (let i = 0; i < validMaps.length; i += 4) {
        const rowMaps = validMaps.slice(i, i + 4)
        
        let maxCompositeHeight = 0
        const rowImages = []
        
        for (let j = 0; j < rowMaps.length; j++) {
          const mapItem = rowMaps[j]
          const originalIdx = mapDataList.value.indexOf(mapItem)
          const canvas = canvasRefs[originalIdx]
          if (!canvas) continue

          const mapWidth = canvas.width
          const mapHeight = canvas.height
          const legendWidth = 160
          
          const compositeWidth = mapWidth + legendWidth
          
          // 获取当前图例需要绘制的 Bin (按顺序，或者只绘制该wafer有的)
          const visibleBins = getMapBins(mapItem)
          const legendHeight = visibleBins.length * 20 + 40
          const compositeHeight = Math.max(mapHeight, legendHeight)
          if (compositeHeight > maxCompositeHeight) maxCompositeHeight = compositeHeight
          
          const offCanvas = document.createElement('canvas')
          offCanvas.width = compositeWidth
          offCanvas.height = compositeHeight
          const ctx = offCanvas.getContext('2d')
          
          if (ctx) {
            ctx.fillStyle = '#ffffff'
            ctx.fillRect(0, 0, compositeWidth, compositeHeight)
            
            // 绘制标题
            ctx.fillStyle = '#333'
            ctx.font = 'bold 16px sans-serif'
            ctx.textAlign = 'center'
            ctx.fillText(mapItem.wafer_id || mapItem.lot_id_str || mapItem.filename, mapWidth / 2, 20)

            // 画地图 (略微下移给标题留空间)
            ctx.drawImage(canvas, 0, 30)

            // 画图例
            const startX = mapWidth + 10
            let startY = 40
            ctx.font = '14px sans-serif'
            ctx.textAlign = 'left'
            ctx.textBaseline = 'middle'
            
            ctx.beginPath()
            ctx.arc(startX + 6, startY, 5, 0, 2 * Math.PI)
            ctx.fillStyle = '#aaa'
            ctx.fill()
            ctx.fillStyle = '#333'
            ctx.fillText(`ALL`, startX + 16, startY)
            startY += 24

            visibleBins.forEach(b => {
              const color = getBinColor(b.bin_number)
              ctx.beginPath()
              ctx.arc(startX + 6, startY, 5, 0, 2 * Math.PI)
              ctx.fillStyle = color
              ctx.fill()
              ctx.fillStyle = '#333'
              ctx.fillText(`Bin${b.bin_number}(${b.count})`, startX + 16, startY)
              startY += 24
            })
            
            const mapDataUrl = offCanvas.toDataURL('image/png')
            const imageId = workbook.addImage({
              base64: mapDataUrl,
              extension: 'png',
            })
            rowImages.push({ imageId, width: compositeWidth, height: compositeHeight })
          }
        }
        
        // 将这行的图片插入到 Excel
        // 这里可以通过 scale 控制缩放大小，并动态计算占用的列数使其紧挨着显示
        let currentCol = 0
        const scale = 1.3 // 控制导出的 Map 图片缩放比例为 130%
        for (let j = 0; j < rowImages.length; j++) {
          const img = rowImages[j]
          sheet.addImage(img.imageId, {
            tl: { col: currentCol, row: currentRow },
            ext: { width: img.width * scale, height: img.height * scale } // 缩放图片
          })
          // 计算当前图片按比例放大后占据多少列 (默认一列宽度约70px)，以此得出下一张图起始列
          currentCol += Math.ceil((img.width * scale) / 100) 
        }
        
        // 换行计算：根据放大后高度占据多少行 (每行大约20px高)
        currentRow += Math.ceil((maxCompositeHeight * scale) / 20) + 2
      }
    }
  }

  // 4. 导出文件
  const buffer = await workbook.xlsx.writeBuffer()
  const blob = new Blob([buffer], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
  saveAs(blob, `MultiBinReport_${new Date().getTime()}.xlsx`)
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
  height: 100%;
  overflow-y: auto;
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

.export-btn {
  margin-left: 10px;
  background: #52c41a;
  color: white;
  border: none;
  border-radius: 4px;
  padding: 6px 16px;
  cursor: pointer;
  font-size: 13px;
}
.export-btn:hover { background: #73d13d; }

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
.bin-table tbody tr:hover td { background-color: #e6f7ff !important; }

.chk-col {
  width: 32px !important;
  min-width: 32px !important;
  max-width: 32px !important;
  padding: 2px 4px !important;
}

.bin-checkbox {
  width: 15px;
  height: 15px;
  cursor: pointer;
  accent-color: #1890ff;
}

.active-filter-row td {
  background-color: #bae7ff !important;
  font-weight: 600;
}

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
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 5px;
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
  max-height: 520px;
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
