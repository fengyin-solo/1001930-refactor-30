<template>
  <section class="page" data-module="vibration">
    <header class="page-head">
      <div>
        <h2>振动监测管理</h2>
        <p class="page-desc">维护振动监测记录，围绕监测编号、监测部位、所属机组、振动速度做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记振动监测记录</button>
        <button class="btn" type="button" @click="exportRows">导出振动监测清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无振动监测数据，可先登记振动监测记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条振动监测记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>
type StatCard = { label: string; value: number }

const ENDPOINT = '/api/vibration'
const columns = ["监测编号", "监测部位", "所属机组", "振动速度", "报警阈值", "采集时间", "频谱特征", "监测状态"]
const actions = ["开始采集", "登记振动超标", "发起复测"]
// 监测状态、异常结论只认服务端台账，页面不再拿振动速度和报警阈值自行比较
const DEFAULT_STATS: StatCard[] = [
  { label: "待采集记录", value: 0 },
  { label: "振动超标项数", value: 0 },
  { label: "本月复测数", value: 0 },
]
// 页面筛选项与后端查询参数一一对应，避免另起一套过滤口径
const FILTER_PARAMS: Record<string, string> = {
  "监测编号": "keyword",
  "监测部位": "part",
  "所属机组": "turbine",
}

const rows = ref<Row[]>([])
const total = ref(0)
const stats = ref<StatCard[]>(DEFAULT_STATS)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '振动监测记录登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('振动监测动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '振动监测操作失败'
  }
}

// 兜底统计：仅当后端未随列表下发卡片时，用当前采集列表的台账状态汇总，
// 不做任何振动速度/报警阈值比较，结论仍与列表一致。
function statsFromList(items: Row[]): StatCard[] {
  const monthPrefix = new Date().toISOString().slice(0, 7)
  return [
    { label: DEFAULT_STATS[0].label, value: items.filter((row) => row.status === '待采集').length },
    { label: DEFAULT_STATS[1].label, value: items.filter((row) => row.abnormal === true).length },
    {
      label: DEFAULT_STATS[2].label,
      value: items.filter(
        (row) => row.status === '已复测' && String(row['采集时间'] ?? '').startsWith(monthPrefix),
      ).length,
    },
  ]
}

async function reload() {
  errorMessage.value = ''
  const params = new URLSearchParams()
  for (const [field, value] of Object.entries(filters.value)) {
    const trimmed = value.trim()
    if (trimmed) {
      params.set(FILTER_PARAMS[field] ?? field, trimmed)
    }
  }
  try {
    const response = await request(`${ENDPOINT}?${params.toString()}`)
    if (!response.ok) {
      throw new Error('振动监测记录列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    // 统计数字直接用后端随列表给出的同一份结果，不再写死
    stats.value = Array.isArray(payload.stats) && payload.stats.length
      ? payload.stats
      : statsFromList(rows.value)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '振动监测列表读取失败'
  }
}

onMounted(reload)
</script>
