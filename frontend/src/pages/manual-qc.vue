<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import AppLayout from '../components/AppLayout.vue'
import QcReasonPicker from '../components/QcReasonPicker.vue'
import { claimManualQc, fetchManualQcContext, releaseManualQc, submitManualQc, type ManualQcContext } from '../api/client'

const route = useRoute()
const router = useRouter()
const result = ref<'pass' | 'fail'>('pass')
const primaryReason = ref('')
const currentFrame = ref(426)
const playing = ref(false)
const depthMode = ref(false)
const note = ref('')
const loading = ref(true)
const submitting = ref(false)
const claiming = ref(false)
const releasing = ref(false)
const error = ref('')
const payload = ref<ManualQcContext | null>(null)

const episodeId = computed(() => String(route.params.id))
const totalFrames = computed(() => payload.value?.episode.frameCount ?? 1269)
const progress = computed(() => Math.round((currentFrame.value / totalFrames.value) * 100))
const metricCards = computed(() => payload.value?.metrics ?? [])
const timelineSegments = computed(() => payload.value?.timelineSegments ?? [])
const qcRevisions = computed(() => payload.value?.revisions ?? [])
const episode = computed(() => payload.value?.episode)
const reviewLock = computed(() => payload.value?.reviewLock)
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

const loadContext = async () => {
  loading.value = true
  error.value = ''
  try {
    payload.value = await fetchManualQcContext(episodeId.value)
    currentFrame.value = Math.min(426, totalFrames.value)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载人工质检上下文失败'
  } finally {
    loading.value = false
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
    ElMessage.error(err instanceof Error ? err.message : '认领任务失败')
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
    ElMessage.error(err instanceof Error ? err.message : '释放质检锁失败')
    await loadContext()
  } finally {
    releasing.value = false
  }
}

onMounted(loadContext)

onBeforeUnmount(() => {
  if (!reviewLock.value?.isMine || submitting.value || releasing.value) {
    return
  }
  void releaseManualQc(episodeId.value)
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
    await submitManualQc(episodeId.value, {
      result: result.value,
      primaryReason: primaryReason.value,
      note: note.value,
      version: reviewLock.value.version
    })
    ElMessage.success('人工质检结果已提交')
    await loadContext()
    router.push('/qc-history')
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '提交人工质检失败')
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
            <p>{{ episode?.id }} · {{ episode?.taskName }} · {{ episode?.batchId }} · processed-ready</p>
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
              <el-button :loading="releasing" :disabled="!reviewLock?.isMine" @click="release">释放锁</el-button>
            </div>
          </div>
        </div>

        <el-alert v-if="error" type="error" :closable="false" :title="error" />

        <el-card shadow="never" class="qc-stage-card">
          <div class="qc-stage-header">
            <div class="stage-tabs">
              <span class="active">RGB 三相机</span>
              <span :class="{ active: depthMode }">Depth 辅助</span>
              <span>Telemetry</span>
              <span>Reason Code</span>
            </div>
            <el-switch v-model="depthMode" active-text="Depth Colormap" inactive-text="RGB Video" />
          </div>

          <div class="video-grid premium">
            <div v-for="camera in ['Top Camera', 'Left Wrist', 'Right Wrist']" :key="camera" class="video-panel">
              <div class="camera-label">
                <span>{{ camera }}</span>
                <b>{{ depthMode ? 'Depth Colormap' : 'RGB' }}</b>
              </div>
              <div class="video-placeholder" :class="{ depth: depthMode }">
                <span>{{ depthMode ? 'Depth Preview' : 'Synchronized Video' }}</span>
                <small>frame {{ currentFrame }} · 30fps · 640×480</small>
              </div>
            </div>
          </div>
        </el-card>

        <el-card shadow="never" class="timeline-card premium-card">
          <div class="timeline-header">
            <div>
              <strong>Frame {{ currentFrame }} / {{ totalFrames }}</strong>
              <span>{{ progress }}% · 当前时间 {{ (currentFrame / 30).toFixed(2) }}s</span>
            </div>
            <div class="player-actions">
              <el-button @click="currentFrame = Math.max(0, currentFrame - 30)">-1s</el-button>
              <el-button @click="currentFrame = Math.max(0, currentFrame - 1)">上一帧</el-button>
              <el-button type="primary" @click="playing = !playing">{{ playing ? '暂停' : '播放' }}</el-button>
              <el-button @click="currentFrame = Math.min(totalFrames, currentFrame + 1)">下一帧</el-button>
              <el-button @click="currentFrame = Math.min(totalFrames, currentFrame + 30)">+1s</el-button>
            </div>
          </div>
          <el-slider v-model="currentFrame" :max="totalFrames" />
          <div class="segment-row">
            <div v-for="segment in timelineSegments" :key="segment.label" class="segment-chip" :class="segment.level">
              {{ segment.start }}-{{ segment.end }}s · {{ segment.label }}
            </div>
          </div>
        </el-card>

        <el-row :gutter="18">
          <el-col :span="14">
            <el-card shadow="never" class="premium-card">
              <template #header>遥测曲线联动视图</template>
              <div class="telemetry-chart advanced">
                <div v-for="i in 42" :key="i" class="bar" :class="{ alert: i > 24 && i < 30 }" :style="{ height: `${30 + ((i * 17) % 90)}px` }" />
              </div>
              <div class="chart-legend"><span>qpos/actions tracking error</span><span>红色段：tracking_error 超阈值</span></div>
            </el-card>
          </el-col>
          <el-col :span="10">
            <el-card shadow="never" class="premium-card">
              <template #header>异常段核查清单</template>
              <el-check-tag v-for="segment in timelineSegments" :key="segment.label" :checked="segment.level === 'warn'" :type="segment.level === 'bad' ? 'danger' : 'warning'">
                {{ segment.start }}-{{ segment.end }}s {{ segment.label }}
              </el-check-tag>
            </el-card>
          </el-col>
        </el-row>
      </section>

      <aside class="manual-side sticky-side">
        <el-card shadow="never" class="premium-card score-card">
          <template #header>Episode 质量评分</template>
          <div class="score-ring"><strong>{{ metricCards[0]?.value || '--' }}</strong><span>{{ metricCards[0]?.label || 'Q_motion' }}</span></div>
          <div class="metric-list compact-list">
            <div v-for="metric in metricCards" :key="metric.key" class="metric-item" :class="metric.level">
              <div><strong>{{ metric.label }}</strong><span>{{ metric.description }}</span></div>
              <b>{{ metric.value }}</b>
            </div>
          </div>
        </el-card>

        <el-card shadow="never" class="premium-card">
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
            <el-button @click="router.push('/database')">返回总库</el-button>
            <el-button type="primary" :disabled="!canSubmit" :loading="submitting" @click="submit">提交结果</el-button>
          </div>
        </el-card>

        <el-card shadow="never" class="premium-card">
          <template #header>Revision 历史</template>
          <div v-for="revision in qcRevisions" :key="revision.revisionNo" class="revision-item">
            <strong>#{{ revision.revisionNo }} · {{ revision.result }}</strong>
            <span>{{ revision.operator }} · {{ revision.time }}</span>
            <p>{{ revision.note }}</p>
          </div>
        </el-card>
      </aside>
    </div>
  </AppLayout>
</template>
