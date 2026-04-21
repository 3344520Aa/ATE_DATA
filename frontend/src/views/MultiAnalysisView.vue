<template>
  <div class="multi-analysis-view">
    <!-- 顶部LOT信息栏 -->
    <div class="lot-info-bar">
      <div class="info-grid">
        <div class="info-item" v-for="lot in lots" :key="lot.id">
          <span class="label">LOT</span>
          <span class="value">{{ lot.filename }}</span>
        </div>
      </div>
    </div>

    <!-- Options栏 -->
    <div class="options-bar">
      <div class="opt-item">
        <label>CPK &lt;</label>
        <input v-model.number="cpkFilter" type="number" step="0.1" placeholder="不过滤" style="width:80px" />
      </div>
      <button class="btn-submit" @click="applyFilter">应用</button>
    </div>

    <!-- 两级表头参数表格 -->
    <div class="table-wrap" v-if="params.length">
      <table class="param-table">
        <thead>
          <!-- 第一行：LOT名 colspan -->
          <tr>
            <th rowspan="2" style="min-width:50px">#</th>
            <th rowspan="2" style="min-width:200px">TestItem</th>
            <th rowspan="2" style="min-width:60px">Units</th>
            <th rowspan="2" style="min-width:90px">L.Limit</th>
            <th rowspan="2" style="min-width:90px">U.Limit</th>
            <th
              v-for="lot in lots"
              :key="lot.id"
              :colspan="5"
              class="lot-header"
            >{{ lot.filename }}</th>
          </tr>
          <!-- 第二行：指标名 -->
          <tr>
            <template v-for="lot in lots" :key="lot.id">
              <th>Mean</th>
              <th>Stdev</th>
              <th>Min</th>
              <th>Max</th>
              <th>CPK</th>
            </template>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="p in filteredParams"
            :key="p.item_name"
            class="param-row"
            @click="openParam(p)"
          >
            <td>{{ p.item_number }}</td>
            <td class="item-name-cell">{{ p.item_name }}</td>
            <td>{{ p.unit }}</td>
            <td>{{ p.lower_limit ?? '-' }}</td>
            <td>{{ p.upper_limit ?? '-' }}</td>
            <template v-for="lot in lots" :key="lot.id">
              <td>{{ fmtNum(p.lots[String(lot.id)]?.mean) }}</td>
              <td>{{ fmtNum(p.lots[String(lot.id)]?.stdev) }}</td>
              <td>{{ fmtNum(p.lots[String(lot.id)]?.min_val) }}</td>
              <td>{{ fmtNum(p.lots[String(lot.id)]?.max_val) }}</td>
              <td :style="cpkStyle(p.lots[String(lot.id)]?.cpk)">
                {{ fmtNum(p.lots[String(lot.id)]?.cpk) }}
              </td>
            </template>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-else-if="loading" class="loading">加载中...</div>
    <div v-else class="loading">暂无数据</div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '@/api'

const route = useRoute()
const router = useRouter()
const lotIdsStr = route.query.lot_ids as string

const lots = ref<any[]>([])
const params = ref<any[]>([])
const loading = ref(true)
const cpkFilter = ref<number | null>(null)

const filteredParams = computed(() => {
  if (cpkFilter.value === null || cpkFilter.value === undefined) return params.value
  return params.value.filter(p => {
    // 任意一个LOT的CPK低于阈值则显示
    return lots.value.some(lot => {
      const cpk = p.lots[String(lot.id)]?.cpk
      return cpk === null || cpk === undefined || cpk < cpkFilter.value!
    })
  })
})

function applyFilter() {
  // computed 自动响应，无需额外操作
}

async function fetchData() {
  loading.value = true
  try {
    const data: any = await api.get('/analysis/multi/items', {
      params: { lot_ids: lotIdsStr }
    })
    lots.value = data.lots
    params.value = data.params
  } finally {
    loading.value = false
  }
}

function openParam(p: any) {
  const url = router.resolve(
    `/multi-param?lot_ids=${lotIdsStr}&param_name=${encodeURIComponent(p.item_name)}`
  ).href
  window.open(url, '_blank')
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

onMounted(fetchData)
</script>

<style scoped>
.multi-analysis-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  background: #f0f2f5;
  overflow: hidden;
}

.lot-info-bar {
  background: white;
  padding: 10px 16px;
  border-radius: 6px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  flex-shrink: 0;
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
  gap: 12px;
  flex-shrink: 0;
  font-size: 12px;
}

.opt-item { display: flex; align-items: center; gap: 6px; }
.opt-item label { color: #666; }
.opt-item input {
  padding: 3px 6px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  font-size: 12px;
}

.btn-submit {
  background: #1890ff;
  color: white;
  border: none;
  border-radius: 4px;
  padding: 5px 14px;
  cursor: pointer;
  font-size: 12px;
}
.btn-submit:hover { background: #40a9ff; }

.table-wrap {
  flex: 1;
  background: white;
  border-radius: 6px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  overflow: auto;
}

.param-table {
  border-collapse: collapse;
  font-size: 12px;
  white-space: nowrap;
}

.param-table th, .param-table td {
  border: 1px solid #f0f0f0;
  padding: 5px 10px;
  text-align: center;
}

.param-table thead th {
  background: #fafafa;
  color: #555;
  position: sticky;
  top: 0;
  z-index: 2;
}

.lot-header {
  background: #e6f7ff !important;
  color: #1890ff !important;
  font-weight: 600;
  border-bottom: 2px solid #91d5ff !important;
}

.param-row {
  cursor: pointer;
  transition: background 0.1s;
}
.param-row:hover { background: #e6f7ff; }

.item-name-cell {
  color: #1890ff;
  text-align: left;
  font-weight: 500;
}

.loading {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #999;
  font-size: 14px;
}
</style>
