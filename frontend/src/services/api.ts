import type { Conversation, Character, Message, Memory, ChatStreamChunk } from '../types'
import { authService } from './auth'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'https://ai-persona-backend-znpi.onrender.com/api'

export const BACKEND_ORIGIN = API_BASE.replace(/\/api\/?$/, '')

export function resolveImageUrl(imageUrl: string | null | undefined): string {
  if (!imageUrl) return ''
  if (imageUrl.startsWith('http://') || imageUrl.startsWith('https://') || imageUrl.startsWith('data:')) {
    return imageUrl
  }
  return `${BACKEND_ORIGIN}${imageUrl.startsWith('/') ? '' : '/'}${imageUrl}`
}

async function getAuthHeaders(): Promise<Record<string, string>> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (authService.isSupabaseMode()) {
    const token = await authService.getSessionToken()
    if (token) headers['Authorization'] = `Bearer ${token}`
  }
  return headers
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const headers = await getAuthHeaders()
  const res = await fetch(`${API_BASE}${url}`, {
    headers,
    ...options,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(text || `请求失败 (${res.status})`)
  }
  return res.json()
}

async function* parseSSE(res: Response): AsyncGenerator<ChatStreamChunk, void, unknown> {
  if (!res.body) throw new Error('无响应体')
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed.startsWith('data: ')) continue
      const jsonStr = trimmed.slice(6)
      try {
        yield JSON.parse(jsonStr)
      } catch { /* skip */ }
    }
  }
}

export const api = {
  // 会话
  createConversation: (title?: string) =>
    request<Conversation>('/conversations', {
      method: 'POST',
      body: JSON.stringify({ title }),
    }),
  listConversations: () => request<Conversation[]>('/conversations'),
  getConversation: (id: number) => request<Conversation>(`/conversations/${id}`),
  updateConversation: (id: number, data: { title?: string; scene?: string; scene_time?: string; scene_context?: string }) =>
    request<Conversation>(`/conversations/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  deleteConversation: (id: number) =>
    request<{ ok: boolean }>(`/conversations/${id}`, { method: 'DELETE' }),

  // 角色
  listCharacters: (convId: number) =>
    request<Character[]>(`/conversations/${convId}/characters`),
  createCharacter: (convId: number, name: string, persona: string) =>
    request<Character>(`/conversations/${convId}/characters`, {
      method: 'POST',
      body: JSON.stringify({ name, persona }),
    }),
  updateCharacter: (charId: number, data: { name?: string; persona?: string; sort_order?: number }) =>
    request<Character>(`/characters/${charId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  deleteCharacter: (charId: number) =>
    request<{ ok: boolean }>(`/characters/${charId}`, { method: 'DELETE' }),
  moveCharacter: (charId: number, direction: 'up' | 'down') =>
    request<Character>(`/characters/${charId}/move?direction=${direction}`, { method: 'POST' }),

  // 记忆
  listCharacterMemories: (charId: number) =>
    request<Memory[]>(`/characters/${charId}/memories`),
  listConversationMemories: (convId: number) =>
    request<Memory[]>(`/conversations/${convId}/memories`),
  createCharacterMemory: (charId: number, data: { content: string; memory_type?: string; importance?: number }) =>
    request<Memory>(`/characters/${charId}/memories`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateMemory: (memoryId: number, data: { content?: string; memory_type?: string; importance?: number; is_active?: boolean }) =>
    request<Memory>(`/memories/${memoryId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  deleteMemory: (memoryId: number) =>
    request<{ ok: boolean }>(`/memories/${memoryId}`, { method: 'DELETE' }),

  // 消息
  getMessages: (id: number) => request<Message[]>(`/conversations/${id}/messages`),
  clearMessages: (id: number) =>
    request<{ ok: boolean; deleted: number }>(`/conversations/${id}/messages`, { method: 'DELETE' }),

  // 聊天流式（支持 @角色 和智能模式）
  async *chatStream(conversationId: number, message: string, characterId?: number, mode?: string) {
    const headers = await getAuthHeaders()
    const body: any = { conversation_id: conversationId, message }
    if (characterId) body.character_id = characterId
    if (mode) body.mode = mode
    const res = await fetch(`${API_BASE}/chat/stream`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error(`请求失败 (${res.status})`)
    yield* parseSSE(res)
  },

  // 全部 AI 回复
  async *replyAll(conversationId: number, message?: string) {
    const headers = await getAuthHeaders()
    const res = await fetch(`${API_BASE}/chat/reply-all`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ conversation_id: conversationId, message }),
    })
    if (!res.ok) throw new Error(`请求失败 (${res.status})`)
    yield* parseSSE(res)
  },

  // 自由讨论
  async *discussion(conversationId: number, characterIds: number[], rounds: number, message?: string) {
    const headers = await getAuthHeaders()
    const res = await fetch(`${API_BASE}/chat/discussion`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ conversation_id: conversationId, character_ids: characterIds, rounds, message }),
    })
    if (!res.ok) throw new Error(`请求失败 (${res.status})`)
    yield* parseSSE(res)
  },

  // 戏剧模式
  async *dramaStream(conversationId: number, characterIds: number[], rounds: number, interval: number, scene?: string, sceneTime?: string, sceneContext?: string) {
    const headers = await getAuthHeaders()
    const body: any = {
      conversation_id: conversationId,
      character_ids: characterIds,
      rounds,
      interval,
    }
    if (scene !== undefined) body.scene = scene
    if (sceneTime !== undefined) body.scene_time = sceneTime
    if (sceneContext !== undefined) body.scene_context = sceneContext
    const res = await fetch(`${API_BASE}/chat/drama/stream`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error(`请求失败 (${res.status})`)
    yield* parseSSE(res)
  },
  dramaPause: () => request<{ ok: boolean }>('/chat/drama/pause', { method: 'POST' }),
  dramaResume: () => request<{ ok: boolean }>('/chat/drama/resume', { method: 'POST' }),
  dramaStop: () => request<{ ok: boolean }>('/chat/drama/stop', { method: 'POST' }),
  dramaInterject: (conversationId: number, message: string) =>
    request<{ ok: boolean }>('/chat/drama/interject', {
      method: 'POST',
      body: JSON.stringify({ conversation_id: conversationId, message }),
    }),

  // 停止
  stopGeneration: () =>
    request<{ ok: boolean }>('/chat/stop', { method: 'POST' }),
}
