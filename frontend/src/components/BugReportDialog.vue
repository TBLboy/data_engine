<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { createBugReport } from '../api/client'

const DRAFT_KEY = 'bug-report-draft'

interface Draft {
  description: string
  imageDataUrls: string[]
}

const props = defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  submitted: []
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value)
})

const description = ref('')
const imageFiles = ref<File[]>([])
const imagePreviewUrls = ref<string[]>([])
const submitting = ref(false)
const hasDraft = ref(false)

const dataUrlToFile = (dataUrl: string): File => {
  const arr = dataUrl.split(',')
  const mime = arr[0].match(/:(.*?);/)?.[1] ?? 'image/png'
  const bstr = atob(arr[1])
  const n = bstr.length
  const u8arr = new Uint8Array(n)
  for (let i = 0; i < n; i++) u8arr[i] = bstr.charCodeAt(i)
  const ext = mime.split('/')[1] || 'png'
  return new File([u8arr], `draft.${ext}`, { type: mime })
}

const loadDraft = () => {
  try {
    const raw = localStorage.getItem(DRAFT_KEY)
    if (!raw) { hasDraft.value = false; return }
    const draft: Draft = JSON.parse(raw)
    if (!draft.description && !draft.imageDataUrls?.length) { hasDraft.value = false; return }
    hasDraft.value = true
    description.value = draft.description || ''
    const files = (draft.imageDataUrls || []).map(dataUrlToFile)
    imageFiles.value = files
    imagePreviewUrls.value = files.map((f) => URL.createObjectURL(f))
  } catch {
    hasDraft.value = false
  }
}

const saveDraft = () => {
  const draft: Draft = {
    description: description.value,
    imageDataUrls: [],
  }
  // Convert current File objects to base64 data URLs for localStorage
  const readers: Promise<string>[] = imageFiles.value.map(
    (f) =>
      new Promise<string>((resolve) => {
        const reader = new FileReader()
        reader.onload = () => resolve(reader.result as string)
        reader.readAsDataURL(f)
      })
  )
  Promise.all(readers).then((urls) => {
    draft.imageDataUrls = urls
    localStorage.setItem(DRAFT_KEY, JSON.stringify(draft))
  })
}

const clearDraft = () => localStorage.removeItem(DRAFT_KEY)

const revokePreviews = () => {
  for (const url of imagePreviewUrls.value) URL.revokeObjectURL(url)
}

const resetForm = () => {
  description.value = ''
  revokePreviews()
  imageFiles.value = []
  imagePreviewUrls.value = []
}

const appendImageFile = (file: File) => {
  imageFiles.value = [...imageFiles.value, file]
  imagePreviewUrls.value = [...imagePreviewUrls.value, URL.createObjectURL(file)]
}

const removeImage = (index: number) => {
  const files = [...imageFiles.value]
  const urls = [...imagePreviewUrls.value]
  URL.revokeObjectURL(urls[index])
  files.splice(index, 1)
  urls.splice(index, 1)
  imageFiles.value = files
  imagePreviewUrls.value = urls
}

const handlePaste = (event: ClipboardEvent) => {
  const items = Array.from(event.clipboardData?.items ?? [])
  const imageItems = items.filter((item) => item.type.startsWith('image/'))
  if (!imageItems.length) return
  let added = 0
  for (const item of imageItems) {
    const file = item.getAsFile()
    if (!file) continue
    appendImageFile(file)
    added++
  }
  if (added) ElMessage.success(`已粘贴 ${added} 张截图`)
}

const handleFileInput = (event: Event) => {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  for (const file of files) appendImageFile(file)
  input.value = ''
  if (files.length) ElMessage.success(`已添加 ${files.length} 张截图`)
}

const stash = async () => {
  if (!description.value.trim() && !imageFiles.value.length) {
    visible.value = false
    return
  }
  await saveDraft()
  ElMessage.success('已暂存草稿')
  visible.value = false
}

const submit = async () => {
  if (!description.value.trim() && !imageFiles.value.length) {
    ElMessage.warning('请至少填写描述或粘贴一张截图')
    return
  }
  submitting.value = true
  try {
    await createBugReport({
      description: description.value.trim(),
      imageFiles: imageFiles.value.length ? [...imageFiles.value] : undefined,
    })
    ElMessage.success('BUG 提交成功')
    clearDraft()
    hasDraft.value = false
    visible.value = false
    emit('submitted')
    resetForm()
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : 'BUG 提交失败')
  } finally {
    submitting.value = false
  }
}

const cancel = () => {
  visible.value = false
}

watch(() => props.modelValue, (next) => {
  if (next) {
    loadDraft()
  } else {
    revokePreviews()
    imageFiles.value = []
    imagePreviewUrls.value = []
  }
})

onMounted(() => {
  if (props.modelValue) loadDraft()
})
</script>

<template>
  <el-dialog v-model="visible" title="BUG提交" width="640px" destroy-on-close>
    <div class="bug-submit-form" @paste="handlePaste">
      <el-alert v-if="hasDraft" type="warning" :closable="false" show-icon>
        已恢复上次暂存的草稿内容，点击暂存可更新草稿，提交成功后草稿自动清除。
      </el-alert>
      <el-alert v-else type="info" :closable="false" show-icon>
        可直接在此窗口内 Ctrl+V / Cmd+V 粘贴截图（支持多张），再补充问题描述后提交。
      </el-alert>

      <el-input
        v-model="description"
        type="textarea"
        :rows="6"
        maxlength="5000"
        show-word-limit
        placeholder="请描述你遇到的问题、复现步骤、页面位置或异常现象。"
      />

      <div class="bug-image-box">
        <div class="bug-image-header">
          <span class="bug-image-title">截图（可选，{{ imagePreviewUrls.length }} 张）</span>
          <label class="add-image-btn">
            + 选择图片
            <input type="file" accept="image/png,image/jpeg,image/webp" multiple hidden @change="handleFileInput" />
          </label>
        </div>

        <div v-if="imagePreviewUrls.length" class="bug-image-grid">
          <div v-for="(url, idx) in imagePreviewUrls" :key="url" class="bug-image-item">
            <img :src="url" alt="BUG截图预览" />
            <el-button class="remove-image-btn" type="danger" size="small" circle @click="removeImage(idx)">×</el-button>
          </div>
        </div>
        <div v-else class="bug-image-placeholder">
          在此弹窗内直接 Ctrl+V / Cmd+V 粘贴截图，或点击上方选择图片
        </div>
      </div>
    </div>

    <template #footer>
      <el-button @click="cancel">取消</el-button>
      <el-button plain @click="stash">暂存</el-button>
      <el-button type="primary" :loading="submitting" @click="submit">提交</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.bug-submit-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.bug-image-box {
  border: 1px dashed #cbd5e1;
  border-radius: 12px;
  padding: 12px;
  background: #f8fafc;
}

.bug-image-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.bug-image-title {
  font-size: 13px;
  color: #475569;
}

.add-image-btn {
  font-size: 13px;
  color: #2563eb;
  cursor: pointer;
}

.add-image-btn:hover {
  text-decoration: underline;
}

.bug-image-placeholder {
  min-height: 100px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #64748b;
  text-align: center;
}

.bug-image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 10px;
}

.bug-image-item {
  position: relative;
  aspect-ratio: 1;
  border-radius: 8px;
  overflow: hidden;
  background: #e2e8f0;
}

.bug-image-item img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.remove-image-btn {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 22px;
  height: 22px;
  font-size: 14px;
  padding: 0;
}
</style>
