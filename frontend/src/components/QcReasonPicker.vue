<script setup lang="ts">
import { ref } from 'vue'

const result = defineModel<'pass' | 'fail'>('result', { default: 'pass' })
const primaryReason = defineModel<string>('primaryReason', { default: '' })
const secondaryReasons = ref<string[]>([])

const reasonGroups = [
  { label: 'L2 视觉类', options: ['blur', 'exposure_over', 'occlusion_hand', 'occlusion_object', 'object_not_visible', 'depth_invalid'] },
  { label: 'L3 轨迹类', options: ['motion_abnormal', 'chatter', 'stall', 'tracking_error', 'joint_limit_risk', 'sync_bad'] },
  { label: 'L4 任务类', options: ['task_incomplete', 'wrong_final_state', 'grasp_failed', 'placement_failed'] },
  { label: '系统类', options: ['conversion_issue', 'metadata_missing', 'modality_missing', 'file_corrupted'] }
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
      <el-select v-model="primaryReason" placeholder="选择主原因码" style="width: 100%">
        <el-option-group v-for="group in reasonGroups" :key="group.label" :label="group.label">
          <el-option v-for="item in group.options" :key="item" :label="item" :value="item" />
        </el-option-group>
      </el-select>
    </template>

    <div class="field-label">次原因码（可选，最多 3 个）</div>
    <el-select v-model="secondaryReasons" multiple :multiple-limit="3" placeholder="记录轻微问题或伴随问题" style="width: 100%">
      <el-option-group v-for="group in reasonGroups" :key="group.label" :label="group.label">
        <el-option v-for="item in group.options" :key="item" :label="item" :value="item" />
      </el-option-group>
    </el-select>
  </div>
</template>
