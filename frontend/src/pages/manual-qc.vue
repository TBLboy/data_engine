<script setup lang="ts">
import { QuestionFilled } from '@element-plus/icons-vue'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import { ElMessage } from 'element-plus'
import AppLayout from '../components/AppLayout.vue'
import QcReasonPicker from '../components/QcReasonPicker.vue'
import { claimManualQc, downloadManualQcObject, fetchManualQcContext, refreshManualQcMedia, releaseManualQc, submitManualQc, type ManualQcContext } from '../api/client'
import { useSessionStore } from '../stores/session'
import { triggerCelebration } from '../composables/useCelebration'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
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
const downloadingObjectId = ref('')
const error = ref('')
const payload = ref<ManualQcContext | null>(null)
const selectedVariant = ref<'rgb' | 'depth_colormap'>('rgb')
const syncingSlider = ref(false)
const celebrating = ref(false)
const celebrationDone = ref(false)
const videoRefs = ref<Record<string, HTMLVideoElement | null>>({})
const isReviewer = computed(() => session.user?.role === 'reviewer')
const isManager = computed(() => session.user?.role === 'admin' || session.user?.role === 'qc_manager')
let playbackLoopId: number | null = null

const episodeId = computed(() => String(route.params.id))
const fps = computed(() => payload.value?.episode.fps || 30)
const totalFrames = computed(() => Math.max(0, payload.value?.episode.frameCount ?? 0))
const durationSec = computed(() => payload.value?.episode.durationSec ?? 0)
const maxFrame = computed(() => Math.max(totalFrames.value - 1, 0))
const progress = computed(() => (maxFrame.value ? Math.round((currentFrame.value / maxFrame.value) * 100) : 0))
const currentTimeSec = computed(() => currentFrame.value / fps.value)
const metricCards = computed(() => payload.value?.metrics ?? [])
const sortedMetricCards = computed(() => {
  const order: Record<string, number> = { bad: 0, warn: 1, good: 2 }
  return [...metricCards.value].sort((a, b) => (order[a.level] ?? 3) - (order[b.level] ?? 3))
})
// 评分环固定展示综合质量分 Q_motion，而非随严重度排序变化的首个指标
const scoreMetric = computed(() => metricCards.value.find((metric) => metric.key === 'q_motion') ?? sortedMetricCards.value[0] ?? null)
const timelineSegments = computed(() => payload.value?.timelineSegments ?? [])
const qcRevisions = computed(() => payload.value?.revisions ?? [])
const episode = computed(() => payload.value?.episode)
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
  } catch (err) {
    error.value = formatError(err, '加载人工质检上下文失败')
  } finally {
    loading.value = false
  }
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

const downloadMedia = async (objectId: string) => {
  downloadingObjectId.value = objectId
  try {
    const blob = await downloadManualQcObject(episodeId.value, objectId)
    const link = document.createElement('a')
    const url = URL.createObjectURL(blob)
    link.href = url
    const mime = media.value.find((item) => item.objectId === objectId)?.mimeType ?? ''
    const ext = mime.includes('mp4') ? 'mp4' : (mime.split('/')[1] || 'bin')
    link.download = `${episodeId.value}-${objectId}.${ext}`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    ElMessage.success('对象下载已开始')
  } catch (err) {
    ElMessage.error(formatError(err, '对象下载失败'))
  } finally {
    downloadingObjectId.value = ''
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
  if (syncingSlider.value) return
  await syncVideosToFrame()
})

watch(selectedVariant, async () => {
  pauseAll()
  await nextTick()
  await syncVideosToFrame()
})

onBeforeUnmount(() => {
  pauseAll()
})

onBeforeRouteLeave(async () => {
  // 离开质检工作台时可靠释放自己的审核锁，避免弃审任务被锁死到 20 分钟过期。
  // 同路由 :id 变化（流水线自动跳转）不会触发本守卫，且提交时后端已释放锁。
  if (reviewLock.value?.isMine && !submitting.value && !releasing.value) {
    try {
      await releaseManualQc(episodeId.value)
    } catch {
      // best-effort：释放失败不阻塞导航，后端锁过期兜底
    }
  }
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
            <p>{{ episode?.id }} · {{ episode?.taskName }} · {{ episode?.batchId }} · MinIO indexed</p>
          </div>
          <div class="lock-panel">
            <span>审核锁状态</span>
            <strong>{{ reviewLock?.ownerName || (episode?.reviewer && episode.reviewer !== '-' ? episode.reviewer : '待认领') }}</strong>
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
                @click.prevent
              />
              <div style="display:flex; justify-content:space-between; align-items:center; gap:12px; margin-top:8px; font-size:12px; color:#909399;">
                <span>{{ item.slot }} · expires {{ item.previewExpiresAt || '--' }}</span>
                <el-button link type="primary" :loading="downloadingObjectId === item.objectId" @click="downloadMedia(item.objectId)">下载对象</el-button>
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
            <div v-for="segment in timelineSegments" :key="segment.label" class="segment-chip" :class="segment.level">
              {{ segment.start }}-{{ segment.end }}s · {{ segment.label }}
            </div>
          </div>
        </el-card>

        <el-row :gutter="18">
          <el-col :span="14">
            <el-card shadow="never" class="qc-card">
              <template #header>遥测曲线联动视图</template>
              <div class="telemetry-chart advanced">
                <div v-for="i in 42" :key="i" class="bar" :class="{ alert: i > 24 && i < 30 }" :style="{ height: `${30 + ((i * 17) % 90)}px` }" />
              </div>
              <div class="chart-legend"><span>qpos/actions tracking error</span><span>红色段：tracking_error 超阈值</span></div>
            </el-card>
          </el-col>
          <el-col :span="10">
            <el-card shadow="never" class="qc-card">
              <template #header>异常段核查清单</template>
              <el-check-tag v-for="segment in timelineSegments" :key="segment.label" :checked="segment.level === 'warn'" :type="segment.level === 'bad' ? 'danger' : 'warning'">
                {{ segment.start }}-{{ segment.end }}s {{ segment.label }}
              </el-check-tag>
            </el-card>
          </el-col>
        </el-row>
      </section>

      <aside class="manual-side sticky-side">
        <el-card shadow="never" class="qc-card score-card">
          <template #header>Episode 质量评分</template>
          <div class="score-ring"><strong>{{ scoreMetric?.value || '--' }}</strong><span>{{ scoreMetric?.label || 'Q_motion' }}</span></div>
          <div class="metric-scroll">
            <div class="metric-list compact-list">
              <div v-for="metric in sortedMetricCards" :key="metric.key" class="metric-item" :class="metric.level">
              <div class="metric-copy">
                <div class="metric-label-row">
                  <strong>{{ metric.label }}</strong>
                  <el-tooltip :content="metric.description" placement="top" effect="light">
                    <el-icon class="metric-help-icon"><QuestionFilled /></el-icon>
                  </el-tooltip>
                </div>
              </div>
              <b>{{ metric.value }}</b>
            </div>
          </div>
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
</style>
