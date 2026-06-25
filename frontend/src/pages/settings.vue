<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import AppLayout from '../components/AppLayout.vue'
import { fetchL3Params, updateL3Params, type L3Params } from '../api/client'

const loading = ref(true)
const saving = ref(false)
const params = ref<L3Params>({} as L3Params)

const groups = [
  {
    title: '维度划分',
    fields: [
      { key: 'arm_joint_count', label: '预设机械臂关节数（自动检测失败时fallback）', step: 1, min: 1, max: 30 },
    ]
  },
  {
    title: '无效动作占比 (Dead Actions)',
    fields: [
      { key: 'eps_arm', label: 'ε_arm (rad)', step: 0.001, min: 0, max: 1 },
      { key: 'eps_hand', label: 'ε_hand (归一化后)', step: 0.001, min: 0, max: 1 },
      { key: 'dead_good', label: 'good 阈值 (<)', step: 0.01, min: 0, max: 1 },
      { key: 'dead_warn', label: 'warn 阈值 (<)', step: 0.01, min: 0, max: 1 },
    ]
  },
  {
    title: '动作饱和率 (Action Saturation)',
    fields: [
      { key: 'sat_margin', label: '饱和 margin（归一化比例）', step: 0.01, min: 0, max: 1 },
      { key: 'sat_hand_low', label: '手部低饱和边界 (0-255)', step: 1, min: 0, max: 128 },
      { key: 'sat_hand_high', label: '手部高饱和边界 (0-255)', step: 1, min: 127, max: 255 },
      { key: 'sat_good', label: 'good 阈值 (<)', step: 0.01, min: 0, max: 1 },
      { key: 'sat_warn', label: 'warn 阈值 (<)', step: 0.01, min: 0, max: 1 },
    ]
  },
  {
    title: '停滞检测 (Static Detection)',
    fields: [
      { key: 'static_window_s', label: '滑动窗口 (秒)', step: 0.1, min: 0.1, max: 5 },
      { key: 'static_arm_vel', label: 'arm 速度阈值 (rad/s)', step: 0.001, min: 0, max: 1 },
      { key: 'static_arm_act', label: 'arm 动作阈值 (rad)', step: 0.001, min: 0, max: 1 },
      { key: 'static_hand_act', label: 'hand 动作阈值 (归一化)', step: 0.001, min: 0, max: 1 },
      { key: 'static_good', label: 'good 阈值 (<)', step: 0.01, min: 0, max: 1 },
      { key: 'static_warn', label: 'warn 阈值 (<)', step: 0.01, min: 0, max: 1 },
    ]
  },
  {
    title: '时间戳抖动 (Timestamp Jitter)',
    fields: [
      { key: 'jitter_good', label: 'good 阈值 (<)', step: 0.01, min: 0, max: 1 },
      { key: 'jitter_warn', label: 'warn 阈值 (<)', step: 0.01, min: 0, max: 1 },
    ]
  },
  {
    title: '跟踪误差 (Tracking Error)',
    fields: [
      { key: 'tracking_arm_weight', label: 'arm 权重', step: 0.1, min: 0, max: 1 },
      { key: 'tracking_hand_weight', label: 'hand 权重', step: 0.1, min: 0, max: 1 },
      { key: 'tracking_good', label: 'good 阈值 (<)', step: 0.01, min: 0, max: 1 },
      { key: 'tracking_warn', label: 'warn 阈值 (<)', step: 0.01, min: 0, max: 1 },
    ]
  },
  {
    title: '平滑度 (LDLJ)',
    fields: [
      { key: 'ldlj_good', label: 'good 阈值 (>=)', step: 0.1, min: 0, max: 10 },
      { key: 'ldlj_warn', label: 'warn 阈值 (>=)', step: 0.1, min: 0, max: 10 },
    ]
  },
  {
    title: '手指颤振 (Finger Chatter)',
    fields: [
      { key: 'chatter_threshold', label: '翻转判定阈值 (/s)', step: 0.1, min: 0, max: 20 },
      { key: 'chatter_good', label: 'good 阈值 (<)', step: 0.1, min: 0, max: 20 },
      { key: 'chatter_warn', label: 'warn 阈值 (<)', step: 0.1, min: 0, max: 20 },
    ]
  },
  {
    title: '执行力度 (Joint Effort)',
    fields: [
      { key: 'effort_good', label: 'good 阈值 (<)', step: 0.1, min: 0, max: 10 },
      { key: 'effort_warn', label: 'warn 阈值 (<)', step: 0.1, min: 0, max: 10 },
    ]
  },
  {
    title: 'Timeline 生成',
    fields: [
      { key: 'timeline_min_dur', label: '最小持续时长 (秒)', step: 0.1, min: 0, max: 10 },
      { key: 'timeline_gap_merge', label: '段合并间隔 (秒)', step: 0.1, min: 0, max: 10 },
      { key: 'sync_bad_threshold_ms', label: '同步异常阈值 (ms)', step: 50, min: 0, max: 5000 },
    ]
  },
]

function getLabel(key: string) {
  for (const g of groups) {
    for (const f of g.fields) {
      if (f.key === key) return f.label
    }
  }
  return key
}

async function load() {
  loading.value = true
  try {
    params.value = await fetchL3Params()
  } catch (e) {
    ElMessage.error('加载 L3 参数失败')
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  try {
    await updateL3Params(params.value)
    ElMessage.success('L3 超参数已保存')
  } catch (e) {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <AppLayout>
    <div class="l3-settings" v-loading="loading">
      <div class="settings-header">
        <h1>L3 指标超参数配置</h1>
        <el-button type="primary" :loading="saving" @click="save">保存全部</el-button>
      </div>
      <el-alert type="info" :closable="false" style="margin-bottom: 20px">
        修改后立即生效，下次加载 manual QC 时自动使用新参数。参数值为空时将回退到系统默认值。
      </el-alert>

      <el-card v-for="group in groups" :key="group.title" shadow="never" class="qc-card" style="margin-bottom: 16px">
        <template #header><strong>{{ group.title }}</strong></template>
        <el-row :gutter="20">
          <el-col :span="8" v-for="field in group.fields" :key="field.key" style="margin-bottom: 12px">
            <div class="field-label">{{ field.label }}</div>
            <el-input-number
              v-model="(params as any)[field.key]"
              :step="field.step"
              :min="field.min"
              :max="field.max"
              :precision="field.step < 0.01 ? 4 : field.step < 0.1 ? 3 : field.step < 1 ? 2 : 0"
              controls-position="right"
              style="width: 100%"
            />
          </el-col>
        </el-row>
      </el-card>
    </div>
  </AppLayout>
</template>

<style scoped>
.l3-settings {
  max-width: 1100px;
  margin: 0 auto;
  padding: 20px;
}

.settings-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.settings-header h1 {
  margin: 0;
  font-size: 22px;
}

.field-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
