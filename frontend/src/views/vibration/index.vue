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
      <label v-for="field in filterFields" :key="field.key" class="filter-item">
        <span>{{ field.label }}</span>
        <input v-model="filters[field.key]" :placeholder="`按${field.label}检索`" />
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

type Row = Record<string, string | number | null>
type StatCard = { label: string; value: number }

const ENDPOINT = '/api/vibration'
const columns = ["监测编号", "监测部位", "所属机组", "振动速度", "报警阈值", "采集时间", "频谱特征", "监测状态"]
const actions = ["开始采集", "登记振动超标", "发起复测"]
const statuses = ["待采集", "数据正常", "振动超标", "已复测"]
// 统计卡片不再写死：标签与口径都由服务端按采集列表算好下发。
const stats = ref<StatCard[]>([
  { label: "待采集记录", value: 0 },
  { label: "振动超标项数", value: 0 },
  { label: "本月复测数", value: 0 },
])

// 页面只负责把筛选条件交给服务端，结论（含监测状态、超标与否）一律以服务端台账为准，
// 前端不再拿报警阈值自行判一遍，避免两个出口说法打架。
const filterFields = [
  { key: 'keyword', label: '监测编号' },
  { key: 'part', label: '监测部位' },
  { key: 'turbine', label: '所属机组' },
] as const

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})

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

async function reload() {
  errorMessage.value = ''
  const params = new URLSearchParams()
  for (const field of filterFields) {
    const value = filters.value[field.key]?.trim()
    if (value) {
      params.set(field.key, value)
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
    if (Array.isArray(payload.stats) && payload.stats.length) {
      stats.value = payload.stats as StatCard[]
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '振动监测列表读取失败'
  }
}

onMounted(reload)
</script>
