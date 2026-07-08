import { ref, computed } from 'vue'
import { fetchOrCreateConversation, postChatMessage, postChatStream, checkAiHealth } from '../api/client'
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
  /** 流式输出时的当前阶段 */
  const streamPhase = ref<string>('')
  const healthOk = ref(true)
  /** 面板组件设置的滚动回调 */
  let _scrollToBottom: (() => void) | null = null
  function setScrollFn(fn: (() => void) | null) { _scrollToBottom = fn }

  async function checkHealth(): Promise<boolean> {
    try {
      const r = await checkAiHealth()
      healthOk.value = r.ok
      return r.ok
    } catch {
      healthOk.value = false
      return false
    }
  }
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
      } catch { /* 离线降级 */ }
      return
    }

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
    }
  }

  /** 发送消息（非流式，兼容保留） */
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

  /** 流式发送消息。每条流式 chunk 直接追加到消息列表最后一条 assistant 消息上。 */
  async function sendStream(
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
    _scrollToBottom?.()

    // 快速健康检查（3s 超时）
    const ok = await checkHealth()
    if (!ok) {
      addMessage('assistant', '无法连接 AI 模型服务，请确认模型服务器已启动。')
      return
    }

    isThinking.value = true
    lastError.value = null
    streamPhase.value = ''

    if (!conversationId.value) {
      await loadConversation(context.episodeId)
    }

    // 占位消息，之后逐 chunk 追加
    const streamingId = `msg-${++_seq}`
    messages.value.push({ id: streamingId, role: 'assistant', content: '' })

    try {
      const stream = postChatStream({
        conversationId: conversationId.value,
        episodeId: context.episodeId,
        message: prompt,
        pageState: pageState || null,
        qMotionScore: context.qMotionScore,
        qMotionLevel: context.qMotionLevel,
        weightedScoreBeforeCap: context.weightedScoreBeforeCap || null,
        metrics: context.metrics,
        timelineSegments: context.timelineSegments || [],
        stream: true,
      })

      let finalSource = ''
      let finalModel = ''

      for await (const sse of stream) {
        switch (sse.event) {
          case 'status':
            streamPhase.value = sse.data?.phase || ''
            break
          case 'text':
            // 逐 chunk 追加到占位消息
            const chunk = sse.data?.text || ''
            const msg = messages.value.find(m => m.id === streamingId)
            if (msg) {
              msg.content += chunk
              messages.value = [...messages.value]
              _scrollToBottom?.()
            }
            break
          case 'meta':
            finalSource = sse.data?.source || ''
            finalModel = sse.data?.model || ''
            conversationId.value = sse.data?.conversationId || conversationId.value
            break
          case 'done':
            break
        }
      }

      // 流式结束，回填 meta 信息
      const finalMsg = messages.value.find(m => m.id === streamingId)
      if (finalMsg) {
        if (finalMsg.content === '') {
          finalMsg.content = 'AI 未返回内容，请重试。'
        }
        if (finalSource) {
          finalMsg.provider = finalSource
          providerStatus.value = finalSource === 'llm' ? 'llm' : 'template'
        }
        if (finalModel) {
          finalMsg.model = finalModel
        }
      }
      streamPhase.value = ''
    } catch (err) {
      lastError.value = err instanceof Error ? err.message : 'unknown error'
      const errorMsg = messages.value.find(m => m.id === streamingId)
      if (errorMsg && errorMsg.content === '') {
        errorMsg.content = 'AI 解读暂不可用，请以指标、视频和人工判断为准。'
      }
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
    isOpen, isThinking, providerStatus, lastError,
    conversationId, episodeId, streamPhase, healthOk,
    lastChatResponse, messages, status,
    open, close, loadConversation, send, sendStream, reset, addMessage,
    setScrollFn, checkHealth,
  }
}
