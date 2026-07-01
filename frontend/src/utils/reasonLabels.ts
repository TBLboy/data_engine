const REASON_MAP: Record<string, string> = {
  blur: '图像模糊',
  exposure_over: '过度曝光',
  occlusion_hand: '手部遮挡',
  occlusion_object: '目标遮挡',
  object_not_visible: '目标不可见',
  depth_invalid: '深度图异常',
  trajectory_unsmooth: '轨迹不平滑 (MQ-01)',
  action_discontinuity: '动作指令突变 (MQ-02)',
  oscillation: '控制震荡 (MQ-03)',
  chatter: '手指颤振 (MQ-03)',
  low_effective_action: '有效动作不足 (LQ-01)',
  low_information_density: '信息密度低 (LQ-02)',
  prolonged_idle: '长时间停滞 (LQ-03)',
  sync_bad: '同步异常 (DI-02)',
  timestamp_irregular: '时间戳不规则 (DI-01)',
  tracking_error: '跟踪偏差大 (DX-01)',
  task_incomplete: '动作流程不完整',
  wrong_final_state: '终止状态错误',
  grasp_failed: '抓取失败',
  placement_failed: '放置失败',
  conversion_issue: '数据转换问题',
  metadata_missing: '元数据缺失',
  modality_missing: '模态缺失',
  file_corrupted: '文件损坏',
}

export function reasonLabel(code: string): string {
  return REASON_MAP[code] || (code === '-' ? '-' : code)
}
