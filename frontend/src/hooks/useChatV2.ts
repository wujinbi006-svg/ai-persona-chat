/**
 * Chat Core 2.0 - 前端统一聊天状态管理（Phase 2）
 *
 * 核心特性：
 * 1. 乐观更新：用户发送消息立即显示，不等待服务器
 * 2. 统一 SSE 事件处理：所有事件（generation_started/character_started/content/...）
 * 3. 本地状态直接更新：SSE 事件携带完整数据，直接 append，不重新拉取整个列表
 * 4. 生成锁：前端防止重复点击（后端也有 ConversationLock 双重保障）
 * 5. AbortController：真正取消请求（停止不只是视觉效果）
 * 6. 性能 Trace：记录 T0~T16 时间点，输出 TTFT 和完整响应时间
 *
 * 这是 Phase 2 的核心，后续 Phase 6 UI 收敛时会替换 App.tsx 中的旧逻辑。
 * 目前与旧逻辑并存，不破坏现有功能。
 */
import { useState, useRef, useCallback, useEffect } from 'react'
import { api } from '../services/api'
import type { Message, Character } from '../types'

// ============================================================
// 类型定义
// ============================================================

export type ChatMode = 'normal' | 'group' | 'drama'
export type SpeakerStrategy = 'specific' | 'mention' | 'smart'
export type GenerationStatus = 'idle' | 'running' | 'paused' | 'stopping' | 'stopped' | 'completed' | 'error'

export interface GenerationState {
  status: GenerationStatus
  generationId: string | null
  currentCharacterId: number | null
  currentCharacterName: string
  currentSpeakerIndex: number
  totalSpeakers: number
  streamingContent: string
  errorMessage: string | null
}

export interface UseChatV2Options {
  conversationId: number | null
  characters: Character[]
  initialMessages?: Message[]
  onTraceData?: (trace: PerfTraceData) => void  // Trace 数据回调
}

// ============================================================
// 性能 Trace 类型
// ============================================================

export interface PerfTraceData {
  trace_id: string
  mode: string
  strategy: string
  conversation_id: number
  cold_start: boolean
  llm_request_count: number
  retry_count: number
  // 前端时间点（performance.now() 毫秒）
  t0_user_click: number | null
  t1_post_sent: number | null
  t14_first_sse_browser: number | null
  t15_ui_first_token: number | null
  t16_complete: number | null
  // 后端时间点（相对于 T2 的毫秒）
  t2_backend_received_ms: number
  t3_auth_done_ms: number | null
  t4_db_query_done_ms: number | null
  t5_memory_start_ms: number | null
  t6_memory_done_ms: number | null
  t7_plan_start_ms: number | null
  t8_plan_done_ms: number | null
  t9_session_created_ms: number | null
  t10_llm_request_sent_ms: number | null
  t11_llm_connection_ms: number | null
  t12_llm_streaming_start_ms: number | null
  t13_first_token_backend_ms: number | null
  t16_complete_ms: number | null
  // 关键耗时区间
  durations: {
    frontend_to_backend_ms: number | null
    auth_ms: number | null
    db_query_ms: number | null
    memory_retrieval_ms: number | null
    response_plan_ms: number | null
    session_creation_ms: number | null
    llm_connection_ms: number | null
    llm_ttft_ms: number | null
    llm_generation_ms: number | null
    total_backend_ms: number | null
    time_to_first_token_ms: number | null
  }
  // 逐角色 trace
  speaker_traces: Array<{
    character_id: number
    character_name: string
    speaker_index: number
    llm_request_sent_ms: number | null
    llm_connection_ms: number | null
    llm_streaming_start_ms: number | null
    first_token_backend_ms: number | null
    generation_complete_ms: number | null
    token_count: number
    error: string | null
    ttft_ms: number | null
    generation_duration_ms: number | null
  }>
  // 前端计算的关键指标
  frontend_metrics: {
    ttft_ms: number | null       // T0 -> T15（用户点击到 UI 显示首 token）
    full_response_ms: number | null  // T0 -> T16（用户点击到完整回复结束）
    sse_latency_ms: number | null    // T1 -> T14（POST 发出到首个 SSE 事件）
    ui_render_ms: number | null       // T14 -> T15（SSE 事件到 UI 渲染）
  }
}

// ============================================================
// 乐观更新的临时消息 ID
// ============================================================

let optimisticIdCounter = 0
function generateOptimisticId(): number {
  optimisticIdCounter += 1
  return -Date.now() - optimisticIdCounter
}

// ============================================================
// Hook 实现
// ============================================================

export function useChatV2({ conversationId, characters, initialMessages = [], onTraceData }: UseChatV2Options) {
  // 消息列表（乐观更新直接修改这个状态）
  const [messages, setMessages] = useState<Message[]>(initialMessages)

  // 生成状态
  const [generation, setGeneration] = useState<GenerationState>({
    status: 'idle',
    generationId: null,
    currentCharacterId: null,
    currentCharacterName: '',
    currentSpeakerIndex: 0,
    totalSpeakers: 0,
    streamingContent: '',
    errorMessage: null,
  })

  // 图片生成状态
  const [imageGeneratingCharacter, setImageGeneratingCharacter] = useState<{ id: number; name: string } | null>(null)

  // Refs（用于异步回调中访问最新状态）
  const abortControllerRef = useRef<AbortController | null>(null)
  const messagesRef = useRef<Message[]>(initialMessages)
  const generationRef = useRef<GenerationState>(generation)
  const onTraceDataRef = useRef(onTraceData)

  // 同步 ref
  useEffect(() => {
    messagesRef.current = messages
  }, [messages])

  useEffect(() => {
    generationRef.current = generation
  }, [generation])

  useEffect(() => {
    onTraceDataRef.current = onTraceData
  }, [onTraceData])

  // ============================================================
  // 工具函数
  // ============================================================

  const findCharacter = useCallback((characterId: number | null): Character | undefined => {
    if (!characterId) return undefined
    return characters.find(c => c.id === characterId)
  }, [characters])

  const appendMessage = useCallback((message: Message) => {
    setMessages(prev => [...prev, message])
  }, [])

  const updateMessage = useCallback((messageId: number | string, updates: Partial<Message>) => {
    setMessages(prev => prev.map(m => (m.id === messageId ? { ...m, ...updates } : m)))
  }, [])

  // ============================================================
  // 统一 SSE 事件处理
  // ============================================================

  const handleSSEEvent = useCallback((event: any) => {
    const type = event.type

    switch (type) {
      // ---- 生成生命周期 ----
      case 'generation_started': {
        setGeneration(prev => ({
          ...prev,
          status: 'running',
          generationId: event.generation_id,
          totalSpeakers: event.speakers?.length || 0,
          currentSpeakerIndex: 0,
          streamingContent: '',
          errorMessage: null,
        }))
        break
      }

      case 'generation_completed': {
        setGeneration(prev => ({
          ...prev,
          status: 'completed',
          streamingContent: '',
          currentCharacterId: null,
          currentCharacterName: '',
        }))
        break
      }

      case 'generation_stopped': {
        setGeneration(prev => ({
          ...prev,
          status: 'stopped',
          streamingContent: '',
          currentCharacterId: null,
          currentCharacterName: '',
        }))
        break
      }

      case 'generation_error': {
        setGeneration(prev => ({
          ...prev,
          status: 'error',
          errorMessage: event.message || '生成失败',
          streamingContent: '',
          currentCharacterId: null,
          currentCharacterName: '',
        }))
        break
      }

      case 'generation_conflict': {
        // 后端 ConversationLock 拒绝了重复请求
        setGeneration(prev => ({
          ...prev,
          status: 'error',
          errorMessage: event.message || '当前正在回复，请稍候',
        }))
        break
      }

      // ---- 角色生命周期 ----
      case 'character_started': {
        const char = findCharacter(event.character_id)
        setGeneration(prev => ({
          ...prev,
          currentCharacterId: event.character_id,
          currentCharacterName: event.character_name || char?.name || '',
          currentSpeakerIndex: event.speaker_index ?? prev.currentSpeakerIndex,
          streamingContent: '',
        }))
        break
      }

      case 'character_completed': {
        // 角色完成，streamingContent 已经在 content 事件中累积并保存
        setGeneration(prev => ({
          ...prev,
          streamingContent: '',
        }))
        break
      }

      // ---- 文本内容 ----
      case 'content': {
        const char = findCharacter(event.character_id)
        const charName = event.character_name || char?.name || ''

        setGeneration(prev => {
          const newContent = prev.streamingContent + (event.text || '')
          return { ...prev, streamingContent: newContent }
        })
        break
      }

      // ---- 图片生成 ----
      case 'image_start': {
        setImageGeneratingCharacter({
          id: event.character_id,
          name: event.character_name,
        })
        break
      }

      case 'image_done': {
        setImageGeneratingCharacter(null)
        // 图片消息直接 append 到本地状态（不重新拉取）
        if (event.image_url) {
          const char = findCharacter(event.character_id)
          const imgMessage: Message = {
            id: event.message_id || generateOptimisticId(),
            conversation_id: conversationId || 0,
            character_id: event.character_id || null,
            character_name: event.character_name || char?.name || null,
            role: 'assistant',
            content: '',
            image_url: event.image_url,
            created_at: new Date().toISOString(),
          }
          appendMessage(imgMessage)
        }
        break
      }

      case 'image_error': {
        setImageGeneratingCharacter(null)
        // 图片错误不中断聊天，只显示提示
        break
      }

      // ---- 旧版兼容事件（character_done 等同 character_completed）----
      case 'character_done': {
        setGeneration(prev => ({
          ...prev,
          streamingContent: '',
        }))
        break
      }

      case 'done': {
        setGeneration(prev => ({
          ...prev,
          status: 'completed',
          streamingContent: '',
          currentCharacterId: null,
          currentCharacterName: '',
        }))
        break
      }

      case 'error': {
        setGeneration(prev => ({
          ...prev,
          status: 'error',
          errorMessage: event.message || '生成失败',
          streamingContent: '',
        }))
        break
      }

      // trace_data 事件不在此处处理，在 sendMessage 中处理
      default:
        // 未知事件类型，忽略
        break
    }
  }, [conversationId, findCharacter, appendMessage])

  // ============================================================
  // 发送消息（乐观更新 + v2 统一接口 + 性能 Trace）
  // ============================================================

  const sendMessage = useCallback(async (params: {
    message: string
    mode?: ChatMode
    strategy?: SpeakerStrategy
    characterId?: number
    mentionedCharacterIds?: number[]
    dramaConfig?: Record<string, any>
  }) => {
    if (!conversationId) {
      setGeneration(prev => ({ ...prev, status: 'error', errorMessage: '未选择会话' }))
      return
    }

    // 前端生成锁：防止重复点击
    if (generationRef.current.status === 'running') {
      setGeneration(prev => ({
        ...prev,
        status: 'error',
        errorMessage: '当前正在回复，请稍候',
      }))
      return
    }

    const { message, mode = 'normal', strategy = 'specific', characterId, mentionedCharacterIds, dramaConfig } = params

    // T0: 用户点击发送
    const t0 = performance.now()

    // 1. 乐观更新：立即显示用户消息
    const optimisticUserMsg: Message = {
      id: generateOptimisticId(),
      conversation_id: conversationId,
      character_id: null,
      character_name: null,
      role: 'user',
      content: message,
      image_url: null,
      created_at: new Date().toISOString(),
    }
    appendMessage(optimisticUserMsg)

    // 2. 创建 AbortController（用于真正取消请求）
    const controller = new AbortController()
    abortControllerRef.current = controller

    // 3. 重置生成状态
    setGeneration(prev => ({
      ...prev,
      status: 'running',
      streamingContent: '',
      errorMessage: null,
    }))

    // Trace 时间点记录
    let t1: number | null = null       // T1: 前端 POST 发出
    let t14: number | null = null      // T14: 第一个 SSE event 到达浏览器
    let t15: number | null = null      // T15: UI 显示第一个 token
    let t16: number | null = null      // T16: 完整回复结束
    let firstSSEEvent = false
    let firstContentToken = false
    let backendTrace: any = null

    try {
      // T1: 前端 POST 发出（在调用 api.chatV2Generate 前标记）
      t1 = performance.now()

      // 4. 调用 v2 统一接口（传递 T0/T1 给后端）
      const stream = api.chatV2Generate({
        conversation_id: conversationId,
        message,
        mode,
        strategy,
        character_id: characterId,
        mentioned_character_ids: mentionedCharacterIds,
        drama_config: dramaConfig,
        traceT0: t0,
        traceT1: t1,
      })

      // 5. 处理 SSE 事件流
      let assistantContent = ''
      let currentCharId: number | null = null

      for await (const event of stream) {
        if (controller.signal.aborted) break

        // T14: 第一个 SSE event 到达浏览器
        if (!firstSSEEvent) {
          firstSSEEvent = true
          t14 = performance.now()
        }

        // 处理 trace_data 事件（后端返回的完整 trace）
        if (event.type === 'trace_data') {
          backendTrace = event.trace
          continue
        }

        // T15: UI 显示第一个 token（第一个 content 事件）
        if (event.type === 'content' && !firstContentToken) {
          firstContentToken = true
          t15 = performance.now()
        }

        // 追踪当前角色的完整回复（用于保存到本地状态）
        if (event.type === 'character_started') {
          assistantContent = ''
          currentCharId = event.character_id ?? null
        } else if (event.type === 'content') {
          assistantContent += event.text || ''
        } else if (event.type === 'character_completed' || event.type === 'character_done') {
          // 角色完成，把完整回复保存到本地状态（不重新拉取）
          if (assistantContent.trim() && currentCharId != null) {
            const char = findCharacter(currentCharId)
            const assistantMsg: Message = {
              id: generateOptimisticId(),
              conversation_id: conversationId,
              character_id: currentCharId,
              character_name: char?.name || event.character_name || null,
              role: 'assistant',
              content: assistantContent,
              image_url: null,
              created_at: new Date().toISOString(),
            }
            appendMessage(assistantMsg)
          }
          assistantContent = ''
          currentCharId = null
        }

        handleSSEEvent(event)
      }

      // T16: 完整回复结束
      t16 = performance.now()

      // 如果流正常结束但没有收到 generation_completed，确保状态重置
      if ((generationRef.current.status as string) === 'running') {
        setGeneration(prev => ({
          ...prev,
          status: 'completed',
          streamingContent: '',
          currentCharacterId: null,
          currentCharacterName: '',
        }))
      }

    } catch (error: any) {
      if (controller.signal.aborted) {
        // 用户主动停止，不算错误
        t16 = performance.now()
        setGeneration(prev => ({
          ...prev,
          status: 'stopped',
          streamingContent: '',
          currentCharacterId: null,
          currentCharacterName: '',
        }))
      } else {
        setGeneration(prev => ({
          ...prev,
          status: 'error',
          errorMessage: error.message || '请求失败',
          streamingContent: '',
        }))
      }
    } finally {
      abortControllerRef.current = null
      setImageGeneratingCharacter(null)

      // 输出性能 Trace 数据
      if (backendTrace && t0 && t16) {
        const perfData: PerfTraceData = {
          ...backendTrace,
          t0_user_click: t0,
          t1_post_sent: t1,
          t14_first_sse_browser: t14,
          t15_ui_first_token: t15,
          t16_complete: t16,
          frontend_metrics: {
            ttft_ms: t15 ? Math.round(t15 - t0) : null,
            full_response_ms: Math.round(t16 - t0),
            sse_latency_ms: t14 && t1 ? Math.round(t14 - t1) : null,
            ui_render_ms: t15 && t14 ? Math.round(t15 - t14) : null,
          },
        }

        // 输出到控制台（便于调试）
        console.log('[PerfTrace]', JSON.stringify(perfData, null, 2))

        // 调用回调
        if (onTraceDataRef.current) {
          onTraceDataRef.current(perfData)
        }
      }
    }
  }, [conversationId, appendMessage, handleSSEEvent, findCharacter])

  // ============================================================
  // 停止生成（真正取消请求，不只是视觉效果）
  // ============================================================

  const stopGeneration = useCallback(async () => {
    // 1. 前端取消 fetch 请求
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }

    // 2. 通知后端停止（后端 ConversationLock + GenerationSession 会处理）
    if (conversationId) {
      try {
        await api.chatV2Stop(conversationId, generationRef.current.generationId || undefined)
      } catch {
        // 后端停止失败不影响前端状态
      }
    }

    // 3. 更新前端状态
    setGeneration(prev => ({
      ...prev,
      status: 'stopped',
      streamingContent: '',
      currentCharacterId: null,
      currentCharacterName: '',
    }))
    setImageGeneratingCharacter(null)
  }, [conversationId])

  // ============================================================
  // 暂停 / 继续（剧情模式用）
  // ============================================================

  const pauseGeneration = useCallback(async () => {
    if (!conversationId) return
    try {
      await api.chatV2Pause(conversationId)
      setGeneration(prev => ({ ...prev, status: 'paused' }))
    } catch (error: any) {
      setGeneration(prev => ({ ...prev, errorMessage: error.message }))
    }
  }, [conversationId])

  const resumeGeneration = useCallback(async () => {
    if (!conversationId) return
    try {
      await api.chatV2Resume(conversationId)
      setGeneration(prev => ({ ...prev, status: 'running' }))
    } catch (error: any) {
      setGeneration(prev => ({ ...prev, errorMessage: error.message }))
    }
  }, [conversationId])

  // ============================================================
  // 消息管理
  // ============================================================

  const setMessagesDirect = useCallback((newMessages: Message[]) => {
    setMessages(newMessages)
  }, [])

  const clearMessages = useCallback(() => {
    setMessages([])
  }, [])

  // ============================================================
  // 组件卸载时清理
  // ============================================================

  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
    }
  }, [])

  // ============================================================
  // 返回
  // ============================================================

  return {
    // 状态
    messages,
    generation,
    imageGeneratingCharacter,
    isGenerating: generation.status === 'running',
    isPaused: generation.status === 'paused',

    // 操作
    sendMessage,
    stopGeneration,
    pauseGeneration,
    resumeGeneration,
    setMessages: setMessagesDirect,
    clearMessages,
    appendMessage,
    updateMessage,

    // 工具
    findCharacter,
  }
}

export default useChatV2
