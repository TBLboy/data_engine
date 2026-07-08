<template>
  <section class="ai-panel is-open" aria-label="AI 质检助手面板">
    <header class="panel-header">
      <span class="panel-mini-core" aria-hidden="true" />
      <div>
        <h3 class="panel-title">AI 质检助手</h3>
        <p class="panel-subtitle">已接入当前 episode 上下文 · {{ providerStatusText }}</p>
      </div>
      <button class="panel-close" aria-label="关闭" @click="$emit('close')">×</button>
    </header>

    <div class="panel-notice">AI 解读仅解释自动质检结果，不代替人工 pass/fail 结论。</div>

    <div class="quick-actions">
      <button v-for="action in quickActions" :key="action" @click="$emit('send', action)">{{ action }}</button>
    </div>

    <div ref="messagesEl" class="messages">
      <div v-for="message in messages" :key="message.id" class="msg" :class="message.role">
        <div class="bubble">{{ message.content }}</div>
      </div>
      <div v-if="isThinking" class="msg assistant">
        <div class="bubble"><span class="typing"><i/><i/><i/></span> {{ streamPhaseText }}</div>
      </div>
    </div>

    <div class="panel-input">
      <input v-model="draft" placeholder="向 AI 询问当前 episode 的检测结果..." @keydown.enter="submit" />
      <button @click="submit">发送</button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick } from 'vue'

export interface AiMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
}

const props = defineProps<{
  messages: AiMessage[]
  isThinking?: boolean
  providerStatus?: string
  streamPhase?: string
  healthOk?: boolean
}>()

const emit = defineEmits<{
  close: []
  send: [prompt: string]
  ready: [scrollFn: () => void]
}>()

const draft = ref('')
const messagesEl = ref<HTMLElement | null>(null)
const quickActions = [
  '解释本条检测结果',
  '为什么被降分',
  '总结主要异常',
  '推荐先看哪几秒',
  '灵巧手有问题吗',
  '解释 Q_motion 截断规则',
  '帮我写人工复核备注'
]

const providerStatusText = computed(() => {
  if (!props.healthOk) return '模型未连接'
  switch (props.providerStatus) {
    case 'llm': return '本地模型'
    case 'template': return '规则模板'
    default: return '未连接'
  }
})

const streamPhaseText = computed(() => {
  if (!props.healthOk) return '模型服务不可达'
  switch (props.streamPhase) {
    case 'thinking': return '正在分析...'
    case 'fallback': return '模型超时，切换模板解释...'
    default: return '正在分析当前 episode...'
  }
})

function scrollToBottom() {
  nextTick(() => {
    const el = messagesEl.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

watch(() => props.messages, () => scrollToBottom(), { deep: true })

onMounted(() => {
  emit('ready', scrollToBottom)
})

function submit() {
  const value = draft.value.trim()
  if (!value) return
  emit('send', value)
  draft.value = ''
}
</script>

<style scoped>
.ai-panel {
  position: absolute;
  z-index: 30;
  top: 64px;
  right: -18px;
  width: 386px;
  min-height: 454px;
  border-radius: 20px;
  border: 1px solid rgba(198, 216, 234, .86);
  background:
    linear-gradient(180deg, rgba(255,255,255,.97), rgba(249,252,255,.94)),
    radial-gradient(circle at 92% 0%, rgba(31,184,255,.10), transparent 42%);
  box-shadow: 0 24px 48px rgba(20, 40, 64, .14), 0 8px 16px rgba(20, 36, 56, .06);
  backdrop-filter: blur(22px);
  overflow: hidden;
}
.panel-header {
  position: relative;
  padding: 16px 16px 12px;
  border-bottom: 1px solid rgba(219,229,241,.86);
  display: grid;
  grid-template-columns: 42px 1fr 32px;
  gap: 10px;
  align-items: center;
}
.panel-mini-core {
  width: 42px; height: 42px; border-radius: 14px;
  background: linear-gradient(145deg, rgba(11,38,65,.92), rgba(17,96,124,.86));
  box-shadow: inset 0 1px 0 rgba(255,255,255,.28), 0 10px 24px rgba(31,184,255,.16);
  position: relative;
  overflow: hidden;
}
.panel-mini-core::before {
  content: ""; position:absolute; inset:8px; border-radius:50%;
  background: radial-gradient(circle at 35% 30%, #fff, #7cf6e8 18%, #1fb8ff 44%, rgba(25,42,72,.15) 69%);
  box-shadow: 0 0 18px rgba(37,232,212,.65);
}
.panel-title { margin: 0; font-size: 15px; line-height: 1.2; letter-spacing: -0.01em; }
.panel-subtitle { margin: 5px 0 0; font-size: 12px; color: #94a3b8; }
.panel-close {
  width: 30px; height: 30px; border: 0; border-radius: 10px;
  color: #627089; background: #f1f6fb; cursor: pointer; font-size: 18px; line-height: 1;
}
.panel-close:hover { background: #e8f1fa; color: #24364c; }
.panel-notice {
  margin: 12px 16px 0;
  padding: 8px 10px;
  border-radius: 12px;
  background: #f4f9ff;
  border: 1px solid #dfeafa;
  color: #58708c;
  font-size: 12px;
  line-height: 1.5;
}
.quick-actions { display: flex; gap: 8px; flex-wrap: wrap; padding: 12px 16px 2px; }
.quick-actions button {
  border: 1px solid #dce8f4;
  background: #fff;
  color: #42556e;
  border-radius: 999px;
  padding: 7px 9px;
  font-size: 12px;
  cursor: pointer;
}
.quick-actions button:hover { border-color: rgba(31,184,255,.46); color: #19648f; background: #f7fcff; }
.messages {
  height: 208px;
  overflow: auto;
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.msg { display: flex; }
.msg.user { justify-content: flex-end; }
.bubble {
  max-width: 88%;
  padding: 10px 11px;
  border-radius: 14px;
  font-size: 13px;
  line-height: 1.62;
  color: #33475f;
  background: #f1f6fb;
}
.msg.user .bubble { background: #e9f8ff; color: #1b5e83; }
.typing { display:inline-flex; gap: 3px; vertical-align: middle; margin-right: 6px; }
.typing i { width: 5px; height: 5px; border-radius:50%; background:#56bde8; animation: typing 1s ease-in-out infinite; }
.typing i:nth-child(2) { animation-delay: .12s; }
.typing i:nth-child(3) { animation-delay: .24s; }
.panel-input {
  display: grid;
  grid-template-columns: 1fr 56px;
  gap: 8px;
  padding: 12px 16px 16px;
  border-top: 1px solid rgba(219,229,241,.72);
}
.panel-input input {
  width: 100%;
  border: 1px solid #dce8f4;
  border-radius: 13px;
  padding: 10px 11px;
  font-size: 13px;
  outline: none;
}
.panel-input input:focus { border-color: rgba(31,184,255,.58); box-shadow: 0 0 0 3px rgba(31,184,255,.10); }
.panel-input button {
  border: 0;
  border-radius: 13px;
  background: linear-gradient(135deg, #1fb8ff, #25e8d4);
  color: #fff;
  font-weight: 700;
  cursor: pointer;
}
@keyframes typing { 0%,100% { transform: translateY(0); opacity:.35; } 50% { transform: translateY(-3px); opacity:1; } }
</style>
