import type {
  AuditRecord,
  BatchSummary,
  DispatchPreview,
  EpisodeRow,
  IngestJob,
  MetricCard,
  QcRevision,
  QcTask,
  ReasonStat,
  ReviewerWorkload,
  TaskType,
  TimelineSegment,
  UserProfile
} from '../types/qc'

export const currentUser: UserProfile = {
  id: 'u_001',
  name: '王主管',
  role: 'qc_manager',
  avatar: 'W'
}

export const taskTypes: TaskType[] = [
  { id: 'double_hand_grasp', name: '双臂灵巧手抓取', description: 'TeleDex 双臂 + 双灵巧手采集任务', isActive: true, totalBatches: 8, totalEpisodes: 426 },
  { id: 'transfer_place', name: '转运放置', description: '抓取、转运、放置完整流程', isActive: true, totalBatches: 5, totalEpisodes: 218 },
  { id: 'drawer_open', name: '抽屉开合', description: '含接触、拉拽和终态判断', isActive: true, totalBatches: 3, totalEpisodes: 96 }
]

export const batches: BatchSummary[] = [
  {
    id: 'batch_20260622_001',
    taskTypeId: 'double_hand_grasp',
    name: '2026-06-22 上午入库',
    importedAt: '2026-06-22 09:30',
    episodeCount: 64,
    sampledEpisodeCount: 16,
    completedSampleCount: 5,
    sampleCoverageRate: 25,
    sampleReviewCompletionRate: 31,
    dispatchMode: 'sampled',
    samplingRatio: 25,
    qcStatus: 'in_review',
    passRate: 80,
    topReason: '-',
    bucket: 'yaocao',
    storagePrefix: 'double_linkerhand_grasp_2026-06-22_09-30-12/processed/'
  },
  {
    id: 'batch_20260621_002',
    taskTypeId: 'double_hand_grasp',
    name: '2026-06-21 下午入库',
    importedAt: '2026-06-21 15:18',
    episodeCount: 58,
    sampledEpisodeCount: 18,
    completedSampleCount: 15,
    sampleCoverageRate: 31,
    sampleReviewCompletionRate: 83,
    dispatchMode: 'sampled',
    samplingRatio: 30,
    qcStatus: 'in_review',
    passRate: 87.1,
    topReason: 'occlusion_object',
    bucket: 'yaocao',
    storagePrefix: 'double_linkerhand_grasp_2026-06-21_15-18-07/processed/'
  },
  {
    id: 'batch_20260620_001',
    taskTypeId: 'double_hand_grasp',
    name: '2026-06-20 稳定性复采',
    importedAt: '2026-06-20 11:04',
    episodeCount: 72,
    sampledEpisodeCount: 72,
    completedSampleCount: 72,
    sampleCoverageRate: 100,
    sampleReviewCompletionRate: 100,
    dispatchMode: 'full',
    samplingRatio: 100,
    qcStatus: 'done',
    passRate: 91.7,
    topReason: 'tracking_error',
    bucket: 'yaocao',
    storagePrefix: 'double_linkerhand_grasp_2026-06-20_11-04-39/processed/'
  },
  {
    id: 'batch_20260619_001',
    taskTypeId: 'transfer_place',
    name: '转运放置第一批',
    importedAt: '2026-06-19 17:42',
    episodeCount: 46,
    sampledEpisodeCount: 23,
    completedSampleCount: 23,
    sampleCoverageRate: 50,
    sampleReviewCompletionRate: 100,
    dispatchMode: 'sampled',
    samplingRatio: 50,
    qcStatus: 'done',
    passRate: 84.8,
    topReason: 'placement_failed',
    bucket: 'yaocao',
    storagePrefix: 'transfer_place_2026-06-19_17-42-10/processed/'
  },
  {
    id: 'batch_20260618_003',
    taskTypeId: 'drawer_open',
    name: '抽屉开合补采',
    importedAt: '2026-06-18 14:12',
    episodeCount: 38,
    sampledEpisodeCount: 38,
    completedSampleCount: 38,
    sampleCoverageRate: 100,
    sampleReviewCompletionRate: 100,
    dispatchMode: 'full',
    samplingRatio: 100,
    qcStatus: 'done',
    passRate: 89.5,
    topReason: 'task_incomplete',
    bucket: 'yaocao',
    storagePrefix: 'drawer_open_2026-06-18_14-12-02/processed/'
  }
]

export const episodes: EpisodeRow[] = [
  { id: 'episode_000124', batchId: 'batch_20260622_001', batchName: '2026-06-22 上午入库', taskName: '双臂灵巧手抓取', durationSec: 42.3, frameCount: 1269, qcStatus: 'new', qcResult: 'pending', reviewer: '-', reasonCode: '-', updatedAt: '2026-06-22 09:42' },
  { id: 'episode_000125', batchId: 'batch_20260622_001', batchName: '2026-06-22 上午入库', taskName: '双臂灵巧手抓取', durationSec: 39.8, frameCount: 1194, qcStatus: 'assigned', qcResult: 'pending', reviewer: '李审核', reasonCode: '-', updatedAt: '2026-06-22 09:44' },
  { id: 'episode_000126', batchId: 'batch_20260621_002', batchName: '2026-06-21 下午入库', taskName: '双臂灵巧手抓取', durationSec: 45.1, frameCount: 1353, qcStatus: 'done', qcResult: 'pass', reviewer: '张审核', reasonCode: '-', updatedAt: '2026-06-21 18:02' },
  { id: 'episode_000127', batchId: 'batch_20260621_002', batchName: '2026-06-21 下午入库', taskName: '双臂灵巧手抓取', durationSec: 37.6, frameCount: 1128, qcStatus: 'done', qcResult: 'fail', reviewer: '张审核', reasonCode: 'occlusion_object', updatedAt: '2026-06-21 18:08' },
  { id: 'episode_000128', batchId: 'batch_20260620_001', batchName: '2026-06-20 稳定性复采', taskName: '双臂灵巧手抓取', durationSec: 41.7, frameCount: 1251, qcStatus: 'done', qcResult: 'fail', reviewer: '李审核', reasonCode: 'tracking_error', updatedAt: '2026-06-20 16:21' },
  { id: 'episode_000129', batchId: 'batch_20260622_001', batchName: '2026-06-22 上午入库', taskName: '双臂灵巧手抓取', durationSec: 44.6, frameCount: 1338, qcStatus: 'in_review', qcResult: 'pending', reviewer: '赵审核', reasonCode: '-', updatedAt: '2026-06-22 10:04' },
  { id: 'episode_000130', batchId: 'batch_20260619_001', batchName: '转运放置第一批', taskName: '转运放置', durationSec: 51.2, frameCount: 1536, qcStatus: 'done', qcResult: 'pass', reviewer: '李审核', reasonCode: '-', updatedAt: '2026-06-19 19:20' },
  { id: 'episode_000131', batchId: 'batch_20260618_003', batchName: '抽屉开合补采', taskName: '抽屉开合', durationSec: 34.9, frameCount: 1047, qcStatus: 'done', qcResult: 'fail', reviewer: '赵审核', reasonCode: 'task_incomplete', updatedAt: '2026-06-18 16:12' }
]

export const qcTasks: QcTask[] = [
  {
    id: 'task_001',
    episodeId: 'episode_000124',
    batchId: 'batch_20260622_001',
    batchName: '2026-06-22 上午入库',
    taskName: '双臂灵巧手抓取',
    assignee: '未派发',
    status: 'new',
    priority: 'high',
    dispatchMode: 'sampled',
    samplingRatio: 25,
    dispatchGeneration: 1,
    isActive: true,
    assignmentMode: 'unassigned',
    createdAt: '2026-06-22 09:45',
    reviewLock: { isLocked: false, isMine: false, ownerUserId: '', ownerName: '', acquiredAt: null, expiresAt: null, version: 1 }
  },
  {
    id: 'task_002',
    episodeId: 'episode_000125',
    batchId: 'batch_20260622_001',
    batchName: '2026-06-22 上午入库',
    taskName: '双臂灵巧手抓取',
    assignee: '李审核',
    status: 'assigned',
    priority: 'normal',
    dispatchMode: 'sampled',
    samplingRatio: 25,
    dispatchGeneration: 1,
    isActive: true,
    assignmentMode: 'even',
    createdAt: '2026-06-22 09:47',
    reviewLock: { isLocked: false, isMine: false, ownerUserId: '', ownerName: '', acquiredAt: null, expiresAt: null, version: 3 }
  },
  {
    id: 'task_003',
    episodeId: 'episode_000129',
    batchId: 'batch_20260622_001',
    batchName: '2026-06-22 上午入库',
    taskName: '双臂灵巧手抓取',
    assignee: '赵审核',
    status: 'in_review',
    priority: 'normal',
    dispatchMode: 'sampled',
    samplingRatio: 25,
    dispatchGeneration: 1,
    isActive: true,
    assignmentMode: 'even',
    createdAt: '2026-06-22 09:51',
    reviewLock: { isLocked: true, isMine: false, ownerUserId: 'u_003', ownerName: '赵审核', acquiredAt: '2026-06-22 10:04', expiresAt: '2026-06-22 10:24', version: 4 }
  },
  {
    id: 'task_004',
    episodeId: 'episode_000132',
    batchId: 'batch_20260622_001',
    batchName: '2026-06-22 上午入库',
    taskName: '双臂灵巧手抓取',
    assignee: '未派发',
    status: 'new',
    priority: 'normal',
    dispatchMode: 'sampled',
    samplingRatio: 25,
    dispatchGeneration: 1,
    isActive: false,
    assignmentMode: 'unassigned',
    createdAt: '2026-06-22 10:03',
    reviewLock: { isLocked: false, isMine: false, ownerUserId: '', ownerName: '', acquiredAt: null, expiresAt: null, version: 1 }
  }
]

export const dispatchPreviews: DispatchPreview[] = [
  {
    batchId: 'batch_20260622_001',
    candidateEpisodeCount: 64,
    sampledEpisodeCount: 16,
    unsampledEpisodeCount: 48,
    createdTaskCount: 16,
    assignedTaskCount: 11,
    inReviewTaskCount: 3,
    doneTaskCount: 5,
    supersededTaskCount: 4,
    pendingAssignCount: 1,
    dispatchMode: 'sampled',
    samplingRatio: 25,
    activeDispatchGeneration: 1
  },
  {
    batchId: 'batch_20260621_002',
    candidateEpisodeCount: 58,
    sampledEpisodeCount: 18,
    unsampledEpisodeCount: 40,
    createdTaskCount: 18,
    assignedTaskCount: 3,
    inReviewTaskCount: 0,
    doneTaskCount: 15,
    supersededTaskCount: 0,
    pendingAssignCount: 0,
    dispatchMode: 'sampled',
    samplingRatio: 30,
    activeDispatchGeneration: 2
  },
  {
    batchId: 'batch_20260620_001',
    candidateEpisodeCount: 72,
    sampledEpisodeCount: 72,
    unsampledEpisodeCount: 0,
    createdTaskCount: 72,
    assignedTaskCount: 0,
    inReviewTaskCount: 0,
    doneTaskCount: 72,
    supersededTaskCount: 0,
    pendingAssignCount: 0,
    dispatchMode: 'full',
    samplingRatio: 100,
    activeDispatchGeneration: 3
  }
]

export const metricCards: MetricCard[] = [
  { key: 'q_motion', label: 'Q_motion', value: '8.6', level: 'good', description: '轨迹质量综合分' },
  { key: 'smoothness', label: '平滑度 LDLJ', value: '7.9', level: 'good', description: '动作连续性良好' },
  { key: 'sync', label: '同步异常率', value: '1.8%', level: 'good', description: '低于 5% 阈值' },
  { key: 'tracking', label: '跟踪误差', value: '0.21', level: 'warn', description: '右手末段略高' },
  { key: 'chatter', label: '手指颤振', value: '0.08', level: 'good', description: '未发现明显抖动' },
  { key: 'saturation', label: '动作饱和率', value: '3.2%', level: 'good', description: '遥操指令正常' }
]

export const timelineSegments: TimelineSegment[] = [
  { start: 18, end: 26, level: 'warn', label: 'tracking_error' },
  { start: 63, end: 71, level: 'bad', label: 'occlusion_object' },
  { start: 82, end: 88, level: 'warn', label: 'sync_bad' }
]

export const auditRecords: AuditRecord[] = [
  { id: 'audit_001', operator: '张审核', action: '提交人工质检', target: 'episode_000127', time: '2026-06-21 18:08', detail: 'fail / occlusion_object / 已写入 revision #2' },
  { id: 'audit_002', operator: '王主管', action: '批量派发任务', target: 'batch_20260622_001', time: '2026-06-22 09:50', detail: '分配 32 条 episode 给李审核' },
  { id: 'audit_003', operator: '系统', action: '扫描入库', target: 'batch_20260622_001', time: '2026-06-22 09:31', detail: '发现 64 条 MinIO episode' },
  { id: 'audit_004', operator: '李审核', action: '释放软锁', target: 'episode_000128', time: '2026-06-20 16:22', detail: '人工质检提交后释放 review_lock' }
]

export const reasonStats: ReasonStat[] = [
  { reason: 'occlusion_object', count: 14, ratio: 31, category: 'L2' },
  { reason: 'tracking_error', count: 9, ratio: 20, category: 'L3' },
  { reason: 'placement_failed', count: 8, ratio: 18, category: 'L4' },
  { reason: 'task_incomplete', count: 7, ratio: 16, category: 'L4' },
  { reason: 'sync_bad', count: 4, ratio: 9, category: 'L3' },
  { reason: 'metadata_missing', count: 3, ratio: 6, category: 'System' }
]

export const reviewerWorkloads: ReviewerWorkload[] = [
  { name: '李审核', assigned: 38, done: 27, passRate: 88.9, avgMinutes: 3.8 },
  { name: '张审核', assigned: 31, done: 31, passRate: 83.9, avgMinutes: 4.1 },
  { name: '赵审核', assigned: 24, done: 15, passRate: 86.7, avgMinutes: 4.6 }
]

export const ingestJobs: IngestJob[] = [
  { id: 'job_001', bucket: 'yaocao', scope: 'full', status: 'done', progress: 100, confirmedLists: 4, totalEpisodes: 64, newEpisodes: 64, detail: 'lists=4 episodes=64 new=64', startedAt: '2026-06-22 09:30', finishedAt: '2026-06-22 09:34' },
  { id: 'job_002', bucket: 'yaocao', scope: 'full', status: 'scanning', progress: 0, confirmedLists: 0, totalEpisodes: 0, newEpisodes: 0, detail: '正在递归扫描对象前缀', startedAt: '2026-06-22 10:10', finishedAt: null },
  { id: 'job_003', bucket: 'yaocao', scope: 'full', status: 'classifying', progress: 0, confirmedLists: 3, totalEpisodes: 58, newEpisodes: 12, detail: '正在匹配 list 与 episode 状态', startedAt: '2026-06-21 15:18', finishedAt: null }
]

export const qcRevisions: QcRevision[] = [
  { episodeId: 'episode_000127', batchId: 'batch_20260622_001', batchName: '2026-06-22 上午入库', revisionNo: 3, result: 'fail', primaryReason: 'occlusion_object', operator: '张审核', time: '2026-06-21 18:08', note: '目标物在关键接触阶段被右手遮挡，无法确认抓取稳定性。' },
  { episodeId: 'episode_000127', batchId: 'batch_20260622_001', batchName: '2026-06-22 上午入库', revisionNo: 2, result: 'pass', primaryReason: '-', operator: '李审核', time: '2026-06-21 17:52', note: '初审认为任务完成，但未展开 depth 辅助核查。' },
  { episodeId: 'episode_000127', batchId: 'batch_20260622_001', batchName: '2026-06-22 上午入库', revisionNo: 1, result: 'pending', primaryReason: '-', operator: '系统', time: '2026-06-21 15:20', note: '入库后先进入候选池，再按批次抽检计划生成 QC 任务。' }
]
