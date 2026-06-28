<script setup lang="ts">
import { ref } from 'vue'

const result = defineModel<'pass' | 'fail'>('result', { default: 'pass' })
const primaryReason = defineModel<string>('primaryReason', { default: '' })
const secondaryReasons = ref<string[]>([])

const reasonGroups = [
  { label: 'L2 视觉类', options: [
    { value: 'blur', label: '图像模糊' },
    { value: 'exposure_over', label: '过度曝光' },
    { value: 'occlusion_hand', label: '手部遮挡' },
    { value: 'occlusion_object', label: '目标遮挡' },
    { value: 'object_not_visible', label: '目标不可见' },
    { value: 'depth_invalid', label: '深度图异常' },
  ]},
  { label: '动作示范质量', options: [
    { value: 'trajectory_unsmooth', label: '轨迹不平滑 (MQ-01)' },
    { value: 'action_discontinuity', label: '动作指令突变 (MQ-02)' },
    { value: 'oscillation', label: '控制震荡 (MQ-03)' },
    { value: 'chatter', label: '手指颤振 (MQ-03)' },
  ]},
  { label: '可学习性', options: [
    { value: 'low_effective_action', label: '有效动作不足 (LQ-01)' },
    { value: 'low_information_density', label: '信息密度低 (LQ-02)' },
    { value: 'prolonged_idle', label: '长时间停滞 (LQ-03)' },
  ]},
  { label: '数据完整性', options: [
    { value: 'sync_bad', label: '同步异常 (DI-02)' },
    { value: 'timestamp_irregular', label: '时间戳不规则 (DI-01)' },
  ]},
  { label: '执行诊断', options: [
    { value: 'tracking_error', label: '跟踪偏差大 (DX-01)' },
  ]},
  { label: 'L4 任务类', options: [
    { value: 'task_incomplete', label: '动作流程不完整' },
    { value: 'wrong_final_state', label: '终止状态错误' },
    { value: 'grasp_failed', label: '抓取失败' },
    { value: 'placement_failed', label: '放置失败' },
  ]},
  { label: '系统类', options: [
    { value: 'conversion_issue', label: '数据转换问题' },
    { value: 'metadata_missing', label: '元数据缺失' },
    { value: 'modality_missing', label: '模态缺失' },
    { value: 'file_corrupted', label: '文件损坏' },
  ]}
]
</script>

<template>
  <div class="reason-picker">
    <el-radio-group v-model="result" size="large">
      <el-radio-button label="pass">Pass</el-radio-button>
      <el-radio-button label="fail">Fail</el-radio-button>
    </el-radio-group>

    <el-divider />

    <template v-if="result === 'fail'">
      <div class="field-label">主原因码（Fail 必填，只能一个）</div>
      <el-select v-model="primaryReason" class="qc-select" placeholder="选择主原因码" style="width: 100%">
        <el-option-group v-for="group in reasonGroups" :key="group.label" :label="group.label">
          <el-option v-for="item in group.options" :key="item.value" :label="item.label" :value="item.value" />
        </el-option-group>
      </el-select>
    </template>

    <div class="field-label">次原因码（可选，最多 3 个）</div>
    <el-select v-model="secondaryReasons" class="qc-select" multiple :multiple-limit="3" placeholder="记录轻微问题或伴随问题" style="width: 100%">
      <el-option-group v-for="group in reasonGroups" :key="group.label" :label="group.label">
        <el-option v-for="item in group.options" :key="item.value" :label="item.label" :value="item.value" />
      </el-option-group>
    </el-select>
  </div>
</template>
