<script setup lang="ts">
import AppLayout from '../components/AppLayout.vue'
</script>

<template>
  <AppLayout>
    <div class="qc-settings-page">
      <div class="qc-settings-header">
        <h1>设置</h1>
      </div>

      <el-tabs model-value="general">
        <el-tab-pane label="通用" name="general">
          <el-empty description="L3 v2 指标阈值当前为内置默认值，可配置参数面板将在后续版本中开放" />
        </el-tab-pane>
      </el-tabs>
    </div>
  </AppLayout>
</template>
