import { ref, computed } from 'vue'
import { fetchOrCreateConversation, postChatMessage } from '../api/client'
import type { AiMessageItem, AiChatResponse, PageState } from '../types/qc'

export type AiProviderStatus = 'template' | 'llm' | 'unavailable'
export type AiStatus = 'idle' | 'thinking' | 'error'

export interface AiMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  provider?: string | null
  model?: string | null
}

let _seq = 0

export function useAiAssistant() {
  const isOpen = ref(false)
  const isThinking = ref(false)
  const providerStatus = ref<AiProviderStatus>('template')
  const lastError = ref<string | null>(null)
  const conversationId = ref<string>('')
  const episodeId = ref<string>('')

  const lastChatResponse = ref<AiChatResponse | null>(null)
  const messages = ref<AiMessage[]>([
    {
      id: `msg-${++_seq}`,
      role: 'assistant',
      content: '我可以解释当前 episode 的自动检测结果、主要短板和建议关注点。'
    }
  ])

  const status = computed<AiStatus>(() => {
    if (lastError.value) return 'error'
    if (isThinking.value) return 'thinking'
    return 'idle'
  })

  function open() { isOpen.value = true }
  function close() { isOpen.value = false }

  function addMessage(role: 'user' | 'assistant', content: string, meta?: { provider?: string; model?: string }) {
    messages.value.push({
      id: `msg-${++_seq}`,
      role,
      content,
      provider: meta?.provider,
      model: meta?.model,
    })
  }

  /** 首次打开或切换 episode 时调用，恢复服务端对话 */
  async function loadConversation(epId: string) {
    episodeId.value = epId

    if (conversationId.value) {
      // 已有 conversation，从服务端刷新消息
      try {
        const { fetchConversationMessages } = await import('../api/client')
        const detail = await fetchConversationMessages(conversationId.value)
        if (detail.messages && detail.messages.length > 0) {
          messages.value = detail.messages.map((m: AiMessageItem) => ({
            id: m.id,
            role: m.role as 'user' | 'assistant' | 'system',
            content: m.content,
            provider: m.provider,
            model: m.model,
          }))
          return
        }
      } catch {
        // 恢复失败，继续用本地消息
      }
      return
    }

    // 创建新 conversation
    try {
      const detail = await fetchOrCreateConversation(epId)
      conversationId.value = detail.conversationId
      if (detail.messages && detail.messages.length > 0) {
        messages.value = detail.messages.map((m: AiMessageItem) => ({
          id: m.id,
          role: m.role as 'user' | 'assistant' | 'system',
          content: m.content,
          provider: m.provider,
          model: m.model,
        }))
      }
    } catch (err) {
      console.warn('Failed to load conversation:', err)
      // 离线模式：使用本地消息
    }
  }

  /** 发送消息并获取 AI 回复 */
  async function send(
    prompt: string,
    context: {
      episodeId: string
      qMotionScore: number
      qMotionLevel: string
      weightedScoreBeforeCap?: number | null
      metrics: any[]
      timelineSegments?: any[]
    },
    pageState?: PageState | null,
  ) {
    addMessage('user', prompt)
    isThinking.value = true
    lastError.value = null

    // 确保有 conversation
    if (!conversationId.value) {
      await loadConversation(context.episodeId)
    }

    try {
      const resp = await postChatMessage({
        conversationId: conversationId.value,
        episodeId: context.episodeId,
        message: prompt,
        pageState: pageState || null,
        qMotionScore: context.qMotionScore,
        qMotionLevel: context.qMotionLevel,
        weightedScoreBeforeCap: context.weightedScoreBeforeCap || null,
        metrics: context.metrics,
        timelineSegments: context.timelineSegments || [],
        stream: false,
      })

      lastChatResponse.value = resp
      conversationId.value = resp.conversationId
      providerStatus.value = resp.source === 'llm' ? 'llm' : 'template'
      addMessage('assistant', resp.answer, { provider: resp.source, model: resp.model || undefined })
    } catch (err) {
      lastError.value = err instanceof Error ? err.message : 'unknown error'
      addMessage('assistant', 'AI 解读暂不可用，请以指标、视频和人工判断为准。')
    } finally {
      isThinking.value = false
    }
  }

  function reset(initialMessage?: string) {
    messages.value = [{
      id: `msg-${++_seq}`,
      role: 'assistant',
      content: initialMessage || '我可以解释当前 episode 的自动检测结果、主要短板和建议关注点。'
    }]
    lastChatResponse.value = null
    lastError.value = null
    conversationId.value = ''
  }

  return {
    isOpen,
    isThinking,
    providerStatus,
    lastError,
    conversationId,
    episodeId,
    lastChatResponse,
    messages,
    status,
    open,
    close,
    loadConversation,
    send,
    reset,
    addMessage,
  }
}
