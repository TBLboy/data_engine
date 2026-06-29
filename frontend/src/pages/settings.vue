<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import AppLayout from '../components/AppLayout.vue'
import { fetchL3V2Params, updateL3V2Params, type L3V2Params } from '../api/client'

const loading = ref(true)
const saving = ref(false)
const params = ref<L3V2Params>({})

const groups = [
  {
    title: '动作示范质量 — 轨迹平滑度 (MQ-01)',
    desc: '机械臂关节位置三阶差分 P95',
    fields: [
      { key: 'mq01_good', label: 'good 阈值 (<)', step: 0.001, min: 0, max: 1 },
      { key: 'mq01_warn', label: 'warn 阈值 (<)', step: 0.001, min: 0, max: 1 },
      { key: 'mq01_bad', label: 'bad 阈值 (>=)', step: 0.001, min: 0, max: 1 },
      { key: 'mq01_weight', label: '指标权重', step: 0.01, min: 0, max: 1 },
      { key: 'mq01_spike_p98_floor', label: 'Spike Floor (P98 最小)', step: 0.001, min: 0, max: 1 },
    ]
  },
  {
    title: '动作示范质量 — 动作连续性 (MQ-02)',
    desc: 'Action 二阶差分 P95',
    fields: [
      { key: 'mq02_good', label: 'good 阈值 (<)', step: 0.001, min: 0, max: 1 },
      { key: 'mq02_warn', label: 'warn 阈值 (<)', step: 0.001, min: 0, max: 1 },
      { key: 'mq02_bad', label: 'bad 阈值 (>=)', step: 0.001, min: 0, max: 1 },
      { key: 'mq02_weight', label: '指标权重', step: 0.01, min: 0, max: 1 },
      { key: 'mq02_threshold_floor', label: 'Threshold Floor', step: 0.01, min: 0, max: 1 },
    ]
  },
  {
    title: '动作示范质量 — 运动稳定性 (MQ-03)',
    desc: '振荡比例 (arm) + 颤振比例 (hand)',
    fields: [
      { key: 'mq03_osc_threshold', label: 'Osc 判定阈值', step: 0.01, min: 0, max: 1 },
      { key: 'mq03_chat_threshold', label: 'Chat 判定阈值', step: 0.01, min: 0, max: 1 },
      { key: 'mq03_osc_weight', label: 'Osc 融合权重', step: 0.1, min: 0, max: 1 },
      { key: 'mq03_chat_weight', label: 'Chat 融合权重', step: 0.1, min: 0, max: 1 },
      { key: 'mq03_good', label: 'good 阈值 (<)', step: 0.01, min: 0, max: 1 },
      { key: 'mq03_warn', label: 'warn 阈值 (<)', step: 0.01, min: 0, max: 1 },
      { key: 'mq03_bad', label: 'bad 阈值 (>=)', step: 0.01, min: 0, max: 1 },
      { key: 'mq03_weight', label: '指标权重', step: 0.01, min: 0, max: 1 },
    ]
  },
  {
    title: '可学习性 — 有效动作比 (LQ-01)',
    desc: 'arm/hand OR 融合有效帧占比',
    fields: [
      { key: 'lq01_eps_arm', label: 'ε_arm (rad)', step: 0.001, min: 0, max: 0.1 },
      { key: 'lq01_eps_hand', label: 'ε_hand (归一化)', step: 0.001, min: 0, max: 0.1 },
      { key: 'lq01_good', label: 'good 阈值 (>=)', step: 0.01, min: 0, max: 1 },
      { key: 'lq01_warn', label: 'warn 阈值 (>=)', step: 0.01, min: 0, max: 1 },
      { key: 'lq01_bad', label: 'bad 阈值 (<=)', step: 0.01, min: 0, max: 1 },
      { key: 'lq01_weight', label: '指标权重', step: 0.01, min: 0, max: 1 },
      { key: 'lq01_min_dur', label: 'TL 最小持续 (秒)', step: 0.1, min: 0, max: 10 },
      { key: 'lq01_gap_merge', label: 'TL 段合并 (秒)', step: 0.1, min: 0, max: 5 },
    ]
  },
  {
    title: '可学习性 — 信息密度 (LQ-02)',
    desc: 'Coverage × Intensity 模型',
    fields: [
      { key: 'lq02_eps_arm', label: 'ε_arm (rad)', step: 0.001, min: 0, max: 0.1 },
      { key: 'lq02_eps_hand', label: 'ε_hand (归一化)', step: 0.001, min: 0, max: 0.1 },
      { key: 'lq02_coverage_weight', label: '覆盖率权重', step: 0.1, min: 0, max: 1 },
      { key: 'lq02_state_weight', label: '状态强度权重', step: 0.1, min: 0, max: 1 },
      { key: 'lq02_good', label: 'good 阈值 (>=)', step: 0.001, min: 0, max: 1 },
      { key: 'lq02_warn', label: 'warn 阈值 (>=)', step: 0.001, min: 0, max: 1 },
      { key: 'lq02_bad', label: 'bad 阈值 (<=)', step: 0.001, min: 0, max: 1 },
      { key: 'lq02_weight', label: '指标权重', step: 0.01, min: 0, max: 1 },
    ]
  },
  {
    title: '可学习性 — 低价值片段 (LQ-03)',
    desc: '长时间低变化片段占比 (segment-level)',
    fields: [
      { key: 'lq03_eps_arm', label: 'ε_arm (rad)', step: 0.001, min: 0, max: 0.1 },
      { key: 'lq03_eps_hand', label: 'ε_hand (归一化)', step: 0.001, min: 0, max: 0.1 },
      { key: 'lq03_tau_q_floor', label: 'τ_q 下限', step: 0.0001, min: 0, max: 0.01 },
      { key: 'lq03_min_seg_dur', label: '最小段长 (秒)', step: 0.1, min: 0, max: 10 },
      { key: 'lq03_good', label: 'good 阈值 (<)', step: 0.01, min: 0, max: 1 },
      { key: 'lq03_warn', label: 'warn 阈值 (<)', step: 0.01, min: 0, max: 1 },
      { key: 'lq03_bad', label: 'bad 阈值 (>=)', step: 0.01, min: 0, max: 1 },
      { key: 'lq03_weight', label: '指标权重', step: 0.01, min: 0, max: 1 },
    ]
  },
  {
    title: '数据完整性 — 时间戳规则性 (DI-01)',
    desc: 'J_95 + R_gap + R_invalid',
    fields: [
      { key: 'di01_jitter_weight', label: 'Jitter 权重', step: 0.1, min: 0, max: 1 },
      { key: 'di01_gap_weight', label: 'Gap 权重', step: 0.1, min: 0, max: 1 },
      { key: 'di01_invalid_weight', label: 'Invalid 权重', step: 0.1, min: 0, max: 1 },
      { key: 'di01_gap_multiplier', label: 'Gap 倍数 (×dt_med)', step: 0.5, min: 1, max: 10 },
      { key: 'di01_good', label: 'good 阈值 (<)', step: 0.01, min: 0, max: 1 },
      { key: 'di01_warn', label: 'warn 阈值 (<)', step: 0.01, min: 0, max: 1 },
      { key: 'di01_bad', label: 'bad 阈值 (>=)', step: 0.01, min: 0, max: 1 },
      { key: 'di01_weight', label: '指标权重', step: 0.01, min: 0, max: 1 },
    ]
  },
  {
    title: '数据完整性 — 同步有效性 (DI-02)',
    desc: '自适应同步检测：R_flag+R_hard+R_soft+M_sync+R_seg',
    fields: [
      { key: 'di02_tau_warn_mult', label: 'Warn τ 倍数 (×dt_med)', step: 0.5, min: 1, max: 10 },
      { key: 'di02_tau_warn_floor', label: 'Warn τ 下限 (秒)', step: 0.01, min: 0, max: 1 },
      { key: 'di02_tau_bad_mult', label: 'Bad τ 倍数 (×dt_med)', step: 0.5, min: 1, max: 20 },
      { key: 'di02_tau_bad_floor', label: 'Bad τ 下限 (秒)', step: 0.01, min: 0, max: 1 },
      { key: 'di02_w_flag', label: 'Flag 权重', step: 0.05, min: 0, max: 1 },
      { key: 'di02_w_hard', label: 'Hard 权重', step: 0.05, min: 0, max: 1 },
      { key: 'di02_w_soft', label: 'Soft 权重', step: 0.05, min: 0, max: 1 },
      { key: 'di02_w_sync', label: 'M_sync 权重', step: 0.05, min: 0, max: 1 },
      { key: 'di02_w_seg', label: 'Seg 权重', step: 0.05, min: 0, max: 1 },
      { key: 'di02_good', label: 'good 阈值 (<)', step: 0.01, min: 0, max: 1 },
      { key: 'di02_warn', label: 'warn 阈值 (<)', step: 0.01, min: 0, max: 1 },
      { key: 'di02_bad', label: 'bad 阈值 (>=)', step: 0.01, min: 0, max: 1 },
      { key: 'di02_weight', label: '指标权重', step: 0.01, min: 0, max: 1 },
    ]
  },
  {
    title: '执行诊断 — 跟踪偏差 (DX-01)',
    desc: 'Lag alignment + 加权跟踪误差 (不参与总分)',
    fields: [
      { key: 'dx01_max_lag', label: 'Max Lag (帧)', step: 1, min: 0, max: 30 },
      { key: 'dx01_lag_ratio', label: 'Lag N/ratio (分母)', step: 1, min: 1, max: 50 },
      { key: 'dx01_tau_warn', label: 'Warn 阈值', step: 0.01, min: 0, max: 1 },
      { key: 'dx01_tau_bad', label: 'Bad 阈值', step: 0.01, min: 0, max: 1 },
      { key: 'dx01_w_p95', label: 'P95 权重', step: 0.1, min: 0, max: 1 },
      { key: 'dx01_w_mean', label: 'Mean 权重', step: 0.1, min: 0, max: 1 },
      { key: 'dx01_w_persist', label: 'Persist 权重', step: 0.1, min: 0, max: 1 },
      { key: 'dx01_arm_weight', label: 'Arm 误差权重', step: 0.1, min: 0, max: 1 },
      { key: 'dx01_hand_weight', label: 'Hand 误差权重', step: 0.1, min: 0, max: 1 },
    ]
  },
  {
    title: '特征提取',
    desc: '振荡/颤振检测的噪声门控百分位',
    fields: [
      { key: 'fe_osc_pct', label: 'Osc P 阈值 (%)', step: 1, min: 0, max: 50 },
      { key: 'fe_chat_pct', label: 'Chat P 阈值 (%)', step: 1, min: 0, max: 50 },
    ]
  },
  {
    title: '质量融合',
    desc: '维度权重、Soft-min 惩罚、DI 上限封顶',
    fields: [
      { key: 'qf_motion_weight', label: 'Motion 维度权重', step: 0.05, min: 0, max: 1 },
      { key: 'qf_learn_weight', label: 'Learn 维度权重', step: 0.05, min: 0, max: 1 },
      { key: 'qf_data_weight', label: 'Data 维度权重', step: 0.05, min: 0, max: 1 },
      { key: 'qf_motion_softmin_ratio', label: 'Motion Soft-min 比', step: 0.1, min: 0, max: 0.5 },
      { key: 'qf_learn_softmin_ratio', label: 'Learn Soft-min 比', step: 0.1, min: 0, max: 0.5 },
      { key: 'qf_data_softmin_ratio', label: 'Data Soft-min 比', step: 0.1, min: 0, max: 0.5 },
      { key: 'qf_data_cap_strict', label: 'DI 严格上限', step: 0.5, min: 0, max: 10 },
      { key: 'qf_data_cap_moderate', label: 'DI 中等上限', step: 0.5, min: 0, max: 10 },
      { key: 'qf_data_cap_strict_threshold', label: '严格触发 DI <', step: 0.5, min: 0, max: 10 },
      { key: 'qf_data_cap_moderate_threshold', label: '中等触发 DI <', step: 0.5, min: 0, max: 10 },
    ]
  },
  {
    title: '评分等级',
    desc: 'score → good/warn/bad 判定边界',
    fields: [
      { key: 'sl_level_good', label: 'good >=', step: 0.5, min: 0, max: 10 },
      { key: 'sl_level_warn', label: 'warn >=', step: 0.5, min: 0, max: 10 },
    ]
  },
]

async function load() {
  loading.value = true
  try {
    params.value = await fetchL3V2Params()
  } catch {
    ElMessage.error('加载 L3 v2 参数失败')
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  try {
    await updateL3V2Params(params.value)
    ElMessage.success('L3 v2 参数已保存')
  } catch {
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
        <div>
          <h1>L3 v2 指标参数配置</h1>
          <p class="settings-subtitle">RDDQF 四层训练数据质量评估引擎 — 所有阈值和权重均可调，修改后立即生效</p>
        </div>
        <el-button type="primary" size="large" :loading="saving" @click="save">保存全部</el-button>
      </div>
      <el-alert type="info" :closable="false" style="margin-bottom: 20px">
        修改后立即生效，下次加载 manual QC 时自动使用新参数。参数为空值将回退到系统默认值。
      </el-alert>

      <el-card v-for="group in groups" :key="group.title" shadow="never" class="qc-card" style="margin-bottom: 16px">
        <template #header>
          <div>
            <strong>{{ group.title }}</strong>
            <div class="group-desc">{{ group.desc }}</div>
          </div>
        </template>
        <el-row :gutter="20">
          <el-col :span="8" v-for="field in group.fields" :key="field.key" style="margin-bottom: 12px">
            <div class="field-label">{{ field.label }}</div>
            <el-input-number
              v-model="(params as any)[field.key]"
              :step="field.step"
              :min="field.min"
              :max="field.max"
              :precision="field.step < 0.001 ? 6 : field.step < 0.01 ? 4 : field.step < 0.1 ? 3 : field.step < 1 ? 2 : 0"
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
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
}

.settings-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
}

.settings-header h1 {
  margin: 0;
  font-size: 22px;
}

.settings-subtitle {
  margin: 4px 0 0;
  font-size: 13px;
  color: #909399;
}

.group-desc {
  font-size: 12px;
  color: #909399;
  font-weight: normal;
  margin-top: 2px;
}

.field-label {
  font-size: 12px;
  color: #606266;
  margin-bottom: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
