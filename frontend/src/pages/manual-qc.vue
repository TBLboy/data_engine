<script setup lang="ts">
import { QuestionFilled } from '@element-plus/icons-vue'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import AppLayout from '../components/AppLayout.vue'
import QcReasonPicker from '../components/QcReasonPicker.vue'
import AiAssistantAnchor from '../components/ai/AiAssistantAnchor.vue'
import AiAssistantPanel from '../components/ai/AiAssistantPanel.vue'
import { claimManualQc, fetchManualQcContext, fetchTelemetryCurve, refreshManualQcMedia, releaseManualQc, submitManualQc, type ManualQcContext, type TelemetryCurve } from '../api/client'
import { useAiAssistant } from '../composables/useAiAssistant'
import { useSessionStore } from '../stores/session'
import { triggerCelebration } from '../composables/useCelebration'
import { Chart, registerables } from 'chart.js'

const timelineOverlayPlugin = {
  id: 'timelineOverlay',
  beforeDatasetsDraw(chart: Chart, _args: unknown, options?: any) {
    const xScale = chart.scales.x
    const chartArea = chart.chartArea
    if (!xScale || !chartArea) return

    const segments = Array.isArray(options?.segments) ? options.segments : []
    if (!segments.length) return
    const ctx = chart.ctx

    // Pre-compute pixel range for each segment
    const segPixels = segments.map((s: any) => {
      const start = Math.max(s.startSec ?? 0, 0)
      const end = Math.max(s.endSec ?? start, start)
      const left = Math.max(chartArea.left, Math.round(xScale.getPixelForValue(start)))
      const right = Math.min(chartArea.right, Math.round(xScale.getPixelForValue(end)))
      return { level: s.level as string, left, right }
    })

    ctx.save()
    const top = chartArea.top
    const height = chartArea.bottom - chartArea.top

    // Scan each pixel column and determine dominant level + overlap count
    let x = chartArea.left
    while (x <= chartArea.right) {
      let badCount = 0
      let warnCount = 0
      let goodCount = 0
      for (const sp of segPixels) {
        if (x >= sp.left && x < sp.right) {
          if (sp.level === 'bad') badCount++
          else if (sp.level === 'warn') warnCount++
          else goodCount++
        }
      }

      let fillStyle: string | null = null
      if (badCount > 0) {
        const alpha = Math.min(0.15 + badCount * 0.12, 0.60)
        fillStyle = `rgba(220, 38, 38, ${alpha})`
      } else if (warnCount > 0) {
        const alpha = Math.min(0.10 + warnCount * 0.08, 0.45)
        fillStyle = `rgba(230, 162, 60, ${alpha})`
      } else if (goodCount > 0) {
        const alpha = Math.min(0.05 + goodCount * 0.04, 0.20)
        fillStyle = `rgba(103, 194, 58, ${alpha})`
      }

      if (fillStyle) {
        ctx.fillStyle = fillStyle
        ctx.fillRect(x, top, 1, height)
      }
      x++
    }
    ctx.restore()
  }
}

Chart.register(...registerables, timelineOverlayPlugin)

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const ai = useAiAssistant()
const result = ref<'pass' | 'fail'>('pass')
const primaryReason = ref('')
const currentFrame = ref(0)
const playing = ref(false)
const note = ref('')
const loading = ref(true)
const submitting = ref(false)
const claiming = ref(false)
const releasing = ref(false)
const refreshingMedia = ref(false)
const error = ref('')
const payload = ref<ManualQcContext | null>(null)
const selectedVariant = ref<'rgb' | 'depth_colormap'>('rgb')
const syncingSlider = ref(false)
const celebrating = ref(false)
const celebrationDone = ref(false)
const videoRefs = ref<Record<string, HTMLVideoElement | null>>({})
const isReviewer = computed(() => session.user?.role === 'reviewer')
const isManager = computed(() => session.user?.role === 'admin' || session.user?.role === 'qc_manager')
const curveData = ref<TelemetryCurve | null>(null)
const curveError = ref('')
const curveMode = ref<'arm' | 'hand'>('arm')
const chartCanvasL = ref<HTMLCanvasElement | null>(null)
const chartCanvasR = ref<HTMLCanvasElement | null>(null)
const chartHoverTimeSec = ref<number | null>(null)
const selectedMetricId = ref('')
const chartDragging = ref(false)
const suppressFrameWatcher = ref(false)
const chartPlaybackCursorLeftPx = ref(0)
const chartPlaybackCursorLeftPxR = ref(0)
const chartPlaybackCursorVisible = ref(false)
const chartHoverCursorLeftPx = ref(0)
const chartHoverCursorLeftPxR = ref(0)
const chartHoverCursorVisible = ref(false)
const chartCursorTopPx = ref(0)
const chartCursorHeightPx = ref(0)
let chartL: Chart | null = null
let chartR: Chart | null = null
let playbackLoopId: number | null = null
let lastScrubMs = 0

const episodeId = computed(() => String(route.params.id))
const fps = computed(() => payload.value?.episode.fps || 30)
const totalFrames = computed(() => Math.max(0, payload.value?.episode.frameCount ?? 0))
const durationSec = computed(() => payload.value?.episode.durationSec ?? 0)
const maxFrame = computed(() => Math.max(totalFrames.value - 1, 0))
const progress = computed(() => (maxFrame.value ? Math.round((currentFrame.value / maxFrame.value) * 100) : 0))
const currentTimeSec = computed(() => currentFrame.value / fps.value)
const l3V2Report = computed(() => payload.value?.l3V2 ?? null)
const qualityDimensions = computed(() => l3V2Report.value?.qualityDimensions ?? [])
const diagnosticMetrics = computed(() => l3V2Report.value?.diagnosticMetrics ?? [])
const trainingQualityScore = computed(() => l3V2Report.value?.trainingQualityScore ?? null)
const trainingQualityLevel = computed(() => l3V2Report.value?.trainingQualityLevel ?? 'good')
const scoreRingPercent = computed(() => {
  const s = trainingQualityScore.value
  if (s == null) return 0
  return Math.round(Math.max(0, Math.min(10, s)) / 10 * 100)
})
const timelineSegments = computed(() => l3V2Report.value?.timelineSegments ?? [])
const normalizedTimelineSegments = computed(() => timelineSegments.value.map((segment: any) => ({
  ...segment,
  startSec: segmentStartSec(segment),
  endSec: segmentEndSec(segment),
}))
  .sort((a: any, b: any) => a.startSec - b.startSec))
const activeTimelineSegments = computed(() => normalizedTimelineSegments.value.filter((segment: any) => {
  const epsilon = 1 / Math.max(fps.value || 30, 1)
  return currentTimeSec.value + epsilon >= segment.startSec && currentTimeSec.value - epsilon <= segment.endSec
}))

const activeTimelineSegmentIds = computed(() => new Set(activeTimelineSegments.value.map((segment: any) => segmentKey(segment))))
const chartLegendItems = computed(() => {
  const cd = curveData.value
  if (!cd) return [] as Array<{ key: string; label: string; color: string; dashed: boolean }>
  const isArm = curveMode.value === 'arm'
  const dimCount = isArm ? cd.armDims : cd.handDims
  const perSideCount = Math.round(dimCount / 2)
  const colors = ['#409EFF', '#67C23A', '#E6A23C', '#F56C6C', '#909399', '#00D4AA', '#B37FEB', '#FF85C0', '#7EC8E3', '#FFD700', '#CD5C5C', '#8FBC8F']
  const items: Array<{ key: string; label: string; color: string; dashed: boolean }> = []
  for (let d = 0; d < perSideCount; d++) {
    const color = colors[d % colors.length]
    items.push({ key: `actual-${d}`, label: `J${d + 1} 实际`, color, dashed: false })
    items.push({ key: `target-${d}`, label: `J${d + 1} 目标`, color, dashed: true })
  }
  return items
})
const qcRevisions = computed(() => payload.value?.revisions ?? [])
const episode = computed(() => payload.value?.episode)
const episodeNumber = computed(() => {
  const parts = episode.value?.id?.split('_episode_')
  return parts?.[1] ? `episode_${parts[1]}` : ''
})
const reviewLock = computed(() => payload.value?.reviewLock)
const media = computed(() => payload.value?.media ?? [])
const mediaByVariant = computed(() => media.value.filter((item) => item.variant === selectedVariant.value))
const canSubmit = computed(() => Boolean(reviewLock.value?.isMine && !submitting.value))
const lockTagType = computed(() => {
  if (reviewLock.value?.isMine) return 'success'
  if (reviewLock.value?.isLocked) return 'danger'
  return 'warning'
})
const lockLabel = computed(() => {
  if (reviewLock.value?.isMine) return '当前由你审核'
  if (reviewLock.value?.isLocked) return '当前被他人锁定'
  return '当前无人认领'
})

const severityTagType = (level?: string) => {
  if (level === 'bad') return 'danger'
  if (level === 'warn') return 'warning'
  return 'success'
}

const segmentStartSec = (segment: any) => Number(segment.startSec ?? segment.start ?? 0)
const segmentEndSec = (segment: any) => Number(segment.endSec ?? segment.end ?? 0)
const segmentKey = (segment: any) => `${segment.label}-${segmentStartSec(segment)}-${segmentEndSec(segment)}-${segment.sourceMetricId || ''}`

const seekToTime = async (targetSec: number) => {
  pauseAll()
  await applyTimeToPlayback(targetSec)
}

const applyTimeToPlayback = async (targetSec: number) => {
  const clampedSec = Math.max(0, Math.min(durationSec.value || targetSec, targetSec))
  suppressFrameWatcher.value = true
  currentFrame.value = Math.max(0, Math.min(maxFrame.value, Math.round(clampedSec * fps.value)))
  await syncVideosToFrame()
  suppressFrameWatcher.value = false
  drawChartOverlay()
}

const scrubToTime = (targetSec: number) => {
  const clampedSec = Math.max(0, Math.min(durationSec.value || targetSec, targetSec))
  const frame = Math.max(0, Math.min(maxFrame.value, Math.round(clampedSec * fps.value)))
  suppressFrameWatcher.value = true
  currentFrame.value = frame
  const targetTime = durationSec.value ? Math.min(frame / fps.value, durationSec.value) : frame / fps.value
  for (const video of activeVideoElements()) {
    video.currentTime = targetTime
  }
  drawChartOverlay()
}

const chartTimeFromPointer = (event: MouseEvent, chart: Chart | null, canvas: HTMLCanvasElement | null) => {
  const xScale = chart?.scales?.x
  const rect = canvas?.getBoundingClientRect()
  if (!xScale || !rect) return null
  const pixelX = event.clientX - rect.left
  const nextTime = Number(xScale.getValueForPixel(pixelX))
  if (!Number.isFinite(nextTime)) return null
  return Math.max(0, Math.min(durationSec.value || nextTime, nextTime))
}

const handleChartPointerMove = (event: MouseEvent, chart: Chart | null, canvas: HTMLCanvasElement | null) => {
  const nextTime = chartTimeFromPointer(event, chart, canvas)
  chartHoverTimeSec.value = nextTime
  drawChartOverlay()
  if (chartDragging.value && nextTime != null) {
    const now = performance.now()
    if (now - lastScrubMs < 16) return
    lastScrubMs = now
    scrubToTime(nextTime)
  }
}

const handleChartPointerLeave = () => {
  if (chartDragging.value) return
  chartHoverTimeSec.value = null
  drawChartOverlay()
}

const handleChartPointerDown = (event: MouseEvent, chart: Chart | null, canvas: HTMLCanvasElement | null) => {
  const nextTime = chartTimeFromPointer(event, chart, canvas)
  if (nextTime == null) return
  chartDragging.value = true
  chartHoverTimeSec.value = nextTime
  pauseAll()
  scrubToTime(nextTime)
}

const stopChartDragging = () => {
  if (!chartDragging.value) return
  chartDragging.value = false
  suppressFrameWatcher.value = false
  lastScrubMs = 0
  drawChartOverlay()
}

const jumpToSegment = async (segment: any) => {
  await seekToTime(segmentStartSec(segment))
}

const drawChartOverlay = () => {
  for (const ch of [chartL, chartR]) {
    if (!ch) continue
    const pluginOptions = ((ch.options.plugins as any).timelineOverlay ??= {})
    pluginOptions.segments = normalizedTimelineSegments.value
    ch.update('none')
  }
  updateChartCursorPosition()
}

const updateChartCursorPosition = () => {
  const canvasL = chartCanvasL.value
  const canvasR = chartCanvasR.value
  if (!canvasL || !canvasR) {
    chartPlaybackCursorVisible.value = false
    chartHoverCursorVisible.value = false
    return
  }

  const calcCursor = (ch: Chart, canvas: HTMLCanvasElement, time: number) => {
    const xScale = ch.scales.x
    const chartArea = ch.chartArea
    if (!xScale || !chartArea) return null
    const displayWidth = canvas.getBoundingClientRect().width || ch.width || 1
    const displayHeight = canvas.getBoundingClientRect().height || ch.height || 1
    const scale = displayWidth / (ch.width || displayWidth || 1)
    const scaleY = displayHeight / (ch.height || displayHeight || 1)
    const pixel = Number(xScale.getPixelForValue(time))
    if (!Number.isFinite(pixel)) return null
    return { left: pixel * scale, top: chartArea.top * scaleY, height: Math.max((chartArea.bottom - chartArea.top) * scaleY, 0) }
  }

  const playbackL = chartL ? calcCursor(chartL, canvasL, currentTimeSec.value) : null
  const playbackR = chartR ? calcCursor(chartR, canvasR, currentTimeSec.value) : null
  chartPlaybackCursorVisible.value = playbackL != null && playbackR != null
  if (playbackL) {
    chartPlaybackCursorLeftPx.value = playbackL.left
    chartCursorTopPx.value = playbackL.top
    chartCursorHeightPx.value = playbackL.height
  }
  if (playbackR) chartPlaybackCursorLeftPxR.value = playbackR.left

  const hoverTime = chartHoverTimeSec.value
  if (hoverTime == null || !Number.isFinite(hoverTime)) {
    chartHoverCursorVisible.value = false
    return
  }
  const hoverL = chartL ? calcCursor(chartL, canvasL, hoverTime) : null
  const hoverR = chartR ? calcCursor(chartR, canvasR, hoverTime) : null
  chartHoverCursorVisible.value = hoverL != null && hoverR != null
  if (hoverL) chartHoverCursorLeftPx.value = hoverL.left
  if (hoverR) chartHoverCursorLeftPxR.value = hoverR.left
}

const stopPlaybackLoop = () => {
  if (playbackLoopId !== null) {
    cancelAnimationFrame(playbackLoopId)
    playbackLoopId = null
  }
}

const activeVideoElements = () => mediaByVariant.value
  .map((item) => videoRefs.value[item.objectId])
  .filter((item): item is HTMLVideoElement => Boolean(item))

const syncVideosToFrame = async () => {
  const targetTime = durationSec.value ? Math.min(currentTimeSec.value, durationSec.value) : currentTimeSec.value
  activeVideoElements().forEach((video) => {
    if (Math.abs(video.currentTime - targetTime) > 0.03) {
      video.currentTime = targetTime
    }
  })
  await nextTick()
}

const updateFrameFromVideoClock = () => {
  const [video] = activeVideoElements()
  if (!video || !playing.value) {
    stopPlaybackLoop()
    return
  }
  const nextFrame = Math.min(Math.round(video.currentTime * fps.value), maxFrame.value)
  currentFrame.value = nextFrame
  playbackLoopId = requestAnimationFrame(updateFrameFromVideoClock)
}

const pauseAll = () => {
  activeVideoElements().forEach((video) => video.pause())
  playing.value = false
  stopPlaybackLoop()
}

const playAll = async () => {
  await syncVideosToFrame()
  await Promise.all(activeVideoElements().map(async (video) => {
    await video.play()
  }))
  playing.value = true
  stopPlaybackLoop()
  playbackLoopId = requestAnimationFrame(updateFrameFromVideoClock)
}

const setVideoRef = (objectId: string) => (element: Element | { $el?: Element } | null) => {
  if (element instanceof HTMLVideoElement) {
    videoRefs.value[objectId] = element
    return
  }
  if (element && '$el' in element && element.$el instanceof HTMLVideoElement) {
    videoRefs.value[objectId] = element.$el
    return
  }
  videoRefs.value[objectId] = null
}

const formatError = (err: unknown, fallback: string) => {
  if (!(err instanceof Error)) return fallback
  try {
    const parsed = JSON.parse(err.message) as { detail?: string }
    return parsed.detail || fallback
  } catch {
    return err.message || fallback
  }
}

const loadContext = async () => {
  loading.value = true
  error.value = ''
  try {
    payload.value = await fetchManualQcContext(episodeId.value)
    currentFrame.value = Math.min(0, maxFrame.value)
    playing.value = false
    stopPlaybackLoop()
    await nextTick()
    await syncVideosToFrame()
    loadCurveData()
  } catch (err) {
    error.value = formatError(err, '加载人工质检上下文失败')
  } finally {
    loading.value = false
  }
}

const destroyChart = () => {
  if (chartL) { chartL.destroy(); chartL = null }
  if (chartR) { chartR.destroy(); chartR = null }
}

const loadCurveData = async () => {
  destroyChart()
  curveError.value = ''
  try {
    curveData.value = await fetchTelemetryCurve(episodeId.value)
    await nextTick()
    renderChart()
  } catch (err) {
    curveData.value = null
    curveError.value = '遥操作曲线数据暂时不可用'
  }
}

function buildAiPayload() {
  const report = l3V2Report.value
  if (!report) return null
  const metrics = (report.metricResults || []).map((m: any) => ({
    metricId: m.metricId,
    name: m.name,
    qualityDimension: m.qualityDimension,
    evidenceId: m.evidenceId || '',
    value: m.value,
    valueText: m.valueText || '',
    unit: m.unit || '',
    score: m.score,
    level: m.level,
    description: m.description || '',
    confidence: m.confidence ?? 1,
    weight: m.weight ?? 1,
  }))
  const timelineSegments = (report.timelineSegments || []).map((s: any) => ({
    start: s.start,
    end: s.end,
    startSec: s.startSec,
    endSec: s.endSec,
    level: s.level,
    label: s.label,
    sourceMetricId: s.sourceMetricId,
    qualityDimension: s.qualityDimension || '',
  }))
  return {
    episodeId: episodeId.value,
    qMotionScore: report.trainingQualityScore,
    qMotionLevel: report.trainingQualityLevel,
    weightedScoreBeforeCap: null as number | null,
    metrics,
    timelineSegments,
  }
}

function buildPageState() {
  return {
    selectedMetricId: selectedMetricId.value || '',
    currentVideoTimeSec: (currentTimeSec.value !== undefined ? currentTimeSec.value : null) as number | null,
    selectedTimelineSegmentId: '',
    visibleChart: curveMode.value === 'arm' ? 'arm_qpos_actions' : 'hand_qpos_actions',
    openedMetricPanel: '',
  }
}

async function handleAiSend(prompt: string) {
  const payload = buildAiPayload()
  if (!payload) return
  await ai.send(prompt, payload, buildPageState())
}

async function handleAiOpen() {
  ai.open()
  const payload = buildAiPayload()
  if (!payload) return
  // 从服务端恢复对话
  await ai.loadConversation(payload.episodeId)
  // 如果恢复后消息只有默认欢迎语，自动请求首次解释
  if (ai.messages.value.length <= 1) {
    await ai.send(payload.episodeId ? '' : '解释本条检测结果', payload, buildPageState())
  }
}

const renderChart = () => {
  if (!chartCanvasL.value || !chartCanvasR.value || !curveData.value) return
  const cd = curveData.value
  const isArm = curveMode.value === 'arm'
  const qpos = isArm ? cd.qposArm : cd.qposHand
  const actions = isArm ? cd.actionsArm : cd.actionsHand
  const dimCount = isArm ? cd.armDims : cd.handDims
  if (!dimCount || !qpos.length) return

  const colors = ['#409EFF', '#67C23A', '#E6A23C', '#F56C6C', '#909399', '#00D4AA', '#B37FEB', '#FF85C0', '#7EC8E3', '#FFD700', '#CD5C5C', '#8FBC8F']
  const perSideCount = Math.round(dimCount / 2)
  const yTitle = isArm ? '位置 (rad)' : '位置 (0-255)'

  const sideLabels = isArm ? ['左臂', '右臂'] : ['左手', '右手']

  const buildDatasets = (dStart: number) => {
    const ds: any[] = []
    for (let d = dStart; d < dStart + perSideCount; d++) {
      const c = colors[(d - dStart) % colors.length]
      ds.push({
        label: `J${d + 1} 实际`,
        data: qpos.map((row, i) => ({ x: cd.timestamps[i], y: row[d] })),
        borderColor: c, backgroundColor: 'transparent',
        borderWidth: 1.5, pointRadius: 0, pointHoverRadius: 3, pointHitRadius: 8, tension: 0.1,
      })
      ds.push({
        label: `J${d + 1} 目标`,
        data: actions.map((row, i) => ({ x: cd.timestamps[i], y: row[d] })),
        borderColor: c, backgroundColor: 'transparent',
        borderWidth: 1, borderDash: [4, 3], pointRadius: 0, pointHoverRadius: 3, pointHitRadius: 8, tension: 0.1,
      })
    }
    return ds
  }

  const maxTime = cd.timestamps.length ? cd.timestamps[cd.timestamps.length - 1] : 0
  const yAxisWidth = isArm ? 72 : 56

  const baseOptions = (title: string): any => ({
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    parsing: false,
    scales: {
      x: { type: 'linear', min: 0, max: maxTime, title: { display: true, text: '时间 (s)' } },
      y: {
        title: { display: true, text: yTitle },
        afterFit(scale: any) {
          scale.width = yAxisWidth
        }
      }
    },
    plugins: {
      legend: { display: false },
      tooltip: { enabled: false },
      title: { display: true, text: title, position: 'top' as const, font: { size: 13 } },
    },
    interaction: { mode: 'nearest', axis: 'x', intersect: false },
  })

  chartL = new Chart(chartCanvasL.value, {
    type: 'line',
    data: { datasets: buildDatasets(0) },
    options: baseOptions(sideLabels[0]),
  })
  ;((chartL.options.plugins as any).timelineOverlay ??= {}).segments = normalizedTimelineSegments.value

  chartR = new Chart(chartCanvasR.value, {
    type: 'line',
    data: { datasets: buildDatasets(perSideCount) },
    options: baseOptions(sideLabels[1]),
  })
  ;((chartR.options.plugins as any).timelineOverlay ??= {}).segments = normalizedTimelineSegments.value

  chartCanvasL.value.style.cursor = 'crosshair'
  chartCanvasR.value.style.cursor = 'crosshair'
  drawChartOverlay()
}

const refreshMedia = async () => {
  if (!payload.value) return
  const objectIds = payload.value.media.filter((item) => item.refreshable).map((item) => item.objectId)
  if (!objectIds.length) return
  refreshingMedia.value = true
  try {
    const response = await refreshManualQcMedia(episodeId.value, { objectIds })
    const refreshed = new Map(response.media.map((item) => [item.objectId, item]))
    payload.value = {
      ...payload.value,
      media: payload.value.media.map((item) => {
        const next = refreshed.get(item.objectId)
        return next ? { ...item, ...next } : item
      })
    }
    await nextTick()
    await syncVideosToFrame()
    ElMessage.success('媒体预览已刷新')
  } catch (err) {
    ElMessage.error(formatError(err, '刷新媒体预览失败'))
    await loadContext()
  } finally {
    refreshingMedia.value = false
  }
}


const claim = async () => {
  claiming.value = true
  try {
    const response = await claimManualQc(episodeId.value)
    if (payload.value) {
      payload.value = {
        ...payload.value,
        reviewLock: response.reviewLock,
        episode: {
          ...payload.value.episode,
          qcStatus: 'in_review',
          reviewer: response.reviewLock.ownerName || payload.value.episode.reviewer
        }
      }
    }
    ElMessage.success('已认领当前质检任务')
    await loadContext()
  } catch (err) {
    ElMessage.error(formatError(err, '认领任务失败'))
    await loadContext()
  } finally {
    claiming.value = false
  }
}

const release = async () => {
  releasing.value = true
  try {
    await releaseManualQc(episodeId.value)
    ElMessage.success('已释放当前质检锁')
    await loadContext()
  } catch (err) {
    ElMessage.error(formatError(err, '释放质检锁失败'))
    await loadContext()
  } finally {
    releasing.value = false
  }
}

const stepFrame = async (delta: number) => {
  pauseAll()
  currentFrame.value = Math.max(0, Math.min(maxFrame.value, currentFrame.value + delta))
  await syncVideosToFrame()
}

const stepSeconds = async (deltaSeconds: number) => {
  await stepFrame(Math.round(deltaSeconds * fps.value))
}

const togglePlayback = async () => {
  if (playing.value) {
    pauseAll()
    return
  }
  try {
    await playAll()
  } catch (err) {
    pauseAll()
    ElMessage.error(formatError(err, '同步播放失败'))
  }
}

onMounted(loadContext)

watch(episodeId, () => {
  stopPlaybackLoop()
  currentFrame.value = 0
  result.value = 'pass'
  primaryReason.value = ''
  note.value = ''
  loadContext()
})

watch(currentFrame, async () => {
  if (syncingSlider.value || suppressFrameWatcher.value) return
  drawChartOverlay()
  if (playing.value) return
  await syncVideosToFrame()
})

watch(selectedVariant, async () => {
  pauseAll()
  await nextTick()
  await syncVideosToFrame()
})

watch(curveMode, () => {
  destroyChart()
  renderChart()
})

watch(normalizedTimelineSegments, () => {
  drawChartOverlay()
}, { deep: true })

watch(curveData, () => {
  drawChartOverlay()
})

onBeforeUnmount(() => {
  pauseAll()
  stopChartDragging()
  destroyChart()
})

onMounted(() => {
  window.addEventListener('mouseup', stopChartDragging)
})

onBeforeUnmount(() => {
  window.removeEventListener('mouseup', stopChartDragging)
})

const submit = async () => {
  if (result.value === 'fail' && !primaryReason.value) {
    ElMessage.warning('fail 结果必须填写主原因码')
    return
  }
  if (!reviewLock.value?.isMine) {
    ElMessage.warning('请先认领该任务后再提交')
    return
  }
  submitting.value = true
  try {
    const resp = await submitManualQc(episodeId.value, {
      result: result.value,
      primaryReason: primaryReason.value,
      note: note.value,
      version: reviewLock.value.version
    })

    if (isReviewer.value && resp.remainingCount === 0) {
      celebrating.value = true
      triggerCelebration(() => {
        celebrating.value = false
        celebrationDone.value = true
      })
      return
    }

    if (isReviewer.value && resp.nextEpisodeId) {
      ElMessage.success(`已提交，正在加载下一条...（剩余 ${resp.remainingCount} 条）`)
      setTimeout(() => {
        router.push(`/manual-qc/${resp.nextEpisodeId}`)
      }, 800)
      return
    }

    ElMessage.success('人工质检结果已提交')
    await loadContext()
  } catch (err) {
    ElMessage.error(formatError(err, '提交人工质检失败'))
    await loadContext()
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <AppLayout>
    <div class="manual-qc-grid enhanced" v-loading="loading">
      <section class="manual-main">
          <div class="qc-top-strip">
            <div>
              <el-tag type="warning" effect="dark">{{ episode?.qcStatus?.toUpperCase() || 'IN REVIEW' }}</el-tag>
            <h1>人工质检工作台</h1>
            <p>{{ episode?.batchName }} · {{ episode?.taskName }} · {{ episodeNumber }}</p>
          </div>
          <div class="lock-panel">
            <span>审核锁状态</span>
            <strong>{{ reviewLock?.ownerName || (episode?.reviewer && episode.reviewer !== '-' ? episode.reviewer : '-') }}</strong>
            <el-tag :type="lockTagType" effect="light">{{ lockLabel }}</el-tag>
            <small v-if="reviewLock?.expiresAt">锁到期时间 {{ reviewLock.expiresAt }}</small>
            <small v-else>认领后方可提交质检结果</small>
            <div class="lock-actions">
              <el-button type="primary" :loading="claiming" :disabled="Boolean(reviewLock?.isLocked && !reviewLock?.isMine)" @click="claim">
                {{ reviewLock?.isMine ? '重新认领' : '认领任务' }}
              </el-button>
              <el-button :loading="releasing" :disabled="!reviewLock?.isMine && !(isManager && reviewLock?.isLocked)" @click="release">{{ reviewLock?.isMine ? '释放锁' : '强制释放' }}</el-button>
            </div>
          </div>
        </div>

        <el-alert v-if="error" type="error" :closable="false" :title="error" />

        <el-card shadow="never" class="qc-card qc-stage-card">
          <div class="qc-stage-header">
            <div class="stage-tabs">
              <span class="active">{{ selectedVariant === 'rgb' ? 'RGB 三相机' : 'Depth 辅助' }}</span>
              <span>Telemetry</span>
              <span>Reason Code</span>
            </div>
            <div style="display:flex; gap:12px; align-items:center; flex-wrap:wrap;">
              <el-radio-group v-model="selectedVariant" size="small">
                <el-radio-button label="rgb" value="rgb">RGB Video</el-radio-button>
                <el-radio-button label="depth_colormap" value="depth_colormap">Depth Colormap</el-radio-button>
              </el-radio-group>
              <el-button size="small" :loading="refreshingMedia" :disabled="!media.some((item) => item.refreshable)" @click="refreshMedia">刷新预览</el-button>
            </div>
          </div>

          <div class="video-grid premium">
            <div v-for="item in mediaByVariant" :key="item.objectId" class="video-panel">
              <div class="camera-label">
                <span>{{ item.label }}</span>
                <b>{{ item.variant === 'depth_colormap' ? 'Depth Colormap' : 'RGB' }}</b>
              </div>
              <video
                :ref="setVideoRef(item.objectId)"
                class="video-placeholder"
                :class="{ depth: item.variant === 'depth_colormap' }"
                :src="item.previewUrl"
                playsinline
                preload="metadata"
                muted
                disablePictureInPicture
                @click.prevent
              />
              <div style="display:flex; justify-content:space-between; align-items:center; gap:12px; margin-top:8px; font-size:12px; color:#909399;">
                <span>{{ item.slot }} · expires {{ item.previewExpiresAt || '--' }}</span>
              </div>
            </div>
            <el-empty v-if="!mediaByVariant.length" description="当前无可播放媒体" />
          </div>
        </el-card>

        <el-card shadow="never" class="qc-card timeline-card">
          <div class="timeline-header">
            <div>
              <strong>Frame {{ currentFrame }} / {{ totalFrames }}</strong>
              <span>{{ progress }}% · 当前时间 {{ currentTimeSec.toFixed(2) }}s / {{ durationSec.toFixed(2) }}s · {{ fps.toFixed(2) }} fps</span>
              <small class="active-segment-note" :class="{ placeholder: !activeTimelineSegments.length }">
                {{ activeTimelineSegments.length
                  ? `当前异常段：${activeTimelineSegments.map((segment: any) => `${segment.startSec.toFixed(1)}-${segment.endSec.toFixed(1)}s ${segment.label}`).join("；")}`
                  : '当前异常段：--' }}
              </small>
            </div>
            <div class="player-actions">
              <el-button :disabled="!totalFrames" @click="stepSeconds(-1)">-1s</el-button>
              <el-button :disabled="!totalFrames" @click="stepFrame(-1)">上一帧</el-button>
              <el-button type="primary" :disabled="!totalFrames" @click="togglePlayback">{{ playing ? '暂停' : '播放' }}</el-button>
              <el-button :disabled="!totalFrames" @click="stepFrame(1)">下一帧</el-button>
              <el-button :disabled="!totalFrames" @click="stepSeconds(1)">+1s</el-button>
            </div>
          </div>
          <el-slider
            v-model="currentFrame"
            :max="maxFrame"
            @change="async () => {
              syncingSlider = true
              pauseAll()
              await syncVideosToFrame()
              syncingSlider = false
            }"
          />
          <div class="segment-row">
            <div
              v-for="segment in timelineSegments"
              :key="segmentKey(segment)"
              class="segment-chip clickable"
              :class="[segment.level, { current: activeTimelineSegmentIds.has(segmentKey(segment)) }]"
              @click="jumpToSegment(segment)"
            >
              {{ segmentStartSec(segment).toFixed(1) }}-{{ segmentEndSec(segment).toFixed(1) }}s · {{ segment.label }}
            </div>
          </div>
        </el-card>

        <el-card shadow="never" class="qc-card" style="margin-top: 18px">
          <template #header>
            <div style="display:flex; justify-content:space-between; align-items:center">
              <span>遥操作曲线联动视图</span>
              <el-radio-group v-model="curveMode" size="small" :disabled="!curveData">
                <el-radio-button value="arm">机械臂 ({{ Math.round((curveData?.armDims || 0) / 2) }} 维)</el-radio-button>
                <el-radio-button v-if="curveData?.handDims" value="hand">灵巧手 ({{ curveData?.handDims || 0 }} 维)</el-radio-button>
              </el-radio-group>
            </div>
          </template>
          <div v-if="curveError" style="height: 200px; display:flex; align-items:center; justify-content:center; color: #909399; font-size: 13px">
            {{ curveError }}
          </div>
          <div v-else-if="!curveData" style="height: 200px; display:flex; align-items:center; justify-content:center; color: #909399; font-size: 13px">
            加载关节位置数据中...
          </div>
          <div v-else>
            <div class="chart-legend-panel">
              <div v-for="item in chartLegendItems" :key="item.key" class="chart-legend-item">
                <span class="chart-legend-swatch" :style="{ borderColor: item.color }" :class="{ dashed: item.dashed }"></span>
                <span>{{ item.label }}</span>
              </div>
            </div>
            <div class="chart-canvas-shell" style="height: 280px; position: relative; margin-bottom: 12px">
              <div
                v-show="chartPlaybackCursorVisible"
                class="chart-cursor-line playback"
                :style="{ left: `${chartPlaybackCursorLeftPx}px`, top: `${chartCursorTopPx}px`, height: `${chartCursorHeightPx}px` }"
              ></div>
              <div
                v-show="chartHoverCursorVisible"
                class="chart-cursor-line hover"
                :style="{ left: `${chartHoverCursorLeftPx}px`, top: `${chartCursorTopPx}px`, height: `${chartCursorHeightPx}px` }"
              ></div>
              <canvas
                ref="chartCanvasL"
                @mousemove="e => handleChartPointerMove(e, chartL, chartCanvasL)"
                @mouseleave="handleChartPointerLeave"
                @mousedown="e => handleChartPointerDown(e, chartL, chartCanvasL)"
              ></canvas>
            </div>
            <div class="chart-canvas-shell" style="height: 280px; position: relative">
              <div
                v-show="chartPlaybackCursorVisible"
                class="chart-cursor-line playback"
                :style="{ left: `${chartPlaybackCursorLeftPxR}px`, top: `${chartCursorTopPx}px`, height: `${chartCursorHeightPx}px` }"
              ></div>
              <div
                v-show="chartHoverCursorVisible"
                class="chart-cursor-line hover"
                :style="{ left: `${chartHoverCursorLeftPxR}px`, top: `${chartCursorTopPx}px`, height: `${chartCursorHeightPx}px` }"
              ></div>
              <canvas
                ref="chartCanvasR"
                @mousemove="e => handleChartPointerMove(e, chartR, chartCanvasR)"
                @mouseleave="handleChartPointerLeave"
                @mousedown="e => handleChartPointerDown(e, chartR, chartCanvasR)"
              ></canvas>
            </div>
          </div>
        </el-card>

      </section>

      <aside class="manual-side sticky-side">
        <el-card shadow="never" class="qc-card score-card">
          <template #header>{{ l3V2Report ? 'RDDQF 训练质量评分' : 'Episode 质量评分' }}</template>

          <div v-if="l3V2Report" class="l3v2-panel">
            <div class="score-ring-wrapper">
              <div class="score-ring" :class="trainingQualityLevel">
                <svg viewBox="0 0 120 120" class="score-ring-svg">
                  <circle cx="60" cy="60" r="52" fill="none" stroke="#e2e8f0" stroke-width="10" />
                  <circle cx="60" cy="60" r="52" fill="none" stroke="currentColor" stroke-width="10"
                    stroke-linecap="round" transform="rotate(-90 60 60)"
                    :stroke-dasharray="2 * Math.PI * 52"
                    :stroke-dashoffset="2 * Math.PI * 52 * (1 - scoreRingPercent / 100)" />
                </svg>
                <div class="score-ring-text">
                  <strong>{{ trainingQualityScore?.toFixed(1) || '--' }}</strong>
                  <span>{{ l3V2Report.scoreLabel }}</span>
                </div>
              </div>
              <AiAssistantAnchor
                class="score-ring-ai-anchor"
                :status="ai.status.value"
                :active="ai.isOpen.value"
                @open="handleAiOpen"
                @close="ai.close"
              />
              <AiAssistantPanel
                v-if="ai.isOpen.value"
                :messages="ai.messages.value"
                :is-thinking="ai.isThinking.value"
                :provider-status="ai.providerStatus.value"
                @send="handleAiSend"
                @close="ai.close"
              />
            </div>
            <p class="l3v2-summary">{{ l3V2Report.summary }}</p>
            <div class="telemetry-profile">
              <span>{{ l3V2Report.version }}</span>
              <span>{{ l3V2Report.telemetryProfile.armDims }} arm DOF</span>
              <span>{{ l3V2Report.telemetryProfile.handDims }} hand DOF</span>
            </div>

            <div class="quality-scroll">
              <div v-for="dimension in qualityDimensions" :key="dimension.dimensionId" class="quality-dimension" :class="dimension.level">
                <div class="quality-header">
                  <div>
                    <strong>{{ dimension.labelZh }}</strong>
                    <small>{{ dimension.label }}</small>
                  </div>
                  <el-tag :type="severityTagType(dimension.level)" effect="dark">{{ dimension.score.toFixed(1) }}</el-tag>
                </div>
                <p>{{ dimension.summary }}</p>
                <div class="evidence-list">
                  <div v-for="evidence in dimension.evidenceGroups" :key="evidence.evidenceId" class="evidence-item" :class="evidence.level">
                    <div class="evidence-header">
                      <span>{{ evidence.label }}</span>
                      <b>{{ evidence.score.toFixed(1) }}</b>
                    </div>
                    <div v-for="metric in evidence.metrics" :key="metric.metricId" class="metric-mini">
                      <span>{{ metric.metricId }} · {{ metric.name }}</span>
                      <el-tooltip :content="metric.description" placement="top" effect="light">
                        <el-icon class="metric-help-icon inline"><QuestionFilled /></el-icon>
                      </el-tooltip>
                      <b>{{ metric.valueText }}</b>
                    </div>
                  </div>
                </div>
              </div>

              <div v-if="diagnosticMetrics.length" class="diagnostic-block">
                <div class="diagnostic-title">Execution Diagnostics（不进入训练质量总分）</div>
                <div v-for="metric in diagnosticMetrics" :key="metric.metricId" class="metric-mini diagnostic">
                  <span>{{ metric.metricId }} · {{ metric.name }}</span>
                  <b>{{ metric.valueText }}</b>
                </div>
              </div>
            </div>
          </div>

          <div v-else>
            <el-empty description="L3 quality data unavailable" />
          </div>
        </el-card>

        <el-card shadow="never" class="qc-card">
          <template #header>质检结论提交</template>
          <el-alert
            v-if="!reviewLock?.isMine"
            :title="reviewLock?.isLocked ? `当前任务已由 ${reviewLock.ownerName || '其他审核员'} 认领` : '请先认领任务后再提交结果'"
            type="warning"
            :closable="false"
            style="margin-bottom: 12px"
          />
          <QcReasonPicker v-model:result="result" v-model:primary-reason="primaryReason" />
          <div class="field-label">审核备注</div>
          <el-input v-model="note" type="textarea" :rows="4" placeholder="填写遮挡、动作异常、任务失败等人工判断依据" />
          <div class="submit-row split">
            <el-button @click="note = ''">清空备注</el-button>
            <el-button @click="router.push(isReviewer ? '/reviewer' : '/database')">{{ isReviewer ? '返回看板' : '返回总库' }}</el-button>
            <el-button type="primary" :disabled="!canSubmit" :loading="submitting" @click="submit">提交结果</el-button>
          </div>
        </el-card>

        <el-card shadow="never" class="qc-card">
          <template #header>Revision 历史</template>
          <div v-for="revision in qcRevisions" :key="revision.revisionNo" class="revision-item">
            <strong>#{{ revision.revisionNo }} · {{ revision.result }}</strong>
            <span>{{ revision.operator }} · {{ revision.time }}</span>
            <p>{{ revision.note }}</p>
          </div>
        </el-card>
      </aside>

      <div v-if="celebrating" class="celebration-overlay">
        <div class="celebration-text">正在结算...</div>
      </div>

      <div v-if="celebrationDone" class="celebration-overlay celebration-done">
        <div class="celebration-text">你已完成今日全部质检任务！</div>
        <div class="celebration-sub">感谢你的辛勤工作</div>
        <el-button type="primary" size="large" style="margin-top: 24px" @click="router.push('/reviewer')">返回个人看板</el-button>
      </div>
    </div>
  </AppLayout>
</template>

<style scoped>
.metric-copy {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}

.metric-label-row {
  position: relative;
  width: 100%;
  padding-right: 16px;
}

.metric-item :deep(.metric-help-icon) {
  position: absolute;
  top: -2px;
  right: 0;
  color: #94a3b8;
  cursor: help;
  font-size: 13px;
}

.metric-scroll {
  max-height: 420px;
  overflow-y: auto;
  padding-right: 4px;
}

.metric-scroll::-webkit-scrollbar {
  width: 5px;
}

.metric-scroll::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 3px;
}

.metric-scroll::-webkit-scrollbar-track {
  background: transparent;
}

.celebration-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: rgba(15, 23, 42, 0.92);
}

.celebration-text {
  color: #fff;
  font-size: 36px;
  font-weight: 900;
  letter-spacing: -0.5px;
}

.celebration-sub {
  margin-top: 8px;
  color: #94a3b8;
  font-size: 18px;
}

.lock-panel {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border-radius: 16px;
  background: transparent;
  position: relative;
  z-index: 2;
}

.lock-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.active-segment-note {
  display: block;
  margin-top: 6px;
  color: #b45309;
  font-size: 12px;
  font-weight: 600;
  min-height: 18px;
}

.active-segment-note.placeholder {
  color: #94a3b8;
}

.segment-chip.clickable {
  cursor: pointer;
  transition: transform 0.12s ease, box-shadow 0.12s ease;
}

.segment-chip.clickable:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.12);
}

.segment-chip.current {
  outline: 2px solid rgba(17, 24, 39, 0.18);
  outline-offset: 1px;
  box-shadow: 0 6px 16px rgba(15, 23, 42, 0.12);
}

.chart-legend-panel {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 10px;
  margin-bottom: 10px;
  max-height: 72px;
  overflow-y: auto;
  padding-right: 4px;
}

.chart-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: #475569;
  white-space: nowrap;
}

.chart-legend-swatch {
  width: 18px;
  height: 0;
  border-top: 2px solid currentColor;
  display: inline-block;
}

.chart-legend-swatch.dashed {
  border-top-style: dashed;
}

.chart-canvas-shell {
  position: relative;
  width: 100%;
  height: 100%;
}

.chart-cursor-line {
  position: absolute;
  width: 2px;
  margin-left: -1px;
  pointer-events: none;
  z-index: 3;
}

.chart-cursor-line.playback {
  background: rgba(59, 130, 246, 0.7);
}

.chart-cursor-line.hover {
  background: #111827;
  opacity: 0.95;
}

.score-ring-wrapper {
  position: relative;
}

.score-ring-ai-anchor {
  position: absolute;
  top: -2px;
  right: 36px;
  z-index: 10;
}

.l3v2-panel .score-ring.good {
  color: #16a34a;
}

.l3v2-panel .score-ring.warn {
  color: #f59e0b;
}

.l3v2-panel .score-ring.bad {
  color: #ef4444;
}

.l3v2-summary {
  margin: 10px 0 12px;
  color: #64748b;
  font-size: 13px;
  line-height: 1.55;
}

.telemetry-profile {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 12px;
}

.telemetry-profile span {
  padding: 3px 7px;
  border-radius: 999px;
  background: #f1f5f9;
  color: #475569;
  font-size: 11px;
}

.quality-scroll {
  max-height: 560px;
  overflow-y: auto;
  padding-right: 4px;
}

.quality-dimension {
  border: 1px solid #e5e7eb;
  border-left-width: 4px;
  border-radius: 12px;
  padding: 12px;
  margin-bottom: 12px;
  background: #fff;
}

.quality-dimension.good { border-left-color: #67c23a; }
.quality-dimension.warn { border-left-color: #e6a23c; }
.quality-dimension.bad { border-left-color: #f56c6c; }

.quality-header, .evidence-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
}

.quality-header small {
  display: block;
  color: #94a3b8;
  font-size: 11px;
  margin-top: 2px;
}

.quality-dimension p {
  margin: 8px 0 10px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.evidence-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.evidence-item {
  padding: 9px;
  border-radius: 10px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
}

.evidence-item.warn { background: #fffbeb; border-color: #fde68a; }
.evidence-item.bad { background: #fef2f2; border-color: #fecaca; }

.evidence-header span {
  font-weight: 700;
  font-size: 12px;
  color: #334155;
}

.evidence-header b {
  color: #0f172a;
  font-size: 12px;
}

.metric-mini {
  display: grid;
  grid-template-columns: 1fr auto auto;
  align-items: center;
  gap: 6px;
  margin-top: 7px;
  font-size: 11px;
  color: #64748b;
}

.metric-mini b {
  color: #0f172a;
  font-size: 12px;
}

.metric-help-icon.inline {
  position: static !important;
  font-size: 12px;
  color: #94a3b8;
}

.diagnostic-block {
  margin-top: 14px;
  padding: 10px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px dashed #cbd5e1;
}

.diagnostic-title {
  font-size: 12px;
  font-weight: 800;
  color: #475569;
}

.metric-mini.diagnostic {
  grid-template-columns: 1fr auto;
}

</style>
